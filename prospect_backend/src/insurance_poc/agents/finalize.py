"""Compose the recommendation and persist it as pending_approval in one transaction.

Gate outcomes (do_not_contact / request_info / knockout) are templated here without any LLM.
Every recommendation passes the code-level guardrails before it is stored.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import update

from insurance_poc import rulebook
from insurance_poc.agents.base import node
from insurance_poc.agents.state import GraphState, deps
from insurance_poc.db.models import Lead, Recommendation
from insurance_poc.db.repositories import audit as audit_repo
from insurance_poc.enums import Action, LeadStatus, Priority, RecStatus
from insurance_poc.services import guardrails
from insurance_poc.services.decisions.needs_review import needs_review
from insurance_poc.services.rules.routing import route_queue
from insurance_poc.utils.audit import audit
from insurance_poc.utils.clock import utcnow
from insurance_poc.utils.context import current_run_id
from insurance_poc.utils.ids import new_id

ACQUISITION_REC_TTL = timedelta(days=14)


def _gate_outcome(state: GraphState) -> dict[str, Any]:
    gate = state["gate"]
    owner = state.get("channel_owner")
    failed = [r for r in state.get("rule_results", []) if not r["passed"]]

    def out(action: Action, explanation: str, **extra: Any) -> dict[str, Any]:
        return {
            "action": action,
            "queue": route_queue(action, owner, regulated_product=False),
            "priority": Priority.LOW,
            "explanation": explanation,
            **extra,
        }

    if gate == "do_not_contact":
        return out(
            Action.DO_NOT_CONTACT,
            "Do not contact: " + "; ".join(r["reason"] for r in failed if r["severity"] == "block"),
        )
    if gate == "request_info":
        fields = ", ".join(m["field"] for m in state.get("missing_info", []))
        return out(Action.REQUEST_INFO, f"Cannot assess yet; missing or invalid: {fields}.")
    if gate == "knockout":
        reasons = "; ".join(r["reason"] for r in failed if r["severity"] == "block")
        return out(
            Action.REFER_TO_UNDERWRITER,
            f"Knock-out rule(s) hit: {reasons} The system does not decline; an underwriter "
            "decides.",
            forced_review=["Knock-out rule hit: underwriter to decide"],
        )
    raise ValueError(f"no template for gate {gate}")


@node("finalize")
async def finalize(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    d = deps(config)
    out: dict[str, Any] = {}
    if state.get("gate") in ("do_not_contact", "request_info", "knockout"):
        out = _gate_outcome(state)

    def pick(key: str) -> Any:
        return out.get(key, state.get(key))

    confidences = [
        v.get("confidence") for v in (state.get("decisions") or {}).values() if isinstance(v, dict)
    ]
    review, review_reasons = needs_review(
        llm_flag=False,
        llm_reason=None,
        confidences=confidences,
        forced=[*state.get("forced_review", []), *out.get("forced_review", [])],
    )
    now = utcnow()
    expires = now + ACQUISITION_REC_TTL

    rec = Recommendation(
        id=new_id("rec"),
        run_id=state.get("run_id") or current_run_id.get(),
        use_case=state["use_case"],
        subject_type=state["subject_type"],
        subject_id=state["subject_id"],
        cycle_key=state["cycle_key"],
        status=RecStatus.PENDING_APPROVAL.value,
        queue=str(pick("queue")),
        priority=str(pick("priority")),
        action=str(pick("action")),
        channel_owner=state.get("channel_owner"),
        checklist=state.get("checklist") or {},
        rulebook_version=rulebook.RULEBOOK_VERSION,
        band=state.get("band"),
        confidence=state.get("confidence"),
        needs_review=review,
        review_reasons=review_reasons,
        signals=state.get("signals") or {},
        decisions=state.get("decisions") or {},
        rule_results=state.get("rule_results") or [],
        missing_info=state.get("missing_info") or [],
        products=state.get("products") or [],
        channel=state.get("channel"),
        explanation=pick("explanation"),
        fairness=state.get("fairness") or {},
        expires_at=expires,
        created_at=now,
    )
    try:
        guardrails.check_recommendation(
            {
                "action": rec.action,
                "channel": rec.channel,
                "channel_owner": rec.channel_owner,
                "status": rec.status,
            }
        )
    except guardrails.GuardrailViolation as e:
        await audit(
            d.db,
            "guardrail.blocked",
            {"rule": e.rule, "error": str(e), "action": rec.action, "channel": rec.channel},
            subject_type=rec.subject_type,
            subject_id=rec.subject_id,
        )
        raise

    async with d.db.session() as s:
        superseded = await s.execute(
            update(Recommendation)
            .where(Recommendation.subject_type == rec.subject_type)
            .where(Recommendation.subject_id == rec.subject_id)
            .where(Recommendation.cycle_key == rec.cycle_key)
            .where(Recommendation.status == RecStatus.PENDING_APPROVAL)
            .values(status=RecStatus.SUPERSEDED.value, version=Recommendation.version + 1)
            .returning(Recommendation.id)
        )
        old_ids = list(superseded.scalars())
        s.add(rec)
        lead = await s.get(Lead, rec.subject_id)
        if lead is not None:
            lead.status = LeadStatus.RECOMMENDED.value
        for old in old_ids:
            audit_repo.add_event(
                s,
                event_type="recommendation.superseded",
                run_id=rec.run_id,
                recommendation_id=old,
                subject_type=rec.subject_type,
                subject_id=rec.subject_id,
                node="finalize",
                payload={"superseded_by": rec.id},
            )
        audit_repo.add_event(
            s,
            event_type="recommendation.created",
            run_id=rec.run_id,
            recommendation_id=rec.id,
            subject_type=rec.subject_type,
            subject_id=rec.subject_id,
            node="finalize",
            payload={
                "action": rec.action,
                "queue": rec.queue,
                "priority": rec.priority,
                "channel_owner": rec.channel_owner,
                "needs_review": rec.needs_review,
                "rulebook_version": rec.rulebook_version,
                "superseded": old_ids,
            },
        )
    return {"recommendation_id": rec.id}
