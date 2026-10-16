"""Human-in-the-loop decisions: approve / reject / edit (= approve with changes).

Order of checks: exists -> role -> still pending -> version -> expiry -> staleness (re-run hard
rules on *current* data) -> edit validation -> atomic conditional write. The final UPDATE is
guarded by ``status='pending_approval' AND version=?`` so only the first decision wins even if
two reviewers pass every earlier check at the same time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from insurance_poc.api.session_auth import Actor
from insurance_poc.db.models import Approval, Lead, Recommendation, User
from insurance_poc.db.repositories import audit as audit_repo
from insurance_poc.db.session import Database
from insurance_poc.enums import Action, Decision, LeadStatus, RecStatus
from insurance_poc.services.rules import consent
from insurance_poc.services.rules.facts import lead_facts
from insurance_poc.services.rules.routing import approver_roles
from insurance_poc.utils.clock import today, utcnow
from insurance_poc.utils.ids import new_id

EDITABLE_ACTIONS = {Action.CONTACT_AND_QUOTE, Action.NURTURE, Action.REFER_TO_UNDERWRITER}
EDITABLE_FIELDS = {"action"}


class DecisionError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


@dataclass
class DecisionResult:
    recommendation: Recommendation
    approval: Approval
    violations: list[str] = field(default_factory=list)


async def _stale_reason(db: Database, rec: Recommendation) -> str | None:
    """Re-check consent against today's data. Returns a reason if the rec is stale."""
    async with db.session() as s:
        lead = await s.get(Lead, rec.subject_id)
    if lead is None:
        return "lead no longer exists"
    if rec.action == Action.DO_NOT_CONTACT:
        return None
    facts = lead_facts(lead, today())
    if not consent.check_lead_permission(facts).passed:
        return "data permission withdrawn since the recommendation"
    needs_contact = rec.action != Action.REFER_TO_UNDERWRITER
    if needs_contact and not consent.check_lead_consent(facts).passed:
        return "lead consent withdrawn since the recommendation"
    return None


def _validate_edits(rec: Recommendation, edits: dict[str, Any]) -> dict[str, Any]:
    unknown = set(edits) - EDITABLE_FIELDS
    if unknown:
        raise DecisionError(
            422,
            "rule_violation",
            f"Fields not editable: {sorted(unknown)}",
            [{"rule": "edit.field_not_editable", "fields": sorted(unknown)}],
        )
    if not edits:
        raise DecisionError(422, "rule_violation", "Edit needs at least one changed field.")
    changes: dict[str, Any] = {}
    violations: list[dict[str, str]] = []

    action = edits.get("action")
    if rec.action not in EDITABLE_ACTIONS or action not in EDITABLE_ACTIONS:
        violations.append(
            {
                "rule": "edit.acquisition_action",
                "reason": f"Action can only move between {sorted(EDITABLE_ACTIONS)} "
                "(rule outcomes like request_info / do_not_contact are final).",
            }
        )
    elif rec.action == Action.REFER_TO_UNDERWRITER and action != rec.action:
        violations.append(
            {
                "rule": "edit.referral_final",
                "reason": "Underwriting referrals cannot be downgraded.",
            }
        )
    else:
        changes["action"] = action
    if violations:
        raise DecisionError(422, "rule_violation", "Edit breaks business rules.", violations)
    return changes


def _snapshot(rec: Recommendation) -> dict[str, Any]:
    keys = (
        "action",
        "channel",
        "priority",
        "queue",
        "band",
        "confidence",
        "explanation",
        "version",
    )
    return {k: getattr(rec, k) for k in keys}


