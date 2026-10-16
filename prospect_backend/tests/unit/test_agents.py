from __future__ import annotations

import pytest
from sqlalchemy import func, select

from insurance_poc.agents.graph import cycle_key_for, run_graph
from insurance_poc.agents.state import GraphDeps
from insurance_poc.db.models import AuditEvent, Lead, LLMCall, Recommendation, Run
from insurance_poc.integrations.mocks import MockCatalogue, MockCRM
from insurance_poc.services.llm.types import LLMUnavailable, ProviderError
from insurance_poc.services.rules.fairness import scan_payload
from insurance_poc.utils.ids import new_id
from tests.fixtures.fake_llm import fake_llm, payload


async def run_subject(db, llm, use_case: str, subject_id: str):
    subject_type = "lead"
    cycle = cycle_key_for(use_case, subject_id)
    run_id = new_id("run")
    async with db.session() as s:
        s.add(
            Run(
                id=run_id,
                use_case=use_case,
                subject_type=subject_type,
                subject_id=subject_id,
                cycle_key=cycle,
                status="running",
            )
        )
    deps = GraphDeps(db=db, llm=llm, crm=MockCRM(db), catalogue=MockCatalogue(db))
    state = await run_graph(
        run_id=run_id,
        use_case=use_case,
        subject_type=subject_type,
        subject_id=subject_id,
        cycle_key=cycle,
        deps=deps,
    )
    async with db.session() as s:
        (await s.get(Run, run_id)).status = "succeeded"
    rec = None
    if state.get("recommendation_id"):
        async with db.session() as s:
            rec = await s.get(Recommendation, state["recommendation_id"])
    return state, rec


ACQ = [
    # lead, action, queue, priority, llm calls
    ("lead_l01", "contact_and_quote", "sales", "high", 3),  # broker-owned
    ("lead_l02", "contact_and_quote", "sales", "medium", 3),
    ("lead_l03", "nurture", "sales", "low", 3),
    ("lead_l04", "do_not_contact", "sales", "low", 0),
    ("lead_l05", "request_info", "sales", "low", 0),
    ("lead_l06", "refer_to_underwriter", "underwriting", "low", 0),  # knock-out
    ("lead_l07", "nurture", "sales", "low", 3),
    ("lead_l08", "contact_and_quote", "sales", "high", 3),
    ("lead_l09", "refer_to_underwriter", "underwriting", "medium", 3),
    ("lead_l10", "refer_to_underwriter", "underwriting", "high", 2),
    ("lead_l11", "refer_to_underwriter", "underwriting", "low", 0),  # knock-out
    ("lead_l12", "refer_to_underwriter", "underwriting", "medium", 3),
    ("lead_l13", "contact_and_quote", "adviser", "medium", 3),
    ("lead_l14", "request_info", "sales", "low", 0),
    ("lead_l15", "contact_and_quote", "adviser", "high", 3),
    ("lead_l16", "contact_and_quote", "adviser", "medium", 3),
    ("lead_l17", "contact_and_quote", "sales", "high", 3),  # group scheme via broker
    ("lead_l18", "do_not_contact", "sales", "low", 0),  # purchased list
]


@pytest.mark.parametrize(("lead_id", "action", "queue", "priority", "calls"), ACQ)
async def test_acquisition_branches(seeded_db, lead_id, action, queue, priority, calls):
    llm, provider = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", lead_id)
    assert rec is not None and rec.status == "pending_approval"
    assert (rec.action, rec.queue, rec.priority) == (action, queue, priority)
    assert len(provider.calls) == calls
    assert rec.explanation and rec.rulebook_version
    async with seeded_db.session() as s:
        assert (await s.get(Lead, lead_id)).status == "recommended"


async def test_refer_forces_review_and_lists_products(seeded_db):
    llm, _ = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l09")
    assert rec.needs_review
    assert any("Underwriting referral" in r for r in rec.review_reasons)
    assert [p["code"] for p in rec.products] == ["LIFE_TERM"]
    assert rec.channel_owner == "adviser"
    assert "full_medical_exam" in {e["item"] for e in rec.checklist["evidence_required"]}


async def test_knockout_goes_to_underwriter_without_llm(seeded_db):
    llm, provider = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l11")
    assert rec.action == "refer_to_underwriter" and rec.needs_review
    assert "does not decline" in rec.explanation
    assert provider.calls == []


async def test_broker_lead_routes_through_broker(seeded_db):
    llm, _ = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l01")
    assert rec.channel_owner == "broker" and rec.channel == "intermediary"
    assert rec.checklist["completeness_pct"] == 100


async def test_cross_line_suggestion_is_grounded_and_keeps_the_broker(seeded_db):
    llm, provider = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l01")
    fit = rec.decisions["product_fit"]
    assert fit["reasons"] and all(r["signal"] in rec.signals for r in fit["reasons"])
    [extra] = fit["also_suggest"]
    assert extra["code"] == "PA_INDIVIDUAL" and extra["line"] == "personal_accident"
    assert extra["sold_through"] == "broker" and extra["needs_underwriter"] is False
    assert "occupation_risk" in rec.signals  # the other line's facts reach the AI
    assert rec.products[0]["code"].startswith("MOTOR_")  # the main ranking is unchanged
    call = next(c for c in provider.calls if c["purpose"] == "product_fit")
    others = payload(call["messages"])["other_products"]
    assert [o["code"] for o in others] == ["PA_INDIVIDUAL"]
    assert "description" not in others[0]


