from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

from insurance_poc import csv_data
from insurance_poc.db.models import Customer, Lead, Product
from tests.conftest import DEMO_CSV
from tests.fixtures.fake_llm import fake_llm
from tests.unit.test_agents import run_subject


def _copy_demo(tmp_path: Path) -> Path:
    folder = tmp_path / "csv"
    shutil.copytree(DEMO_CSV, folder)
    return folder


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


async def _load(db, folder: Path) -> dict[str, int]:
    async with db.session() as s:
        return await csv_data.load(s, folder)


async def test_demo_csv_loads_and_writes_back_unchanged(db, tmp_path) -> None:
    folder = _copy_demo(tmp_path)
    assert await _load(db, folder) == {"products": 15, "customers": 2, "leads": 18}
    async with db.session() as s:
        leads = (await s.execute(select(Lead).order_by(Lead.created_at, Lead.id))).scalars().all()
        products = (await s.execute(select(Product).order_by(Product.code))).scalars().all()
        customers = (await s.execute(select(Customer).order_by(Customer.id))).scalars().all()
    # Every value survives a read + write: the written rows equal the input rows.
    for name, rows, fn in (
        ("leads.csv", leads, csv_data.lead_row),
        ("products.csv", products, csv_data.product_row),
        ("customers.csv", customers, csv_data.customer_row),
    ):
        original = {r[next(iter(r))]: r for r in _rows(folder / name)}
        written = {r[next(iter(r))]: r for r in map(fn, rows)}
        assert written == original, name
    l13 = next(x for x in leads if x.id == "lead_l13")
    assert l13.existing_customer_id == "cust_p03"
    assert l13.declared["annual_income"] == 40_000_000  # whole units in the file -> minor
    l02 = next(x for x in leads if x.id == "lead_l02")
    assert l02.declared["pre_existing_conditions"] == []  # "none" = declared empty


async def test_problems_are_reported_by_row_and_column(db, tmp_path) -> None:
    folder = _copy_demo(tmp_path)
    rows = _rows(folder / "leads.csv")
    rows[0]["smoker"] = "maybe"
    rows[1]["existing_customer_id"] = "cust_nope"
    rows[2]["lead_id"] = rows[3]["lead_id"]
    _write(folder / "leads.csv", rows)
    with pytest.raises(csv_data.CsvError) as e:
        await _load(db, folder)
    text = str(e.value)
    assert "leads.csv row 2, column smoker" in text
    assert "row 3: existing_customer_id 'cust_nope'" in text
    assert "rows 4 and 5: duplicate lead_id" in text
    async with db.session() as s:  # nothing half-loaded
        assert (await s.execute(select(Lead))).first() is None


async def test_agent_runs_on_a_lead_added_in_the_csv(db, tmp_path) -> None:
    folder = _copy_demo(tmp_path)
    rows = _rows(folder / "leads.csv")
    new = {k: "" for k in rows[0]}
    new.update(
        first_name="Lina",
        last_name="Haddad",
        dob="1990-03-01",
        email="lina@example.com",
        product_line="motor",
        sum_insured="40000",
        source="web",
        consent_marketing="true",
        consent_email="true",
        vehicle_year="2022",
        driving_years="8",
        requested_callback="yes",
    )
    _write(folder / "leads.csv", [*rows, new])
    await _load(db, folder)
    async with db.session() as s:
        lead = (await s.execute(select(Lead).where(Lead.first_name == "Lina"))).scalar_one()
    assert lead.id.startswith("lead_") and lead.sum_insured_requested == 4_000_000
    assert lead.status == "new"
    llm, _ = fake_llm()
    _, rec = await run_subject(db, llm, "acquisition", lead.id)
    assert rec.action == "contact_and_quote" and rec.products