async def decide(
    db: Database,
    rec_id: str,
    actor: Actor,
    decision: Decision,
    *,
    expected_version: int | None,
    reason: str | None,
    edits: dict[str, Any] | None = None,
) -> DecisionResult:
    async with db.session() as s:
        rec = await s.get(Recommendation, rec_id)
        if rec is None:
            raise DecisionError(404, "not_found", f"recommendation {rec_id} not found")
        if actor.role not in approver_roles(rec.queue):
            raise DecisionError(
                403, "forbidden", f"Role '{actor.role}' cannot decide the {rec.queue} queue."
            )
        if rec.status != RecStatus.PENDING_APPROVAL:
            who = await s.get(User, rec.decided_by) if rec.decided_by else None
            raise DecisionError(
                409,
                "conflict",
                f"Already {rec.status}.",
                {
                    "status": rec.status,
                    "decided_by": who.name if who else None,
                    "decided_at": rec.decided_at.isoformat() if rec.decided_at else None,
                },
            )
        if expected_version is not None and expected_version != rec.version:
            raise DecisionError(
                409,
                "conflict",
                "Recommendation changed; reload it.",
                {"current_version": rec.version},
            )
        version = rec.version

    if decision == Decision.REJECTED and not (reason or "").strip():
        raise DecisionError(422, "rule_violation", "A reason is required to reject.")

    if rec.expires_at and rec.expires_at < utcnow():
        await _close(db, rec, version, RecStatus.EXPIRED, "expired")
        raise DecisionError(409, "expired", "Recommendation expired; re-run to get a fresh one.")

    if decision != Decision.REJECTED:
        stale = await _stale_reason(db, rec)
        if stale:
            await _close(db, rec, version, RecStatus.SUPERSEDED, stale)
            raise DecisionError(409, "stale", f"Recommendation is stale: {stale}.")

    changes = _validate_edits(rec, edits or {}) if decision == Decision.APPROVED_WITH_EDITS else {}
    now = utcnow()
    original = _snapshot(rec)

    async with db.session() as s:
        res = await s.execute(
            update(Recommendation)
            .where(
                Recommendation.id == rec.id,
                Recommendation.status == RecStatus.PENDING_APPROVAL,
                Recommendation.version == version,
            )
            .values(
                status=decision.value,
                version=version + 1,
                decided_at=now,
                decided_by=actor.user_id,
                **changes,
            )
        )
        if res.rowcount != 1:
            raise DecisionError(409, "conflict", "Someone else decided this first; reload it.")
        approval = Approval(
            id=new_id("apv"),
            recommendation_id=rec.id,
            decision=decision.value,
            user_id=actor.user_id,
            actor_name=actor.name,
            actor_role=actor.role,
            session_id=actor.session_id,
            reason=reason,
            edits=edits or {},
            original_snapshot=original,
            created_at=now,
        )
        s.add(approval)
        fresh = await s.get(Recommendation, rec.id, populate_existing=True)
        lead = await s.get(Lead, fresh.subject_id)
        if lead:
            lead.status = LeadStatus.DECIDED.value
        audit_repo.add_event(
            s,
            event_type=f"recommendation.{decision.value}",
            run_id=fresh.run_id,
            recommendation_id=fresh.id,
            subject_type=fresh.subject_type,
            subject_id=fresh.subject_id,
            actor=f"{actor.name} ({actor.role})",
            payload={"reason": reason, "edits": edits or {}},
        )
        try:
            await s.flush()
        except IntegrityError as e:  # approvals.recommendation_id unique backstop
            raise DecisionError(409, "conflict", "Already decided.") from e
    return DecisionResult(recommendation=fresh, approval=approval)


async def _close(
    db: Database, rec: Recommendation, version: int, status: RecStatus, reason: str
) -> None:
    async with db.session() as s:
        res = await s.execute(
            update(Recommendation)
            .where(
                Recommendation.id == rec.id,
                Recommendation.status == RecStatus.PENDING_APPROVAL,
                Recommendation.version == version,
            )
            .values(status=status.value, version=version + 1)
        )
        if res.rowcount == 1:
            audit_repo.add_event(
                s,
                event_type=f"recommendation.{status.value}",
                recommendation_id=rec.id,
                subject_type=rec.subject_type,
                subject_id=rec.subject_id,
                payload={"reason": reason},
            )
