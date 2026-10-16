from __future__ import annotations

import pytest

from insurance_poc import csv_data, rulebook
from insurance_poc.enums import Action, Channel, Queue
from insurance_poc.services import guardrails
from insurance_poc.services.decisions import features
from insurance_poc.services.rules import (
    application,
    consent,
    cross_sell,
    data_quality,
    eligibility,
    fairness,
    routing,
    underwriting,
)
from insurance_poc.services.rules.facts import LeadFacts, lead_facts
from insurance_poc.services.rules.types import Severity
from tests.conftest import AS_OF, DEMO_CSV


def _demo() -> tuple[list, dict]:
    problems: list[str] = []
    products = csv_data.read_products(DEMO_CSV / "products.csv", problems)
    customers = csv_data.read_customers(DEMO_CSV / "customers.csv", problems)
    leads = csv_data.read_leads(DEMO_CSV / "leads.csv", problems, {c.id for c in customers})
    assert not problems, problems
    return products, {lead.external_ref.split("-")[0]: lead for lead in leads}


CATALOGUE, DEMO_LEADS = _demo()
PRODUCTS_BY_CODE = {p.code: p for p in CATALOGUE}


def lead(ref_prefix: str) -> LeadFacts:
    return lead_facts(DEMO_LEADS[ref_prefix], AS_OF)


# ------------------------------------------------------------- rulebook ---


def test_every_product_is_wired_to_the_rulebook() -> None:
    for p in CATALOGUE:
        assert p.line in rulebook.LINES, p.code
        assert set(p.channels) <= set(rulebook.LINES[p.line]["owners"]), p.code
        assert set(p.rules) <= set(csv_data.PRODUCT_RULES), p.code


def test_every_action_has_an_approver() -> None:
    for action in Action:
        assert action in rulebook.APPROVAL_MATRIX, action
        assert rulebook.APPROVAL_MATRIX[action]["agent"] in ("draft", "recommend")


# ------------------------------------------------------------ acquisition ---

LEAD_EXPECTATIONS = [
    # ref, owner, permission, outreach consent, data ok, uw outcome, eligible products
    ("L01", "broker", True, True, True, "clear", {"MOTOR_TPL", "MOTOR_COMPREHENSIVE"}),
    ("L02", "direct", True, True, True, "clear", {"MEDICAL_FAMILY"}),
    ("L03", "direct", True, True, True, "clear", {"HOME_CONTENTS"}),
    ("L04", "direct", True, False, True, "clear", {"MOTOR_TPL", "MOTOR_COMPREHENSIVE"}),
    ("L06", "adviser", True, True, True, "knockout", set()),
    ("L07", "direct", True, True, True, "clear", {"MOTOR_TPL", "MOTOR_COMPREHENSIVE"}),
    ("L08", "direct", True, True, True, "clear", {"MEDICAL_ESSENTIAL", "MEDICAL_FAMILY"}),
    ("L09", "adviser", True, True, True, "refer", {"LIFE_TERM"}),
    ("L10", "direct", True, True, True, "refer", set()),
    ("L11", "direct", True, True, True, "knockout", set()),
    ("L12", "direct", True, True, True, "refer", {"HOME_CONTENTS"}),
    (
        "L13",
        "adviser",
        True,
        True,
        True,
        "clear",
        {"LIFE_TERM", "LIFE_CRITICAL_ILLNESS", "LIFE_WHOLE_OF_LIFE"},
    ),
    (
        "L15",
        "adviser",
        True,
        True,
        True,
        "clear",
        {"SAVINGS_EDUCATION", "SAVINGS_REGULAR", "SAVINGS_SINGLE_PREMIUM"},
    ),
    ("L16", "adviser", True, True, True, "clear", {"SAVINGS_REGULAR", "SAVINGS_SINGLE_PREMIUM"}),
    ("L17", "broker", True, True, True, "clear", {"GROUP_MEDICAL", "GROUP_LIFE"}),
    ("L18", "direct", False, True, True, "clear", {"MOTOR_TPL", "MOTOR_COMPREHENSIVE"}),
]


