"""Display names for run/recommendation subjects (leads), resolved in bulk for list views."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.db.models import Lead


def _lead_ids(subjects: Iterable[tuple[str, str]]) -> set[str]:
    return {sid for kind, sid in subjects if kind == "lead"}


async def subject_names(s: AsyncSession, subjects: Iterable[tuple[str, str]]) -> dict[str, str]:
    """``{lead_id: "First Last"}`` for (subject_type, subject_id) pairs; unknown ids omitted."""
    ids = _lead_ids(subjects)
    if not ids:
        return {}
    rows = await s.execute(select(Lead.id, Lead.first_name, Lead.last_name).where(Lead.id.in_(ids)))
    return {lid: " ".join(filter(None, [first, last])) or "(no name)" for lid, first, last in rows}


async def subject_lines(s: AsyncSession, subjects: Iterable[tuple[str, str]]) -> dict[str, str]:
    """``{lead_id: product line}`` for (subject_type, subject_id) pairs."""
    ids = _lead_ids(subjects)
    if not ids:
        return {}
    rows = await s.execute(select(Lead.id, Lead.product_line).where(Lead.id.in_(ids)))
    return {i: ln for i, ln in rows if ln}
