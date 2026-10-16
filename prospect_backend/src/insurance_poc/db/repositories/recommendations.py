from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.db.models import Lead, Recommendation
from insurance_poc.enums import Priority, RecStatus

# Work queues show high priority first, then newest.
_PRIORITY_RANK = case(
    {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2},
    value=Recommendation.priority,
    else_=3,
)


async def get(s: AsyncSession, rec_id: str) -> Recommendation | None:
    return await s.get(Recommendation, rec_id)


async def latest_by_subject(
    s: AsyncSession, subject_type: str, subject_ids: Iterable[str]
) -> dict[str, Recommendation]:
    ids = list(subject_ids)
    if not ids:
        return {}
    newest = (
        select(Recommendation.subject_id, func.max(Recommendation.created_at).label("ts"))
        .where(Recommendation.subject_type == subject_type, Recommendation.subject_id.in_(ids))
        .group_by(Recommendation.subject_id)
        .subquery()
    )
    q = (
        select(Recommendation)
        .join(
            newest,
            (Recommendation.subject_id == newest.c.subject_id)
            & (Recommendation.created_at == newest.c.ts),
        )
        .where(Recommendation.subject_type == subject_type)
    )
    return {r.subject_id: r for r in (await s.execute(q)).scalars()}


async def open_for_cycle(
    s: AsyncSession, subject_type: str, subject_id: str, cycle_key: str
) -> Recommendation | None:
    q = select(Recommendation).where(
        Recommendation.subject_type == subject_type,
        Recommendation.subject_id == subject_id,
        Recommendation.cycle_key == cycle_key,
        Recommendation.status == RecStatus.PENDING_APPROVAL,
    )
    return (await s.execute(q)).scalar_one_or_none()


async def decided_for_cycle(
    s: AsyncSession, subject_type: str, subject_id: str, cycle_key: str
) -> Recommendation | None:
    q = (
        select(Recommendation)
        .where(
            Recommendation.subject_type == subject_type,
            Recommendation.subject_id == subject_id,
            Recommendation.cycle_key == cycle_key,
            Recommendation.status.in_(
                [RecStatus.APPROVED, RecStatus.APPROVED_WITH_EDITS, RecStatus.REJECTED]
            ),
        )
        .limit(1)
    )
    return (await s.execute(q)).scalar_one_or_none()


async def list_(
    s: AsyncSession,
    *,
    status: str | None = None,
    use_case: str | None = None,
    queue: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    line: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Recommendation], int]:
    q = select(Recommendation)
    if line:
        q = q.where(line_filter(line))
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        lead_ids = select(Lead.id).where(
            func.lower(
                func.coalesce(Lead.first_name, "") + " " + func.coalesce(Lead.last_name, "")
            ).like(term)
        )
        q = q.where(Recommendation.subject_id.in_(lead_ids))
    if status:
        q = q.where(Recommendation.status == status)
    if use_case:
        q = q.where(Recommendation.use_case == use_case)
    if queue:
        q = q.where(Recommendation.queue == queue)
    if priority:
        q = q.where(Recommendation.priority == priority)
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (
            await s.execute(
                q.order_by(
                    _PRIORITY_RANK, Recommendation.created_at.desc(), Recommendation.id.desc()
                )
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


def line_filter(line: str) -> Any:
    """Recommendations whose lead is in one product line."""
    return Recommendation.subject_id.in_(select(Lead.id).where(Lead.product_line == line))
