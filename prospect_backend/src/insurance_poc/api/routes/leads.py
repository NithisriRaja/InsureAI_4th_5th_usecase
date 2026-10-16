"""Lead intake (async: returns run handles) and the acquisition worklist.

Write routes open their own unit of work so the commit is done before the runner is woken.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.api.deps import db_session, get_database, get_runner
from insurance_poc.api.errors import not_found
from insurance_poc.api.schemas.common import BatchOut, Page, RecBrief, RunBrief, RunOut
from insurance_poc.api.schemas.leads import (
    LeadBulkIn,
    LeadBulkResult,
    LeadDetail,
    LeadIn,
    LeadIngestResult,
    LeadOut,
)
from insurance_poc.api.session_auth import optional_actor
from insurance_poc.db.models import Lead
from insurance_poc.db.repositories import leads as leads_repo
from insurance_poc.db.repositories import recommendations as recs_repo
from insurance_poc.db.repositories import runs as runs_repo
from insurance_poc.db.session import Database
from insurance_poc.services import intake
from insurance_poc.services.rules.routing import resolve_lead_owner
from insurance_poc.services.runner import Runner

router = APIRouter(prefix="/leads", tags=["leads"])


async def _lead_out(s: AsyncSession, leads: list[Lead]) -> list[LeadOut]:
    recs = await recs_repo.latest_by_subject(s, "lead", [x.id for x in leads])
    out = []
    for lead in leads:
        run = await runs_repo.latest_for(s, "lead", lead.id)
        out.append(
            LeadOut(
                id=lead.id,
                external_ref=lead.external_ref,
                name=" ".join(filter(None, [lead.first_name, lead.last_name])) or "(no name)",
                product_line=lead.product_line,
                sum_insured=lead.sum_insured_requested // 100
                if lead.sum_insured_requested is not None
                else None,
                source=lead.source,
                channel_owner=resolve_lead_owner(
                    lead.product_line, lead.source, lead.channel_owner
                ),
                intermediary=lead.intermediary,
                status=lead.status,
                existing_customer=lead.existing_customer_id is not None,
                consent_marketing=lead.consent_marketing,
                created_at=lead.created_at,
                latest_recommendation=RecBrief.of(recs.get(lead.id)),
                latest_run=RunBrief.of(run),
            )
        )
    return out


@router.post(
    "",
    response_model=LeadIngestResult,
    status_code=202,
    responses={200: {"description": "Duplicate lead: existing lead returned"}},
)
async def ingest_lead(
    body: LeadIn,
    response: Response,
    db: Database = Depends(get_database),
    runner: Runner | None = Depends(get_runner),
    actor: str | None = Depends(optional_actor),
) -> LeadIngestResult:
    async with db.session() as s:
        lead, created, run = await intake.ingest_lead(s, body.to_model_fields(), requested_by=actor)
        result = LeadIngestResult(lead_id=lead.id, created=created, run=RunBrief.of(run))
    if not created:
        response.status_code = 200
    elif runner:
        runner.notify()
    return result


@router.post("/bulk", response_model=LeadBulkResult, status_code=202)
async def ingest_bulk(
    body: LeadBulkIn,
    db: Database = Depends(get_database),
    runner: Runner | None = Depends(get_runner),
    actor: str | None = Depends(optional_actor),
) -> LeadBulkResult:
    async with db.session() as s:
        batch = await intake.create_lead_batch(s, actor)
        results = []
        for item in body.leads:
            lead, created, run = await intake.ingest_lead(
                s, item.to_model_fields(), batch_id=batch.id, requested_by=actor
            )
            results.append(LeadIngestResult(lead_id=lead.id, created=created, run=RunBrief.of(run)))
    if runner:
        runner.notify()
    return LeadBulkResult(batch_id=batch.id, results=results)


@router.post("/runs", response_model=BatchOut, status_code=202)
async def run_all(
    scope: Literal["unchecked", "all"] = Query(
        "unchecked",
        description="unchecked: never analysed or failed; all: also re-check open suggestions",
    ),
    product_line: str | None = None,
    db: Database = Depends(get_database),
    runner: Runner | None = Depends(get_runner),
    actor: str | None = Depends(optional_actor),
) -> BatchOut:
    """Run the AI on every matching prospect. Decided or converted prospects are skipped."""
    async with db.session() as s:
        batch, queued, busy = await intake.run_all_leads(
            s, scope=scope, product_line=product_line, requested_by=actor
        )
        out = BatchOut.of(batch, {"queued": len(queued)} if queued else {}, [r.id for r in queued])
        out.params = {**out.params, "already_running": busy}
    if runner and queued:
        runner.notify()
    return out


@router.get("", response_model=Page[LeadOut])
async def list_leads(
    status: str | None = None,
    product_line: str | None = None,
    source: str | None = None,
    q: str | None = Query(None, max_length=100, description="Name, email or reference contains"),
    sort: Literal["newest", "oldest", "name", "cover_desc"] = "newest",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    s: AsyncSession = Depends(db_session),
) -> Page[LeadOut]:
    rows, total = await leads_repo.list_(
        s,
        status=status,
        product_line=product_line,
        source=source,
        search=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return Page(items=await _lead_out(s, list(rows)), total=total, limit=limit, offset=offset)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: str, s: AsyncSession = Depends(db_session)) -> LeadDetail:
    lead = await leads_repo.get(s, lead_id)
    if lead is None:
        raise not_found("lead", lead_id)
    base = (await _lead_out(s, [lead]))[0]
    return LeadDetail(
        **base.model_dump(),
        first_name=lead.first_name,
        last_name=lead.last_name,
        dob=lead.dob,
        email=lead.email,
        phone=lead.phone,
        city=lead.city,
        declared=lead.declared or {},
        notes=lead.notes,
        documents_provided=list(lead.documents_provided or []),
        consent_profiling=lead.consent_profiling,
        consent_email=lead.consent_email,
        consent_sms=lead.consent_sms,
    )


@router.post(
    "/{lead_id}/runs",
    response_model=RunOut,
    status_code=202,
    responses={200: {"description": "A run is already active; returned as-is"}},
)
async def rerun_lead(
    lead_id: str,
    response: Response,
    db: Database = Depends(get_database),
    runner: Runner | None = Depends(get_runner),
    actor: str | None = Depends(optional_actor),
) -> RunOut:
    async with db.session() as s:
        if await leads_repo.get(s, lead_id) is None:
            raise not_found("lead", lead_id)
        run, created = await intake.enqueue_lead(s, lead_id, requested_by=actor)
        out = RunOut.of(run)
    if not created:
        response.status_code = 200
    elif runner:
        runner.notify()
    return out
