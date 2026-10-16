from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, StatementError

from insurance_poc.db.models import Lead, Product, Run
from insurance_poc.db.repositories import leads as leads_repo
from insurance_poc.db.session import Database
from insurance_poc.utils.clock import today, utcnow

LEAD = dict(
    external_ref=None,
    first_name="Jo",
    last_name="Bloggs",
    email="Jo.Bloggs@Example.com",
    phone="+1 (555) 000-1111",
    product_line="motor",
)


async def test_clock_uses_as_of_date() -> None:
    assert today().isoformat() == "2026-10-13"


async def test_demo_data_counts(seeded_db: Database) -> None:
    async with seeded_db.session() as s:
        assert (await s.execute(select(func.count()).select_from(Lead))).scalar_one() == 18
        assert (await s.execute(select(func.count()).select_from(Product))).scalar_one() == 15
        cross_sell = await s.get(Lead, "lead_l13")
        assert cross_sell is not None and cross_sell.existing_customer_id == "cust_p03"


async def test_duplicate_lead_returns_existing(db: Database) -> None:
    async with db.session() as s:
        first, created1 = await leads_repo.create_or_get(s, dict(LEAD))
    # Same person, differently formatted email/phone -> duplicate.
    async with db.session() as s:
        second, created2 = await leads_repo.create_or_get(
            s, {**LEAD, "email": "jo.bloggs@example.com ", "phone": "15550001111"}
        )
    assert created1 and not created2
    assert second.id == first.id


async def test_same_person_other_line_is_not_duplicate(db: Database) -> None:
    async with db.session() as s:
        _, c1 = await leads_repo.create_or_get(s, dict(LEAD))
        _, c2 = await leads_repo.create_or_get(s, {**LEAD, "product_line": "home"})
    assert c1 and c2


async def test_concurrent_duplicate_lead_creates_one(db: Database) -> None:
    async def ingest() -> tuple[str, bool]:
        async with db.session() as s:
            lead, created = await leads_repo.create_or_get(s, dict(LEAD))
            return lead.id, created

    results = await asyncio.gather(*(ingest() for _ in range(5)))
    assert sum(created for _, created in results) == 1
    assert len({lead_id for lead_id, _ in results}) == 1


async def test_only_one_active_run_per_subject(db: Database) -> None:
    def run(run_id: str, status: str = "queued") -> Run:
        return Run(
            id=run_id,
            use_case="acquisition",
            subject_type="lead",
            subject_id="lead_x",
            cycle_key="lead_x",
            status=status,
        )

    async with db.session() as s:
        s.add(run("run_1"))
    with pytest.raises(IntegrityError):
        async with db.session() as s:
            s.add(run("run_2"))
    # Finished runs don't block a new one.
    async with db.session() as s:
        r1 = await s.get(Run, "run_1")
        assert r1 is not None
        r1.status = "succeeded"
    async with db.session() as s:
        s.add(run("run_3"))


async def test_timestamps_roundtrip_as_utc(db: Database) -> None:
    async with db.session() as s:
        s.add(
            Run(
                id="run_t",
                use_case="acquisition",
                subject_type="lead",
                subject_id="l",
                cycle_key="l",
            )
        )
    async with db.session() as s:
        r = await s.get(Run, "run_t")
        assert r is not None and r.created_at.tzinfo is not None


async def test_naive_datetime_rejected(db: Database) -> None:
    with pytest.raises(StatementError):
        async with db.session() as s:
            s.add(
                Run(
                    id="run_n",
                    use_case="acquisition",
                    subject_type="lead",
                    subject_id="l",
                    cycle_key="l",
                    started_at=datetime(2026, 1, 1),
                )
            )
            await s.flush()
    assert utcnow().tzinfo is not None
