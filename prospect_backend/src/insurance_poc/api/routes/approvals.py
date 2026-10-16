"""Approve / reject / edit. Actor comes from the X-Session-Id session, never the body."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from insurance_poc.api.deps import get_database
from insurance_poc.api.errors import AppError
from insurance_poc.api.session_auth import Actor, require_actor
from insurance_poc.db.session import Database
from insurance_poc.enums import Decision
from insurance_poc.services import approvals as svc

router = APIRouter(prefix="/approvals", tags=["approvals"])


class DecisionIn(BaseModel):
    expected_version: int | None = Field(
        default=None, description="Version the reviewer saw; mismatch -> 409."
    )
    reason: str | None = Field(default=None, max_length=1000)


class EditIn(DecisionIn):
    edits: dict[str, Any] = Field(
        description='Only "action": contact_and_quote | nurture | refer_to_underwriter.'
    )


class DecisionOut(BaseModel):
    recommendation_id: str
    status: str
    version: int
    approval_id: str


async def _decide(
    db: Database,
    rec_id: str,
    actor: Actor,
    decision: Decision,
    body: DecisionIn,
    edits: dict[str, Any] | None = None,
) -> DecisionOut:
    try:
        r = await svc.decide(
            db,
            rec_id,
            actor,
            decision,
            expected_version=body.expected_version,
            reason=body.reason,
            edits=edits,
        )
    except svc.DecisionError as e:
        raise AppError(e.status, e.code, e.message, e.details) from e
    return DecisionOut(
        recommendation_id=r.recommendation.id,
        status=r.recommendation.status,
        version=r.recommendation.version,
        approval_id=r.approval.id,
    )


@router.post("/{rec_id}/approve", response_model=DecisionOut)
async def approve(
    rec_id: str,
    body: DecisionIn | None = None,
    actor: Actor = Depends(require_actor),
    db: Database = Depends(get_database),
) -> DecisionOut:
    return await _decide(db, rec_id, actor, Decision.APPROVED, body or DecisionIn())


@router.post("/{rec_id}/reject", response_model=DecisionOut)
async def reject(
    rec_id: str,
    body: DecisionIn,
    actor: Actor = Depends(require_actor),
    db: Database = Depends(get_database),
) -> DecisionOut:
    return await _decide(db, rec_id, actor, Decision.REJECTED, body)


@router.post("/{rec_id}/edit", response_model=DecisionOut)
async def edit(
    rec_id: str,
    body: EditIn,
    actor: Actor = Depends(require_actor),
    db: Database = Depends(get_database),
) -> DecisionOut:
    return await _decide(db, rec_id, actor, Decision.APPROVED_WITH_EDITS, body, body.edits)