@pytest.mark.parametrize(
    ("ref", "owner", "permission", "consent_ok", "data_ok", "outcome", "eligible"),
    LEAD_EXPECTATIONS,
)
def test_lead_scenarios(ref, owner, permission, consent_ok, data_ok, outcome, eligible) -> None:
    f = lead(ref)
    assert f.channel_owner == owner
    assert consent.check_lead_permission(f).passed is permission
    assert consent.check_lead_consent(f).passed is consent_ok
    results, missing = data_quality.check_lead_data(f)
    assert results[0].passed is data_ok, missing
    uw = underwriting.assess(f, CATALOGUE)
    assert uw.outcome == outcome, uw.results
    assert set(uw.eligible_products) == eligible


def test_missing_and_invalid_data_lists_fields() -> None:
    _, missing = data_quality.check_lead_data(lead("L05"))
    assert {m["field"] for m in missing} == {"dob", "email"}


def test_future_dob_is_invalid() -> None:
    results, missing = data_quality.check_lead_data(lead("L14"))
    assert not results[0].passed
    assert missing == [{"field": "dob", "reason": "date of birth is in the future"}]


def test_line_specific_required_fields() -> None:
    f = lead("L01").model_copy(update={"declared": {}})
    _, missing = data_quality.check_lead_data(f)
    assert {"declared.vehicle_year", "declared.driving_years"} <= {m["field"] for m in missing}
    life = lead("L13").model_copy(update={"declared": {}})
    _, missing = data_quality.check_lead_data(life)
    assert "declared.annual_income" in {m["field"] for m in missing}


def test_company_lines_need_no_date_of_birth() -> None:
    results, missing = data_quality.check_lead_data(lead("L17"))
    assert results[0].passed, missing


def test_knockout_is_never_a_decline() -> None:
    uw = underwriting.assess(lead("L06"), CATALOGUE)
    assert uw.outcome == "knockout"
    assert any(r.id == "underwriting.min_age" and r.severity == Severity.BLOCK for r in uw.results)
    assert "decline" not in {a.value for a in Action}


def test_knockout_beats_refer() -> None:
    # Old vehicle (knock-out) + many claims (refer) -> knock-out.
    f = lead("L11").model_copy(update={"declared": {**lead("L11").declared, "prior_claims_3y": 5}})
    uw = underwriting.assess(f, CATALOGUE)
    assert uw.outcome == "knockout"
    assert {r.id for r in uw.results} >= {"underwriting.vehicle_age", "underwriting.claims_history"}


def test_declarative_rule_matching() -> None:
    m = underwriting.matches
    assert m({"field": "age", "op": "gte", "value": 50}, {"age": 50})
    assert not m({"field": "age", "op": "gte", "value": 50}, {"age": None})
    assert m({"field": "x", "op": "intersects", "value": ["a"]}, {"x": ["a", "b"]})
    assert m(
        {"all": [{"field": "smoker", "op": "is_true"}, {"field": "age", "op": "gt", "value": 1}]},
        {"smoker": True, "age": 2},
    )
    assert not m({"field": "smoker", "op": "is_true"}, {"smoker": "yes"})


def test_eligibility_boundaries() -> None:
    comp = PRODUCTS_BY_CODE["MOTOR_COMPREHENSIVE"]
    base = lead("L01")
    assert eligibility.check_product(base.model_copy(update={"age": 21}), comp).eligible
    assert not eligibility.check_product(base.model_copy(update={"age": 20}), comp).eligible
    ten = base.model_copy(update={"declared": {**base.declared, "vehicle_year": 2016}})
    eleven = base.model_copy(update={"declared": {**base.declared, "vehicle_year": 2015}})
    assert eligibility.check_product(ten, comp).eligible
    assert not eligibility.check_product(eleven, comp).eligible


def test_adviser_products_not_sold_through_brokers() -> None:
    f = lead("L13").model_copy(update={"channel_owner": "broker"})
    check = eligibility.check_product(f, PRODUCTS_BY_CODE["LIFE_TERM"])
    assert not check.eligible
    assert any(r.id == "eligibility.channel" for r in check.failures)


def test_cover_income_multiple_limit() -> None:
    f = lead("L13")
    big = f.model_copy(update={"sum_insured": f.declared["annual_income"] * 21})
    assert not eligibility.check_product(big, PRODUCTS_BY_CODE["LIFE_TERM"]).eligible
    assert eligibility.check_product(big, PRODUCTS_BY_CODE["LIFE_WHOLE_OF_LIFE"]).eligible
    assert underwriting.assess(big, CATALOGUE).outcome == "refer"


