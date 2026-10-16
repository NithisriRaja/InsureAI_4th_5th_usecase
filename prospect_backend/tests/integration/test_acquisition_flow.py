from __future__ import annotations

import asyncio

from sqlalchemy import select

from insurance_poc.db.models import Lead, Recommendation, Run
from insurance_poc.services.llm.types import ProviderError
from tests.integration.conftest import wait_run

NEW_LEAD = {
    "external_ref": "WEB-9001",
    "first_name": "Maya",
    "last_name": "Singh",
    "dob": "1990-04-02",
    "email": "maya.singh@example.com",
    "phone": "+1 555 7777",
    "product_line": "motor",
    "sum_insured": 20000,
    "declared": {
        "vehicle_year": 2022,
        "driving_years": 10,
        "prior_claims_3y": 0,
        "vehicle_value": 2000000,
        "requested_callback": True,
        "pages_viewed": 9,
    },
    "consent_marketing": True,
    "consent_email": True,
}


async def test_ingest_runs_async_to_pending_recommendation(api) -> None:
    r = await api.post("/leads", json=NEW_LEAD)
    assert r.status_code == 202
    body = r.json()
    assert body["created"] and body["run"]["status"] == "queued"
    run = await wait_run(api, body["run"]["id"])
    assert run["status"] == "succeeded" and run["recommendation_id"]

    lead = (await api.get(f"/leads/{body['lead_id']}")).json()
    assert lead["status"] == "recommended"
    assert lead["sum_insured"] == 20000
    assert lead["latest_recommendation"]["action"] == "contact_and_quote"
    assert lead["latest_recommendation"]["status"] == "pending_approval"


async def test_duplicate_ingest_returns_existing(api) -> None:
    first = (await api.post("/leads", json=NEW_LEAD)).json()
    dup = await api.post(
        "/leads", json={**NEW_LEAD, "external_ref": None, "email": "MAYA.SINGH@example.com"}
    )
    assert dup.status_code == 200
    assert dup.json()["lead_id"] == first["lead_id"] and dup.json()["created"] is False


async def test_concurrent_identical_ingests_create_one_lead_and_run(api_queue_only) -> None:
    results = await asyncio.gather(
        *(api_queue_only.post("/leads", json=NEW_LEAD) for _ in range(6))
    )
    created = [r.json() for r in results if r.json()["created"]]
    assert len(created) == 1
    assert {r.json()["lead_id"] for r in results} == {created[0]["lead_id"]}
    runs = (await api_queue_only.get("/runs", params={"status": "queued"})).json()
    assert runs["total"] == 1


async def test_rerun_while_active_returns_same_run(api_queue_only) -> None:
    first = await api_queue_only.post("/leads/lead_l01/runs")
    second = await api_queue_only.post("/leads/lead_l01/runs")
    assert first.status_code == 202 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


async def test_concurrent_reruns_one_active_run(api_queue_only) -> None:
    results = await asyncio.gather(*(api_queue_only.post("/leads/lead_l02/runs") for _ in range(5)))
    assert len({r.json()["id"] for r in results}) == 1
    assert sorted(r.status_code for r in results) == [200, 200, 200, 200, 202]


async def test_llm_outage_fails_run_then_retry_succeeds(api, llm_switch) -> None:
    def down(purpose, messages):
        raise ProviderError("HTTP 503", status=503, retryable=True)

    llm_switch.responder = down
    run_id = (await api.post("/leads/lead_l01/runs")).json()["id"]
    run = await wait_run(api, run_id)
    assert run["status"] == "failed" and run["error_code"] == "llm_unavailable"
    assert (await api.get("/leads/lead_l01")).json()["status"] == "failed"

    from tests.fixtures.fake_llm import smart_responder

    llm_switch.responder = smart_responder
    r = await api.post(f"/runs/{run_id}/retry")
    assert r.status_code == 202
    run = await wait_run(api, run_id)
    assert run["status"] == "succeeded" and run["recommendation_id"]


