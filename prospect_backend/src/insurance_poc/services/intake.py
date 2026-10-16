"""Trigger logic shared by API routes and demo scripts: lead intake, re-runs and run-all."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.agents.graph import cycle_key_for
from insurance_poc.config import get_settings
from insurance_poc.db.models import Batch, Lead, Run
from insurance_poc.db.repositories import audit as audit_repo
from insurance_poc.db.repositories import leads as leads_repo
from insurance_poc.db.repositories import runs as runs_repo
from insurance_poc.enums import BatchKind, LeadStatus, SubjectType, UseCase
from insurance_poc.utils.ids import new_id


async def enqueue_lead(
    s: AsyncSession,
    lead_id: str,
    *,
    batch_id: str | None = None,
    requested_by: str | None = None,
) -> tuple[Run, bool]:
    run, created = await runs_repo.enqueue(
        s,
        use_case=UseCase.ACQUISITION,
        subject_type=SubjectType.LEAD,
        subject_id=lead_id,
        cycle_key=cycle_key_for(UseCase.ACQUISITION, lead_id),
        max_attempts=get_settings().run_max_attempts,
        batch_id=batch_id,
        requested_by=requested_by,
    )
    if created:
        audit_repo.add_event(
            s,
            event_type="run.queued",
            run_id=run.id,
            subject_type="lead",
            subject_id=lead_id,
            actor=requested_by or "system",
        )
    return run, created


async def ingest_lead(
    s: AsyncSession,
    fields: dict[str, Any],
    *,
    batch_id: str | None = None,
    requested_by: str | None = None,
) -> tuple[Lead, bool, Run | None]:
    """Create the lead (or find its duplicate) and queue an acquisition run for new leads.

    Duplicates are not re-run automatically; the caller can trigger a re-run explicitly.
    """
    lead, created = await leads_repo.create_or_get(s, fields)
    if not created:
        return lead, False, await runs_repo.latest_for(s, SubjectType.LEAD, lead.id)
    audit_repo.add_event(
        s,
        event_type="lead.ingested",
        subject_type="lead",
        subject_id=lead.id,
        actor=requested_by or "system",
        payload={"external_ref": lead.external_ref, "source": lead.source},
    )
    run, _ = await enqueue_lead(s, lead.id, batch_id=batch_id, requested_by=requested_by)
    return lead, True, run


async def create_lead_batch(s: AsyncSession, requested_by: str | None) -> Batch:
    batch = Batch(
        id=new_id("bat"), kind=BatchKind.LEAD_BULK.value, params={}, requested_by=requested_by
    )
    s.add(batch)
    await s.flush()
    return batch


# "unchecked": never analysed or the last analysis failed. "all": also re-check prospects
# with an open (undecided) suggestion. Decided / converted prospects are never re-run.
RUN_ALL_STATUSES = {
    "unchecked": (LeadStatus.NEW, LeadStatus.FAILED),
    "all": (LeadStatus.NEW, LeadStatus.FAILED, LeadStatus.RECOMMENDED),
}


async def run_all_leads(
    s: AsyncSession,
    *,
    scope: str = "unchecked",
    product_line: str | None = None,
    requested_by: str | None = None,
) -> tuple[Batch, list[Run], int]:
    """Queue an acquisition run for every matching prospect. Returns (batch, queued, already
    running)."""
    q = select(Lead.id).where(Lead.status.in_([x.value for x in RUN_ALL_STATUSES[scope]]))
    if product_line:
        q = q.where(Lead.product_line == product_line)
    lead_ids = list((await s.execute(q.order_by(Lead.created_at))).scalars())
    batch = Batch(
        id=new_id("bat"),
        kind=BatchKind.LEAD_RUN_ALL.value,
        params={"scope": scope, "product_line": product_line, "matched": len(lead_ids)},
        requested_by=requested_by,
    )
    s.add(batch)
    await s.flush()
    queued: list[Run] = []
    busy = 0
    for lead_id in lead_ids:
        run, created = await enqueue_lead(s, lead_id, batch_id=batch.id, requested_by=requested_by)
        if created:
            queued.append(run)
        else:
            busy += 1
    audit_repo.add_event(
        s,
        event_type="leads.run_all",
        actor=requested_by or "system",
        payload={"batch_id": batch.id, "scope": scope, "queued": len(queued), "busy": busy},
    )
    return batch, queued, busy