def _extra(f: LeadFacts) -> dict[str, cross_sell.CrossLineCandidate]:
    return {c.code: c for c in cross_sell.candidates(f, CATALOGUE)}


def test_cross_line_needs_the_other_lines_required_facts() -> None:
    f = lead("L07")  # motor, no occupation_risk / smoker on file
    assert _extra(f) == {}
    with_job = f.model_copy(update={"declared": {**f.declared, "occupation_risk": "low"}})
    assert set(_extra(with_job)) == {"PA_INDIVIDUAL"}


def test_cross_line_never_bypasses_the_broker() -> None:
    f = lead("L01")  # broker-owned motor
    found = _extra(f)
    assert set(found) == {"PA_INDIVIDUAL"} and found["PA_INDIVIDUAL"].channel_owner == "broker"
    smoker = f.model_copy(update={"declared": {**f.declared, "smoker": False}})
    assert "MEDICAL_ESSENTIAL" in _extra(smoker)  # broker sells medical too
    assert not any(c.line == "life" for c in _extra(smoker).values())  # adviser-only line


def test_cross_line_hands_regulated_lines_to_an_adviser() -> None:
    found = _extra(lead("L15"))  # adviser-owned savings lead with life facts
    assert found["LIFE_TERM"].channel_owner == "adviser"
    assert found["MEDICAL_ESSENTIAL"].channel_owner == "direct"


def test_cross_line_ignores_the_main_lines_cover_amount() -> None:
    f = lead("L15").model_copy(update={"sum_insured": 1_000_000})  # 10k, for savings
    assert f.sum_insured < PRODUCTS_BY_CODE["LIFE_TERM"].min_sum_insured
    assert "LIFE_TERM" in _extra(f)


def test_cross_line_drops_knockouts_and_flags_referrals() -> None:
    found = _extra(lead("L09"))  # life lead
    assert found["MEDICAL_ESSENTIAL"].needs_underwriter
    assert found["MEDICAL_ESSENTIAL"].referral_reasons
    assert not found["PA_INDIVIDUAL"].needs_underwriter
    young = lead("L01").model_copy(update={"age": 17})
    assert _extra(young) == {}


def test_cross_line_keeps_companies_and_people_apart() -> None:
    assert _extra(lead("L17")) == {}  # group scheme: no personal products
    f = lead("L13").model_copy(update={"declared": {**lead("L13").declared, "employee_count": 50}})
    assert not any(c.line == "group" for c in _extra(f).values())


def test_channel_owner_resolution() -> None:
    assert routing.resolve_lead_owner("motor", "broker_portal", None) == "broker"
    assert routing.resolve_lead_owner("motor", "web", None) == "direct"
    # Adviser-led lines always land with an adviser, even from the website.
    assert routing.resolve_lead_owner("life", "web", None) == "adviser"
    assert routing.resolve_lead_owner("life", "web", "broker") == "adviser"
    assert routing.resolve_lead_owner("group", "web", None) == "broker"
    assert routing.resolve_lead_owner("motor", "web", "broker") == "broker"


def test_broker_owned_leads_go_through_the_broker() -> None:
    f = lead("L01").model_copy(update={"consent_marketing": False})
    assert consent.check_lead_consent(f).passed  # broker contacts their own client
    assert consent.lead_channels(f) == [Channel.INTERMEDIARY]


def test_lead_channels_need_contact_detail() -> None:
    f = lead("L02").model_copy(update={"phone": None, "consent_email": False})
    assert consent.lead_channels(f) == []
    assert not consent.check_lead_consent(f).passed


def test_purchased_list_is_never_profiled() -> None:
    r = consent.check_lead_permission(lead("L18"))
    assert not r.passed and r.id == "consent.source_permission"
    no_consent = lead("L02").model_copy(update={"consent_profiling": False})
    assert consent.check_lead_permission(no_consent).id == "consent.profiling"


