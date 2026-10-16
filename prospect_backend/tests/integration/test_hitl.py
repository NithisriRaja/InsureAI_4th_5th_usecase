from __future__ import annotations

import asyncio

from insurance_poc.db.models import Lead
from tests.integration.conftest import wait_run


async def login(c, name: str, role: str) -> dict[str, str]:
    r = await c.post("/sessions", json={"name": name, "role": role})
    assert r.status_code == 201
    return {"X-Session-Id": r.json()["session_id"]}


async def _rec_for(api, lead_id: str) -> dict:
    run = await wait_run(api, (await api.post(f"/leads/{lead_id}/runs")).json()["id"])
    return (await api.get(f"/recommendations/{run['recommendation_id']}")).json()


async def test_hitl_end_to_end(api) -> None:
    rec = await _rec_for(api, "lead_l01")  # broker-owned motor lead -> sales queue
    assert rec["queue"] == "sales" and rec["action"] == "contact_and_quote"
    assert rec["llm_calls"] and rec["audit"] and rec["subject"]["name"] == "Daniel Okafor"

    url = f"/approvals/{rec['id']}"
    assert (await api.post(f"{url}/approve")).status_code == 401
    adviser = await login(api, "Omar", "adviser")
    assert (await api.post(f"{url}/approve", headers=adviser)).status_code == 403

    sales = await login(api, "Sam", "sales")
    bad = await api.post(f"{url}/edit", headers=sales, json={"edits": {"channel": "email"}})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "rule_violation"
    worse = await api.post(f"{url}/edit", headers=sales, json={"edits": {"action": "decline"}})
    assert worse.status_code == 422

    # Five reviewers click at once: exactly one wins.
    body = {"expected_version": rec["version"], "edits": {"action": "nurture"}}
    results = await asyncio.gather(
        *(api.post(f"{url}/edit", headers=sales, json=body) for _ in range(5))
    )
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409, 409]

    done = (await api.get(f"/recommendations/{rec['id']}")).json()
    assert done["status"] == "approved_with_edits" and done["action"] == "nurture"
    assert done["approval"]["original"]["action"] == "contact_and_quote"
    assert (await api.get("/leads/lead_l01")).json()["status"] == "decided"


async def test_reject_needs_a_reason(api) -> None:
    rec = await _rec_for(api, "lead_l02")
    sales = await login(api, "Sam", "sales")
    url = f"/approvals/{rec['id']}/reject"
    assert (await api.post(url, headers=sales, json={})).status_code == 422
    r = await api.post(url, headers=sales, json={"reason": "Customer already insured"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"


async def test_stale_after_consent_withdrawn(api) -> None:
    rec = await _rec_for(api, "lead_l02")
    async with api.app.state.db.session() as s:  # type: ignore[attr-defined]
        (await s.get(Lead, "lead_l02")).consent_marketing = False
    sales = await login(api, "Sam", "sales")
    r = await api.post(f"/approvals/{rec['id']}/approve", headers=sales)
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale"
    assert (await api.get(f"/recommendations/{rec['id']}")).json()["status"] == "superseded"


async def test_session_survives_app_restart(seeded_db, llm_switch) -> None:
    from tests.integration.conftest import _client

    async for c in _client(seeded_db, llm_switch, start_runner=False):
        h = await login(c, "Una", "underwriter")
    async for c in _client(seeded_db, llm_switch, start_runner=False):
        me = await c.get("/sessions/me", headers=h)
        assert me.status_code == 200 and me.json()["role"] == "underwriter"
        assert (await c.get("/sessions/me", headers={"X-Session-Id": "bogus"})).status_code == 401


async def test_acquisition_approve(api) -> None:
    run = await wait_run(api, (await api.post("/leads/lead_l01/runs")).json()["id"])
    h = await login(api, "Sam", "sales")
    r = await api.post(
        f"/approvals/{run['recommendation_id']}/approve", headers=h, json={"expected_version": 1}
    )
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert (await api.get("/leads/lead_l01")).json()["status"] == "decided"
