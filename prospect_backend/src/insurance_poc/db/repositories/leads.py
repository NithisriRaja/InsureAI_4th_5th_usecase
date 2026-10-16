from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.db.models import Customer, Lead
from insurance_poc.utils.ids import new_id
from insurance_poc.utils.normalize import lead_dedupe_hash, norm_email, norm_phone


async def get(s: AsyncSession, lead_id: str) -> Lead | None:
    return await s.get(Lead, lead_id)


async def find_duplicate(
    s: AsyncSession, *, external_ref: str | None, dedupe_hash: str
) -> Lead | None:
    conds = [Lead.dedupe_hash == dedupe_hash]
    if external_ref:
        conds.append(Lead.external_ref == external_ref)
    return (await s.execute(select(Lead).where(or_(*conds)).limit(1))).scalar_one_or_none()


async def create_or_get(s: AsyncSession, data: dict[str, Any]) -> tuple[Lead, bool]:
    """Insert a lead unless a duplicate exists. Returns ``(lead, created)``.

    Race-safe: the unique constraints on ``external_ref`` / ``dedupe_hash`` are the real guard;
    a concurrent insert that loses raises IntegrityError and we return the winner instead.
    """
    dedupe = lead_dedupe_hash(
        product_line=data.get("product_line"),
        email=data.get("email"),
        phone=data.get("phone"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        dob=data.get("dob"),
    )
    existing = await find_duplicate(s, external_ref=data.get("external_ref"), dedupe_hash=dedupe)
    if existing:
        return existing, False

    lead = Lead(id=new_id("lead"), dedupe_hash=dedupe, **data)
    lead.existing_customer_id = await match_customer_id(s, lead.email, lead.phone)
    try:
        async with s.begin_nested():
            s.add(lead)
    except IntegrityError:
        existing = await find_duplicate(
            s, external_ref=data.get("external_ref"), dedupe_hash=dedupe
        )
        if existing is None:
            raise
        return existing, False
    return lead, True


async def match_customer_id(s: AsyncSession, email: str | None, phone: str | None) -> str | None:
    e, p = norm_email(email), norm_phone(phone)
    conds = []
    if e:
        conds.append(func.lower(Customer.email) == e)
    if p:
        conds.append(Customer.phone == p)
    if not conds:
        return None
    row = (await s.execute(select(Customer.id).where(or_(*conds)).limit(1))).scalar_one_or_none()
    return row


LEAD_SORTS = {
    "newest": (Lead.created_at.desc(), Lead.id),
    "oldest": (Lead.created_at, Lead.id),
    "name": (func.lower(Lead.first_name), func.lower(Lead.last_name), Lead.id),
    "cover_desc": (Lead.sum_insured_requested.desc().nulls_last(), Lead.id),
}


async def list_(
    s: AsyncSession,
    *,
    status: str | None = None,
    product_line: str | None = None,
    source: str | None = None,
    search: str | None = None,
    sort: str = "newest",
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Lead], int]:
    q = select(Lead)
    if status:
        q = q.where(Lead.status == status)
    if product_line:
        q = q.where(Lead.product_line == product_line)
    if source:
        q = q.where(Lead.source == source)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        full_name = func.lower(
            func.coalesce(Lead.first_name, "") + " " + func.coalesce(Lead.last_name, "")
        )
        q = q.where(
            or_(
                full_name.like(term),
                func.lower(func.coalesce(Lead.email, "")).like(term),
                func.lower(func.coalesce(Lead.external_ref, "")).like(term),
                Lead.id == search.strip(),
            )
        )
    total = (await s.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    order = LEAD_SORTS.get(sort, LEAD_SORTS["newest"])
    rows = (await s.execute(q.order_by(*order).limit(limit).offset(offset))).scalars().all()
    return rows, total


async def set_status(s: AsyncSession, lead_id: str, status: str) -> None:
    lead = await s.get(Lead, lead_id)
    if lead:
        lead.status = status