def test_application_checklist_life() -> None:
    checklist, results = application.prepare(lead("L13"))
    assert checklist["documents_missing"] == ["medical_questionnaire"]
    assert [e["item"] for e in checklist["evidence_required"]] == [
        "medical_questionnaire",
        "paramedical_exam",
        "blood_profile",
    ]
    assert checklist["needs"]["protection_gap"] == 3_500_000
    assert any(r.id == "application.documents" and not r.passed for r in results)


def test_savings_affordability_flag() -> None:
    _, ok = application.prepare(lead("L15"))
    assert not any(r.id == "suitability.affordability" for r in ok)
    checklist, bad = application.prepare(lead("L16"))
    assert checklist["needs"]["affordable"] is False
    assert any(r.id == "suitability.affordability" for r in bad)


# ---------------------------------------------------------------- routing ---


@pytest.mark.parametrize(
    ("action", "owner", "regulated", "queue"),
    [
        (Action.CONTACT_AND_QUOTE, "direct", False, Queue.SALES),
        (Action.CONTACT_AND_QUOTE, "broker", False, Queue.SALES),
        (Action.CONTACT_AND_QUOTE, "adviser", True, Queue.ADVISER),
        (Action.REFER_TO_UNDERWRITER, "adviser", True, Queue.UNDERWRITING),
        (Action.NURTURE, "adviser", True, Queue.ADVISER),
        (Action.NURTURE, "direct", False, Queue.SALES),
        (Action.REQUEST_INFO, "broker", False, Queue.SALES),
    ],
)
def test_queue_routing(action, owner, regulated, queue) -> None:
    assert routing.route_queue(action, owner, regulated_product=regulated) == queue


# ------------------------------------------------------------- guardrails ---


@pytest.mark.parametrize(
    ("rec", "rule"),
    [
        ({"action": "decline"}, "guardrail.forbidden_action"),
        ({"action": "issue_policy"}, "guardrail.forbidden_action"),
        ({"action": "teleport"}, "guardrail.unknown_action"),
        (
            {"action": "contact_and_quote", "channel": "email", "channel_owner": "broker"},
            "guardrail.bypass_intermediary",
        ),
        ({"action": "nurture", "status": "approved"}, "guardrail.auto_execute"),
    ],
)
def test_guardrails_block(rec, rule) -> None:
    with pytest.raises(guardrails.GuardrailViolation) as e:
        guardrails.check_recommendation(rec)
    assert e.value.rule == rule


# --------------------------------------------------------------- fairness ---


def test_notes_redaction() -> None:
    notes, report = features.lead_notes(lead("L08"))
    assert notes is not None
    for word in ("Catholic", "divorced", "Poland", "she", "practising"):
        assert word.lower() not in notes.lower()
    assert report.redactions >= 4
    assert {"religion", "marital_status", "nationality", "gender"} <= set(report.categories)
    assert fairness.scan_payload({"notes": notes}) == []


def test_scan_payload_flags_keys_and_terms() -> None:
    v = fairness.scan_payload({"signals": {"gender": "f"}, "notes": "He is Muslim"})
    assert any("protected key" in x for x in v)
    assert any("religion" in x for x in v)
    with pytest.raises(fairness.FairnessViolation):
        fairness.assert_clean({"x": ["originally from Mexico"]})


def test_scan_avoids_substring_false_positives() -> None:
    assert fairness.scan_payload({"notes": "Other details: the mileage is low, thermal"}) == []


@pytest.mark.parametrize("ref", sorted(DEMO_LEADS))
def test_lead_signals_are_clean(ref) -> None:
    f = lead(ref)
    notes, _ = features.lead_notes(f)
    checklist, _ = application.prepare(f)
    payload = {"signals": features.lead_signals(f, checklist), "notes": notes}
    assert fairness.scan_payload(payload) == []
    flat = str(payload)
    for pii in (f.email, f.phone, f.first_name, f.last_name):
        if pii:
            assert pii not in flat


def test_age_band() -> None:
    assert features.age_band(17) == "under_18"
    assert features.age_band(34) == "25-34"
    assert features.age_band(80) == "75+"
    assert features.age_band(None) is None


