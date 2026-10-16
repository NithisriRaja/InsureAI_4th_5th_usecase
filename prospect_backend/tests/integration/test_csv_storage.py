"""CSV storage: the CSV files are the only data on disk and survive restarts."""

from __future__ import annotations

import csv
import os
import shutil
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from insurance_poc.config import get_settings
from insurance_poc.db import csv_store
from insurance_poc.db.base import Base
from insurance_poc.db.session import Database
from insurance_poc.main import create_app
from tests.conftest import DEMO_CSV
from tests.fixtures.fake_llm import fake_llm
from tests.integration.conftest import wait_run
from tests.unit.test_agents import run_subject


def _leftovers(work: Path, folder: Path) -> tuple[bool, list[Path]]:
    return os.path.exists(work), list(folder.rglob("*.db*"))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


async def _table_rows(db: Database, name: str) -> list[dict]:
    table = Base.metadata.tables[name]
    async with db.session() as s:
        res = await s.execute(select(table).order_by(*table.primary_key.columns))
        return [dict(r._mapping) for r in res.fetchall()]


async def test_every_table_round_trips(seeded_db, tmp_path) -> None:
    llm, _ = fake_llm()
    await run_subject(seeded_db, llm, "acquisition", "lead_l01")
    await run_subject(seeded_db, llm, "acquisition", "lead_l13")
    await csv_store.dump_all(seeded_db, tmp_path)
    assert (tmp_path / "system" / "recommendations.csv").exists()
    assert (tmp_path / "results" / "ai_results.csv").exists()

    fresh = Database(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        await csv_store.load_all(fresh, tmp_path)
        for table in csv_store._tables():
            assert await _table_rows(fresh, table.name) == await _table_rows(
                seeded_db, table.name
            ), table.name
        before = {r["id"]: r for r in await _table_rows(seeded_db, "leads")}
        after = {r["id"]: r for r in await _table_rows(fresh, "leads")}
        for lead_id, row in before.items():
            for k in ("status", "declared", "dedupe_hash", "existing_customer_id", "created_at"):
                assert after[lead_id][k] == row[k], (lead_id, k)
        # A second dump of the reloaded data changes nothing.
        assert await csv_store.dump_all(fresh, tmp_path) == []
    finally:
        await fresh.dispose()


@pytest.fixture
def csv_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    folder = tmp_path / "data_csv"
    shutil.copytree(DEMO_CSV, folder)
    monkeypatch.setenv("DATA_DIR", str(folder))
    monkeypatch.setenv("CSV_FLUSH_INTERVAL_S", "0.05")
    get_settings.cache_clear()
    return folder


async def _serve(app):
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c, app


async def test_app_reads_and_writes_only_csv(csv_mode) -> None:
    llm, _ = fake_llm()
    async for c, app in _serve(create_app(llm_factory=lambda: llm)):
        assert (await c.get("/health")).json()["storage"]["mode"] == "csv"
        work = Path(app.state.csv_store.db.url.split("///", 1)[1])
        assert csv_mode not in work.parents  # working copy is outside the data folder
        run = await wait_run(c, (await c.post("/leads/lead_l01/runs")).json()["id"])
        rec_id = run["recommendation_id"]
    assert _leftovers(work, csv_mode) == (False, [])  # copy dropped; no .db in the folder

    leads = {r["lead_id"]: r for r in _rows(csv_mode / "leads.csv")}
    assert leads["lead_l01"]["status"] == "recommended"
    recs = _rows(csv_mode / "system" / "recommendations.csv")
    assert [r["id"] for r in recs] == [rec_id]
    result = {r["lead_id"]: r for r in _rows(csv_mode / "results" / "ai_results.csv")}
    assert result["lead_l01"]["best_product"] and result["lead_l01"]["next_steps"]

    # Restart: everything comes back from the CSVs.
    async for c, _ in _serve(create_app(llm_factory=lambda: llm)):
        assert (await c.get(f"/recommendations/{rec_id}")).json()["action"] == "contact_and_quote"
        assert (await c.get("/leads/lead_l01")).json()["status"] == "recommended"


async def test_new_lead_from_the_api_lands_in_leads_csv(csv_mode) -> None:
    llm, _ = fake_llm()
    body = {
        "first_name": "Lina",
        "last_name": "Haddad",
        "dob": "1990-03-01",
        "email": "lina@example.com",
        "product_line": "motor",
        "sum_insured": 40000,
        "declared": {"vehicle_year": 2022, "driving_years": 8},
        "consent_marketing": True,
        "consent_email": True,
    }
    async for c, _ in _serve(create_app(llm_factory=lambda: llm)):
        r = await c.post("/leads", json=body)
        await wait_run(c, r.json()["run"]["id"])
    row = next(x for x in _rows(csv_mode / "leads.csv") if x["first_name"] == "Lina")
    assert row["sum_insured"] == "40000" and row["vehicle_year"] == "2022"


async def test_bad_csv_stops_start_up(csv_mode) -> None:
    rows = _rows(csv_mode / "leads.csv")
    rows[0]["consent_email"] = "perhaps"
    with (csv_mode / "leads.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(SystemExit):
        async for _ in _serve(create_app(llm_factory=lambda: fake_llm()[0])):
            pass


async def test_locked_file_is_retried(csv_mode, monkeypatch) -> None:
    store = csv_store.CsvStore(csv_mode, interval_s=0.01)
    await store.open()
    try:
        real = csv_store.os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError(13, "locked", str(dst))
            return real(src, dst)

        monkeypatch.setattr(csv_store.os, "replace", flaky)
        async with store.db.session() as s:
            from insurance_poc.db.models import Lead

            (await s.get(Lead, "lead_l03")).status = "decided"
        await store.flush()  # first write hits the lock
        assert store._dirty.is_set()
        await store.flush()
        assert {r["lead_id"]: r for r in _rows(csv_mode / "leads.csv")}["lead_l03"][
            "status"
        ] == "decided"
    finally:
        await store.close()


async def test_reset_keeps_inputs_and_forgets_ai_work(csv_mode) -> None:
    llm, _ = fake_llm()
    async for c, _ in _serve(create_app(llm_factory=lambda: llm)):
        await wait_run(c, (await c.post("/leads/lead_l01/runs")).json()["id"])
    assert _rows(csv_mode / "system" / "recommendations.csv")
    removed = csv_store.reset_state(csv_mode)
    assert removed and not (csv_mode / "system" / "recommendations.csv").exists()
    leads = _rows(csv_mode / "leads.csv")
    assert len(leads) == 18 and {r["status"] for r in leads} == {"new"}
    async for c, _ in _serve(create_app(llm_factory=lambda: llm)):
        assert (await c.get("/recommendations", params={"status": ""})).json()["total"] == 0
