from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.api.deps import db_session
from insurance_poc.api.errors import not_found
from insurance_poc.api.naming import subject_lines, subject_names
from insurance_poc.api.schemas.common import Page, RunOut
from insurance_poc.db.models import Approval, Lead, Product, Recommendation, User
from insurance_poc.db.repositories import audit as audit_repo
from insurance_poc.db.repositories import recommendations as recs_repo
from insurance_poc.db.repositories import runs as runs_repo
from insurance_poc.services import approachability, justification, next_steps

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RecOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    use_case: str
    subject_type: str
    subject_id: str
    cycle_key: str
    status: str
    version: int
    queue: str
    priority: str
    action: str
    channel_owner: str | None
    band: str | None
    confidence: str | None
    needs_review: bool
    review_reasons: list[Any]
    explanation: str | None
    channel: str | None
    expires_at: datetime | None
    created_at: datetime
    decided_at: datetime | None
    subject_name: str | None = None
    line: str | None = None


class RecDetail(RecOut):
    checklist: dict[str, Any]
    rulebook_version: str | None
    signals: dict[str, Any]
    decisions: dict[str, Any]
    rule_results: list[Any]
    missing_info: list[Any]
    products: list[Any]
    cross_sell: list[dict[str, Any]] = Field(
        default=[],
        description="Products from other lines the rules allow and the AI suggested, with reasons",
    )
    product_screening: list[dict[str, Any]] = Field(
        default=[],
        description="Every catalogue product: rule status (eligible / not_suitable / "
        "not_assessed) with reasons, merged with the AI's pick (recommended / ranked / also_suits)",
    )
    approachability: dict[str, Any] = Field(
        default={}, description="0-100 score: can the team reach out, and how keen the lead is"
    )
    next_steps: list[dict[str, Any]] = Field(
        default=[], description="Ordered to-do list for the team"
    )
    fairness: dict[str, Any]
    subject: dict[str, Any] = {}
    decided_by_user: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    run: RunOut | None = None
    llm_calls: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    justification: dict[str, Any] = {}