def test_product_ranking_must_ground_reasons_and_stay_in_the_lists() -> None:
    from insurance_poc.services.decisions.product_fit import ProductRanking, validate_ranking

    def ranking(**over: object) -> ProductRanking:
        base = {
            "ranked": [{"code": "MOTOR_TPL", "fit": "high", "rationale": "fits"}],
            "recommended_code": "MOTOR_TPL",
            "reasons": [{"signal": "vehicle_age_years", "explanation": "new car"}],
            "also_suggest": [
                {
                    "code": "PA_INDIVIDUAL",
                    "rationale": "two dependents",
                    "reasons": [{"signal": "dependents", "explanation": "family relies on them"}],
                }
            ],
            "explanation": "Third-party cover fits.",
            "pitch": "Covers you if you damage someone else's car.",
            "talking_points": [{"signal": "dependents", "explanation": "Ask about the family"}],
            "pain_points": [{"signal": "dependents", "explanation": "Family relies on them"}],
            "strategies": [
                {
                    "title": "Lead with family",
                    "how": "Explain the protection.",
                    "signal": "dependents",
                }
            ],
            "confidence": "high",
            "needs_review": False,
        }
        return ProductRanking.model_validate({**base, **over})

    sig = {"vehicle_age_years": 3, "dependents": 2}
    ok = ranking()
    coded = ranking(pitch="MOTOR_TPL is great for you.")
    ungrounded_strategy = ranking(strategies=[{"title": "x", "how": "y", "signal": "made_up"}])
    assert any(
        "strategies[0]" in e for e in validate_ranking(ungrounded_strategy, ["MOTOR_TPL"], sig, [])
    )
    coded_strategy = ranking(
        strategies=[{"title": "x", "how": "Offer MOTOR_TPL.", "signal": "dependents"}]
    )
    assert any("not codes" in e for e in validate_ranking(coded_strategy, ["MOTOR_TPL"], sig, []))
    assert any("not codes" in e for e in validate_ranking(coded, ["MOTOR_TPL"], sig, []))
    assert validate_ranking(ok, ["MOTOR_TPL"], sig, ["PA_INDIVIDUAL"]) == []
    assert any("not allowed" in e for e in validate_ranking(ok, ["MOTOR_TPL"], sig, []))
    ungrounded = ranking(reasons=[{"signal": "made_up", "explanation": "x"}])
    assert validate_ranking(ungrounded, ["MOTOR_TPL"], sig, ["PA_INDIVIDUAL"])
    extra_ungrounded = ranking(
        also_suggest=[
            {
                "code": "PA_INDIVIDUAL",
                "rationale": "x",
                "reasons": [{"signal": "made_up", "explanation": "x"}],
            }
        ]
    )
    errs = validate_ranking(extra_ungrounded, ["MOTOR_TPL"], sig, ["PA_INDIVIDUAL"])
    assert any(e.startswith("also_suggest[0]") for e in errs)


def test_screening_explains_every_product() -> None:
    from insurance_poc.services.rules import screening

    rows = {r["code"]: r for r in screening.screen(lead("L01"), CATALOGUE)}
    assert set(rows) == set(PRODUCTS_BY_CODE)
    assert rows["MOTOR_COMPREHENSIVE"]["status"] == "eligible"
    assert rows["MOTOR_COMPREHENSIVE"]["requested_line"] is True
    assert rows["PA_INDIVIDUAL"]["status"] == "eligible"
    assert rows["MEDICAL_ESSENTIAL"]["status"] == "not_assessed"
    assert "smoker" in rows["MEDICAL_ESSENTIAL"]["reasons"][0]
    assert rows["LIFE_TERM"]["status"] == "not_suitable"
    assert "adviser" in rows["LIFE_TERM"]["reasons"][0]
    assert rows["GROUP_MEDICAL"]["status"] == "not_suitable"
    old_car = {r["code"]: r for r in screening.screen(lead("L07"), CATALOGUE)}
    assert all(r["reasons"] for r in old_car.values() if r["status"] != "eligible")


def test_guardrails_allow_valid() -> None:
    guardrails.check_recommendation(
        {"action": "contact_and_quote", "channel": "intermediary", "channel_owner": "broker"}
    )
    guardrails.check_recommendation(
        {"action": "nurture", "channel": None, "channel_owner": "direct", "status": None}
    )


def test_facts_carry_no_protected_fields() -> None:
    assert not set(LeadFacts.model_fields) & fairness.PROTECTED_KEYS