async def test_retry_only_failed_runs(api) -> None:
    run_id = (await api.post("/leads/lead_l03/runs")).json()["id"]
    await wait_run(api, run_id)
    r = await api.post(f"/runs/{run_id}/retry")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


async def test_bulk_ingest(api) -> None:
    leads = [
        {
            **NEW_LEAD,
            "external_ref": f"B-{i}",
            "email": f"b{i}@example.com",
            "phone": f"+1 555 80{i:02d}",
        }
        for i in range(4)
    ]
    leads.append(dict(leads[0]))  # duplicate inside the same batch
    r = await api.post("/leads/bulk", json={"leads": leads})
    assert r.status_code == 202
    results = r.json()["results"]
    assert [x["created"] for x in results] == [True, True, True, True, False]
    for x in results[:4]:
        assert (await wait_run(api, x["run"]["id"]))["status"] == "succeeded"


async def test_validation_and_not_found_envelopes(api) -> None:
    r = await api.post("/leads", json={**NEW_LEAD, "dob": "not-a-date"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = await api.post("/leads", json={**NEW_LEAD, "unknown_field": 1})
    assert r.status_code == 422
    r = await api.get("/runs/run_nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


async def test_lead_with_bad_data_gets_request_info_not_422(api) -> None:
    r = await api.post(
        "/leads",
        json={
            "first_name": "X",
            "product_line": "motor",
            "consent_marketing": True,
            "consent_email": True,
            "email": "x@example.com",
        },
    )
    run = await wait_run(api, r.json()["run"]["id"])
    assert run["status"] == "succeeded"
    lead = (await api.get(f"/leads/{r.json()['lead_id']}")).json()
    assert lead["latest_recommendation"]["action"] == "request_info"


async def test_crash_recovery_requeues_orphaned_run(seeded_db, llm_switch) -> None:
    async with seeded_db.session() as s:
        s.add(
            Run(
                id="run_orphan",
                use_case="acquisition",
                subject_type="lead",
                subject_id="lead_l13",
                cycle_key="lead_l13",
                status="running",
                attempts=1,
                claimed_by="wdead00-0",
            )
        )
    from tests.integration.conftest import _client

    async for c in _client(seeded_db, llm_switch, start_runner=True):
        run = await wait_run(c, "run_orphan")
        assert run["status"] == "succeeded" and run["attempts"] == 2


async def test_orphan_out_of_attempts_is_failed(seeded_db, llm_switch) -> None:
    async with seeded_db.session() as s:
        s.add(
            Run(
                id="run_dead",
                use_case="acquisition",
                subject_type="lead",
                subject_id="lead_l13",
                cycle_key="lead_l13",
                status="running",
                attempts=3,
                max_attempts=3,
                claimed_by="wdead00-0",
            )
        )
    from tests.integration.conftest import _client

    async for c in _client(seeded_db, llm_switch, start_runner=True):
        run = (await c.get("/runs/run_dead")).json()
        assert run["status"] == "failed" and run["error_code"] == "worker_lost"


async def test_parallel_claims_never_double_claim(seeded_db) -> None:
    from insurance_poc.db.repositories import runs as runs_repo

    async with seeded_db.session() as s:
        for i in range(1, 11):
            s.add(
                Run(
                    id=f"run_c{i:02d}",
                    use_case="acquisition",
                    subject_type="lead",
                    subject_id=f"lead_x{i}",
                    cycle_key=f"lead_x{i}",
                    status="queued",
                )
            )

    async def claim(worker: str) -> list[str]:
        got = []
        while True:
            async with seeded_db.session() as s:
                run = await runs_repo.claim_next(s, worker)
            if run is None:
                return got
            got.append(run.id)

    results = await asyncio.gather(*(claim(f"w{i}") for i in range(5)))
    claimed = [rid for r in results for rid in r]
    assert sorted(claimed) == [f"run_c{i:02d}" for i in range(1, 11)]


async def test_no_partial_state_on_failure(api, llm_switch) -> None:
    calls = {"n": 0}

    def fail_on_product(purpose, messages):
        from tests.fixtures.fake_llm import smart_responder

        if purpose == "product_fit":
            raise ProviderError("bad key", status=401, retryable=False)
        calls["n"] += 1
        return smart_responder(purpose, messages)

    llm_switch.responder = fail_on_product
    run_id = (await api.post("/leads/lead_l02/runs")).json()["id"]
    run = await wait_run(api, run_id)
    assert run["status"] == "failed"
    db = api.app.state.db
    async with db.session() as s:
        recs = (
            (await s.execute(select(Recommendation).where(Recommendation.subject_id == "lead_l02")))
            .scalars()
            .all()
        )
        lead = await s.get(Lead, "lead_l02")
    assert recs == [] and lead.status == "failed" and calls["n"] == 2


async def test_recommendation_shows_other_products_with_reasons(api) -> None:
    run = await wait_run(api, (await api.post("/leads/lead_l01/runs")).json()["id"])
    detail = (await api.get(f"/recommendations/{run['recommendation_id']}")).json()
    [extra] = detail["cross_sell"]
    assert extra["code"] == "PA_INDIVIDUAL" and extra["name"] == "Personal Accident Cover"
    assert extra["reasons"] and extra["sold_through"] == "broker"
    steps = {s["key"]: s for s in detail["justification"]["steps"]}
    assert "Personal Accident Cover" in steps["cross_sell"]["outcome"]
    judgements = {f["judgement"] for f in detail["justification"]["cited_facts"]}
    assert {"Product fit", "Also suits: Personal Accident Cover"} <= judgements


async def test_customer_view_has_scores_screening_and_next_steps(api) -> None:
    run = await wait_run(api, (await api.post("/leads/lead_l01/runs")).json()["id"])
    detail = (await api.get(f"/recommendations/{run['recommendation_id']}")).json()
    rows = {r["code"]: r for r in detail["product_screening"]}
    assert rows[detail["products"][0]["code"]]["ai_status"] == "recommended"
    assert rows["PA_INDIVIDUAL"]["ai_status"] == "also_suits"
    assert rows["LIFE_TERM"]["status"] == "not_suitable" and rows["LIFE_TERM"]["reasons"]
    kinds = [s["kind"] for s in detail["next_steps"]]
    assert kinds == ["approve", "contact", "talk", "quote", "cross_sell"]
    contact, talk = detail["next_steps"][1], detail["next_steps"][2]
    assert "call back" in contact["detail"]  # L01 asked for a call back: personal timing
    assert contact["quote"]  # the opening line lives in the contact step
    fit = detail["decisions"]["product_fit"]
    assert fit["pain_points"] and fit["strategies"][0]["signal"] in detail["signals"]
    assert detail["next_steps"][3]["quote"] is None  # the quote step does not repeat it
    assert talk["items"]
    assert detail["next_steps"][1]["owner"] == "Broker desk"
    assert 0 <= detail["decisions"]["risk"]["score"] <= 1

    page = (await api.get("/leads", params={"q": "Okafor"})).json()
    brief = page["items"][0]["latest_recommendation"]
    assert brief["interest_score"] is not None and brief["risk_score"] is not None
    assert brief["top_product"]["name"] and brief["also_suits"] == ["Personal Accident Cover"]
    assert brief["approachability"]["score"] == round(brief["interest_score"] * 100)
    assert detail["approachability"] == brief["approachability"]
    proof = next(r for r in detail["product_screening"] if r["ai_status"] == "recommended")
    assert any(e.startswith("Aged ") for e in proof["evidence"])


async def test_nurture_next_steps_hold_the_sales_call(api) -> None:
    run = await wait_run(api, (await api.post("/leads/lead_l03/runs")).json()["id"])
    detail = (await api.get(f"/recommendations/{run['recommendation_id']}")).json()
    assert detail["action"] == "nurture"
    assert [s["kind"] for s in detail["next_steps"]] == ["approve", "nurture", "rerun"]