async def test_no_cross_line_candidates_without_the_facts(seeded_db):
    llm, provider = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l07")
    assert rec.decisions["product_fit"]["also_suggest"] == []
    call = next(c for c in provider.calls if c["purpose"] == "product_fit")
    assert payload(call["messages"])["other_products"] == []


async def test_adviser_lead_carries_application_prep(seeded_db):
    llm, provider = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l13")
    assert rec.channel is None  # adviser follows up; nothing sent to the customer
    assert rec.checklist["documents_missing"] == ["medical_questionnaire"]
    assert rec.checklist["needs"]["protection_gap"] == 3_500_000
    sig = payload(provider.calls[0]["messages"])["signals"]
    assert sig["protection_gap"] == 3_500_000 and sig["channel_owner"] == "adviser"


async def test_unaffordable_savings_needs_review(seeded_db):
    llm, _ = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l16")
    assert rec.needs_review
    assert any(r.startswith("Suitability:") for r in rec.review_reasons)


async def test_unpermitted_data_is_not_profiled(seeded_db):
    llm, provider = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l18")
    assert rec.action == "do_not_contact" and provider.calls == []
    assert set(rec.signals) == {"product_line", "source", "channel_owner"}


async def test_missing_info_recorded(seeded_db):
    llm, _ = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l05")
    assert {m["field"] for m in rec.missing_info} == {"dob", "email"}
    assert "dob" in rec.explanation


async def test_protected_info_never_reaches_llm(seeded_db):
    llm, provider = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l08")
    assert rec.fairness["redactions"] >= 4
    for call in provider.calls:
        data = payload(call["messages"])
        assert scan_payload(data) == []
        text = str(data).lower()
        for word in ("catholic", "divorced", "poland", "kowalski", "anna", "example.com"):
            assert word not in text


async def test_prompt_injection_is_data_only(seeded_db):
    llm, provider = fake_llm()
    _, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l07")
    score_call = next(c for c in provider.calls if c["purpose"] == "lead_score")
    user = next(m.content for m in score_call["messages"] if m.role == "user")
    system = next(m.content for m in score_call["messages"] if m.role == "system")
    assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in user.split("<data>")[1]  # stays inside data
    assert "untrusted" in system
    assert rec.action == "nurture"  # rules/fake unaffected


async def test_rerun_supersedes_pending(seeded_db):
    llm, _ = fake_llm()
    _, first = await run_subject(seeded_db, llm, "acquisition", "lead_l01")
    _, second = await run_subject(seeded_db, llm, "acquisition", "lead_l01")
    async with seeded_db.session() as s:
        old = await s.get(Recommendation, first.id)
        pending = (
            await s.execute(
                select(func.count())
                .select_from(Recommendation)
                .where(Recommendation.subject_id == "lead_l01")
                .where(Recommendation.status == "pending_approval")
            )
        ).scalar_one()
    assert old.status == "superseded" and old.version == 2
    assert pending == 1 and second.status == "pending_approval"


async def test_llm_failure_propagates_and_writes_nothing(seeded_db):
    def down(purpose, messages):
        raise ProviderError("503", status=503, retryable=True)

    llm, _ = fake_llm(down)
    with pytest.raises(LLMUnavailable):
        await run_subject(seeded_db, llm, "acquisition", "lead_l01")
    async with seeded_db.session() as s:
        n = (await s.execute(select(func.count()).select_from(Recommendation))).scalar_one()
        calls = (await s.execute(select(LLMCall.status))).scalars().all()
    assert n == 0
    assert calls and set(calls) == {"error"}


async def test_audit_trail_per_node(seeded_db):
    llm, _ = fake_llm()
    state, rec = await run_subject(seeded_db, llm, "acquisition", "lead_l01")
    async with seeded_db.session() as s:
        events = (
            (
                await s.execute(
                    select(AuditEvent.event_type)
                    .where(AuditEvent.run_id == state["run_id"])
                    .order_by(AuditEvent.id)
                )
            )
            .scalars()
            .all()
        )
        llm_rows = (
            await s.execute(
                select(LLMCall.node, LLMCall.purpose).where(LLMCall.run_id == state["run_id"])
            )
        ).all()
    assert events == [
        "node.prospect",
        "node.risk",
        "node.scoring",
        "node.product",
        "node.engagement",
        "recommendation.created",
    ]
    assert sorted(llm_rows) == [
        ("product", "product_fit"),
        ("risk", "risk_assessment"),
        ("scoring", "lead_score"),
    ]


async def test_unknown_subject_raises(seeded_db):
    llm, _ = fake_llm()
    with pytest.raises(LookupError):
        await run_subject(seeded_db, llm, "acquisition", "lead_nope")
