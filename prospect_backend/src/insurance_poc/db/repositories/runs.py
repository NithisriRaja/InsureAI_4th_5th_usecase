"""Run queue persistence.

Race guards:
- ``enqueue``: the partial unique index (one queued/running run per subject) is the real
  guard; a losing concurrent insert returns the existing active run instead.
- ``claim_next``: single UPDATE ... WHERE status='queued' ... RETURNING, inside BEGIN IMMEDIATE,
  so two workers can never claim the same run.
- ``finish``/``heartbeat``: only the worker that claimed the run may touch it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.db.models import Run
from insurance_poc.enums import ACTIVE_RUN_STATUSES, RunStatus
from insurance_poc.utils.clock import utcnow
from insurance_poc.utils.ids import new_id


async def get(s: AsyncSession, run_id: str) -> Run | None:
    return await s.get(Run, run_id)


async def active_for(s: AsyncSession, subject_type: str, subject_id: str) -> Run | None:
    q = (
        select(Run)
        .where(Run.subject_type == subject_type, Run.subject_id == subject_id)
        .where(Run.status.in_([x.value for x in ACTIVE_RUN_STATUSES]))
        .limit(1)
    )
    return (await s.execute(q)).scalar_one_or_none()


async def latest_for(s: AsyncSession, subject_type: str, subject_id: str) -> Run | None:
    q = (
        select(Run)
        .where(Run.subject_type == subject_type, Run.subject_id == subject_id)
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(1)
    )
    return (await s.execute(q)).scalar_one_or_none()


async def enqueue(
    s: AsyncSession,
    *,
    use_case: str,
    subject_type: str,
    subject_id: str,
    cycle_key: str,
    max_attempts: int,
    batch_id: str | None = None,
    requested_by: str | None = None,
) -> tuple[Run, bool]:
    """Returns ``(run, created)``. ``created=False`` means an active run already existed."""
    existing = await active_for(s, subject_type, subject_id)
    if existing:
        return existing, False
    run = Run(
        id=new_id("run"),
        batch_id=batch_id,
        use_case=use_case,
        subject_type=subject_type,
        subject_id=subject_id,
        cycle_key=cycle_key,
        status=RunStatus.QUEUED.value,
        max_attempts=max_attempts,
        requested_by=requested_by,
    )
    try:
        async with s.begin_nested():
            s.add(run)
    except IntegrityError:
        existing = await active_for(s, subject_type, subject_id)
        if existing is None:
            raise
        return existing, False
    return run, True


async def claim_next(s: AsyncSession, worker_id: str) -> Run | None:
    now = utcnow()
    # Sessions start with BEGIN IMMEDIATE, so select-then-update is atomic. Checking first
    # keeps an idle poll read-only (no UPDATE, so the CSV store is not marked dirty).
    oldest = (
        await s.execute(
            select(Run.id)
            .where(Run.status == RunStatus.QUEUED)
            .order_by(Run.created_at, Run.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if oldest is None:
        return None
    stmt = (
        update(Run)
        .where(Run.id == oldest, Run.status == RunStatus.QUEUED)
        .values(
            status=RunStatus.RUNNING.value,
            claimed_by=worker_id,
            started_at=now,
            heartbeat_at=now,
            attempts=Run.attempts + 1,
        )
        .returning(Run.id)
    )
    run_id = (await s.execute(stmt)).scalar_one_or_none()
    if run_id is None:
        return None
    run = await s.get(Run, run_id, populate_existing=True)
    return run


async def heartbeat(s: AsyncSession, run_id: str, worker_id: str) -> bool:
    res = await s.execute(
        update(Run)
        .where(Run.id == run_id, Run.claimed_by == worker_id, Run.status == RunStatus.RUNNING)
        .values(heartbeat_at=utcnow())
    )
    return res.rowcount == 1


async def finish(
    s: AsyncSession,
    run_id: str,
    worker_id: str,
    *,
    status: RunStatus,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> bool:
    res = await s.execute(
        update(Run)
        .where(Run.id == run_id, Run.claimed_by == worker_id, Run.status == RunStatus.RUNNING)
        .values(
            status=status.value,
            result=result or {},
            error_code=error_code,
            error_message=(error_message or "")[:2000] or None,
            finished_at=utcnow(),
        )
    )
    return res.rowcount == 1


async def recover_stale(
    s: AsyncSession, *, instance_prefix: str, stale_before: datetime
) -> tuple[list[str], list[str]]:
    """Requeue (or fail, if out of attempts) runs whose worker is gone: claimed by a previous
    process instance, or silent past the heartbeat deadline. Returns (requeued, failed)."""
    q = select(Run).where(Run.status == RunStatus.RUNNING)
    requeued: list[str] = []
    failed: list[str] = []
    for run in (await s.execute(q)).scalars():
        foreign = not (run.claimed_by or "").startswith(instance_prefix)
        silent = run.heartbeat_at is None or run.heartbeat_at < stale_before
        if not (foreign or silent):
            continue
        if run.attempts < run.max_attempts:
            run.status = RunStatus.QUEUED.value
            run.claimed_by = None
            run.error_code = "worker_lost"
            run.error_message = "Worker stopped before finishing; requeued."
            requeued.append(run.id)
        else:
            run.status = RunStatus.FAILED.value
            run.error_code = "worker_lost"
            run.error_message = f"Worker lost {run.attempts} times; giving up."
            run.finished_at = utcnow()
            failed.append(run.id)
    return requeued, failed


async def reset_for_retry(s: AsyncSession, run_id: str) -> Run | None:
    """Failed run -> queued again (keeps id so audit/LLM history stays together)."""
    res = await s.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == RunStatus.FAILED)
        .values(
            status=RunStatus.QUEUED.value,
            error_code=None,
            error_message=None,
            claimed_by=None,
            finished_at=None,
            attempts=0,
            created_at=utcnow(),
        )
    )
    if res.rowcount != 1:
        return None
    return await s.get(Run, run_id, populate_existing=True)


async def list_(
    s: AsyncSession,
    *,
    status: str | None = None,
    batch_id: str | None = None,
    use_case: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Run], int]:
    q = select(Run)
    if status:
        q = q.where(Run.status == status)
    if use_case:
        q = q.where(Run.use_case == use_case)
    if batch_id:
        q = q.where(Run.batch_id == batch_id)
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        (
            await s.execute(
                q.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return rows, total


async def status_counts(s: AsyncSession, batch_id: str | None = None) -> dict[str, int]:
    q = select(Run.status, func.count()).group_by(Run.status)
    if batch_id:
        q = q.where(Run.batch_id == batch_id)
    return {status: n for status, n in (await s.execute(q)).all()}


def stale_cutoff(seconds: float) -> datetime:
    return utcnow() - timedelta(seconds=seconds)
