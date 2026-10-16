from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.db.models import AuditEvent, LLMCall


def add_event(
    s: AsyncSession,
    *,
    event_type: str,
    run_id: str | None = None,
    recommendation_id: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    node: str | None = None,
    actor: str = "system",
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        event_type=event_type,
        run_id=run_id,
        recommendation_id=recommendation_id,
        subject_type=subject_type,
        subject_id=subject_id,
        node=node,
        actor=actor,
        payload=payload or {},
    )
    s.add(ev)
    return ev


async def query(
    s: AsyncSession,
    *,
    run_id: str | None = None,
    recommendation_id: str | None = None,
    subject_id: str | None = None,
    limit: int = 500,
) -> Sequence[AuditEvent]:
    q = select(AuditEvent)
    if run_id:
        q = q.where(AuditEvent.run_id == run_id)
    if recommendation_id:
        q = q.where(AuditEvent.recommendation_id == recommendation_id)
    if subject_id:
        q = q.where(AuditEvent.subject_id == subject_id)
    return (await s.execute(q.order_by(AuditEvent.id).limit(limit))).scalars().all()


async def llm_calls_for_run(s: AsyncSession, run_id: str) -> Sequence[LLMCall]:
    q = select(LLMCall).where(LLMCall.run_id == run_id).order_by(LLMCall.created_at)
    return (await s.execute(q)).scalars().all()