@router.get("", response_model=Page[RecOut])
async def list_recommendations(
    status: str | None = "pending_approval",
    use_case: str | None = None,
    queue: str | None = None,
    priority: str | None = None,
    line: str | None = Query(None, description="Product line of the lead"),
    q: str | None = Query(None, max_length=100, description="Customer name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    s: AsyncSession = Depends(db_session),
) -> Page[RecOut]:
    """Default view is the approval queue (``status=pending_approval``); pass ``status=``
    empty for all."""
    rows, total = await recs_repo.list_(
        s,
        status=status or None,
        use_case=use_case,
        queue=queue,
        priority=priority,
        search=q,
        line=line,
        limit=limit,
        offset=offset,
    )
    subjects = [(r.subject_type, r.subject_id) for r in rows]
    names = await subject_names(s, subjects)
    lines = await subject_lines(s, subjects)
    items = [
        RecOut.model_validate(r).model_copy(
            update={"subject_name": names.get(r.subject_id), "line": lines.get(r.subject_id)}
        )
        for r in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


def _screening(rec: Recommendation) -> list[dict[str, Any]]:
    """Rule screening of the catalogue, with the AI's ranking laid on top."""
    dec: dict[str, Any] = rec.decisions or {}
    rows = (dec.get("product_screening") or {}).get("products") or []
    ranked = [p for p in rec.products or [] if isinstance(p, dict)]
    rank = {p.get("code"): (i, p) for i, p in enumerate(ranked)}
    also = {
        x.get("code"): x
        for x in (dec.get("product_fit") or {}).get("also_suggest") or []
        if isinstance(x, dict)
    }
    out = []
    for row in rows:
        code = row.get("code")
        ai: dict[str, Any] = {"ai_status": None}
        if code in rank:
            i, p = rank[code]
            ai = {
                "ai_status": "recommended" if i == 0 else "ranked",
                "rank": i + 1,
                "fit": p.get("fit"),
                "rationale": p.get("rationale"),
            }
        elif code in also:
            x = also[code]
            ai = {
                "ai_status": "also_suits",
                "rationale": x.get("rationale"),
                "needs_underwriter": x.get("needs_underwriter"),
            }
        out.append({**row, **ai})
    return out


async def _subject(s: AsyncSession, rec: Recommendation) -> dict[str, Any]:
    lead = await s.get(Lead, rec.subject_id)
    if lead is None:
        return {}
    return {
        "type": "lead",
        "id": lead.id,
        "external_ref": lead.external_ref,
        "name": f"{lead.first_name or ''} {lead.last_name or ''}".strip(),
        "first_name": lead.first_name,
        "email": lead.email,
        "phone": lead.phone,
        "consent_email": lead.consent_email,
        "consent_sms": lead.consent_sms,
        "product_line": lead.product_line,
        "source": lead.source,
        "intermediary": lead.intermediary,
        "documents_provided": lead.documents_provided,
        "sum_insured": lead.sum_insured_requested,
        "declared": lead.declared,
        "notes": lead.notes,
        "status": lead.status,
    }


@router.get("/{rec_id}", response_model=RecDetail)
async def get_recommendation(rec_id: str, s: AsyncSession = Depends(db_session)) -> RecDetail:
    rec = await recs_repo.get(s, rec_id)
    if rec is None:
        raise not_found("recommendation", rec_id)
    out = RecDetail.model_validate(rec)
    codes = [p.get("code") for p in out.products if isinstance(p, dict) and p.get("code")]
    if codes:  # catalogue facts for display; the stored ranking is not changed
        catalogue = {
            p.code: p
            for p in (await s.execute(select(Product).where(Product.code.in_(codes)))).scalars()
        }

        def facts(code: str | None) -> dict[str, Any]:
            p = catalogue.get(code or "")
            if p is None:
                return {"name": code}
            return {
                "name": p.name,
                "line": p.line,
                "tier": p.tier,
                "description": p.description,
                "base_premium": p.base_premium / 100,  # catalogue "price from", whole units
                "payment_frequency": p.payment_frequency,
            }

        out.products = [
            {**p, **facts(p.get("code"))} if isinstance(p, dict) else p for p in out.products
        ]
    fit = (rec.decisions or {}).get("product_fit") or {}
    out.cross_sell = [x for x in fit.get("also_suggest") or [] if isinstance(x, dict)]
    out.product_screening = _screening(rec)
    out.subject = await _subject(s, rec)
    out.next_steps = next_steps.for_lead(rec, out.subject)
    out.approachability = approachability.compute(rec)
    out.subject_name = out.subject.get("name") or None
    out.line = out.subject.get("product_line") or None
    if rec.decided_by:
        u = await s.get(User, rec.decided_by)
        out.decided_by_user = {"id": u.id, "name": u.name, "role": u.role} if u else None
    apv = (
        await s.execute(select(Approval).where(Approval.recommendation_id == rec.id))
    ).scalar_one_or_none()
    if apv:
        out.approval = {
            "decision": apv.decision,
            "actor": apv.actor_name,
            "role": apv.actor_role,
            "reason": apv.reason,
            "edits": apv.edits,
            "original": apv.original_snapshot,
            "at": apv.created_at.isoformat(),
        }
    run = await runs_repo.get(s, rec.run_id)
    out.run = RunOut.of(run) if run else None
    out.llm_calls = [
        {
            "id": c.id,
            "node": c.node,
            "purpose": c.purpose,
            "provider": c.provider,
            "model": c.model,
            "attempt": c.attempt,
            "status": c.status,
            "error": c.error,
            "latency_ms": c.latency_ms,
            "prompt_tokens": c.prompt_tokens,
            "completion_tokens": c.completion_tokens,
            "request": c.request,
            "response_raw": c.response_raw,
            "parsed": c.parsed,
            "created_at": c.created_at.isoformat(),
        }
        for c in await audit_repo.llm_calls_for_run(s, rec.run_id)
    ]
    events = list(await audit_repo.query(s, run_id=rec.run_id))
    events += [
        e for e in await audit_repo.query(s, recommendation_id=rec.id) if e.run_id != rec.run_id
    ]
    out.audit = [
        {
            "id": e.id,
            "ts": e.ts.isoformat(),
            "event_type": e.event_type,
            "node": e.node,
            "actor": e.actor,
            "payload": e.payload,
        }
        for e in sorted(events, key=lambda e: e.id)
    ]
    out.justification = justification.build(rec, events, out.products)
    return out
