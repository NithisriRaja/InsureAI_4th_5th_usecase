"""Regression tests for storage, intake and session fixes found in code review."""

from __future__ import annotations

from sqlalchemy import select

from insurance_poc.db.models import Recommendation, Session
from tests.integration.conftest import wait_run

PA_LEAD = {
    "external_ref": "WEB-PA-1",
    "first_name": "Omar",
    "last_name": "Haddad",
    "dob": "1988-06-15",
    "email": "omar.haddad@example.com",
    "phone": "+971 50 123 4567",
    "product_line": "personal_accident",
    "sum_insured": 500000,
    "declared": {"occupation_risk": "low", "dependents": 2, "pages_viewed": 6},
    "consent_marketing": True,
    "consent_email": True,
}


async def test_personal_accident_lead_is_not_blocked_by_its_own_catalogue_text(
    api, seeded_db
) -> None:
    """The PA description says "disability"; it must not trip the fairness scan."""
    body = (await api.post("/leads", json=PA_LEAD)).json()
    run = await wait_run(api, body["run"]["id"])
    assert run["status"] == "succeeded", run
    async with seeded_db.session() as s:
        rec = (
            await s.execute(
                select(Recommendation).where(Recommendation.subject_id == body["lead_id"])
            )
        ).scalar_one()
    assert rec.products and rec.products[0]["code"] == "PA_INDIVIDUAL"


async def test_declared_facts_with_wrong_types_are_rejected(api) -> None:
    for declared in (
        {"vehicle_value": "x"},  # crashed the CSV writer
        {"vehicle_year": "abc"},  # saved, then refused at the next start-up
        {"not_a_fact": 1},  # silently dropped on save
        {"smoker": "maybe"},
    ):
        r = await api.post("/leads", json={**PA_LEAD, "declared": declared})
        assert r.status_code == 422, (declared, r.text)
        assert r.json()["error"]["code"] == "validation_error"


async def test_numeric_strings_are_coerced(api) -> None:
    r = await api.post(
        "/leads",
        json={**PA_LEAD, "external_ref": "WEB-PA-2", "declared": {"dependents": "3"}},
    )
    assert r.status_code == 202, r.text


async def test_spreadsheet_formulas_are_rejected(api) -> None:
    for field in ("first_name", "notes", "city"):
        r = await api.post("/leads", json={**PA_LEAD, field: '=HYPERLINK("http://x")'})
        assert r.status_code == 422, field
    # A phone number may start with "+".
    r = await api.post("/leads", json={**PA_LEAD, "external_ref": "WEB-PA-3"})
    assert r.status_code == 202


async def test_role_change_ends_the_users_other_sessions(api, seeded_db) -> None:
    first = (await api.post("/sessions", json={"name": "Alice", "role": "sales"})).json()
    await api.post("/sessions", json={"name": "alice", "role": "admin"})
    r = await api.get("/sessions/me", headers={"X-Session-Id": first["session_id"]})
    assert r.status_code == 401
    async with seeded_db.session() as s:
        old = await s.get(Session, first["session_id"])
    assert old is not None and old.ended_at is not None


async def test_shallow_health_check(api) -> None:
    r = await api.get("/health")
    assert r.status_code == 200 and r.json()["db"] == "ok"
