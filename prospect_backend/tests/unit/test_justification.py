from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from insurance_poc.services import justification


def _rec(**kw: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "use_case": "acquisition",
        "action": "contact_and_quote",
        "queue": "sales",
        "priority": "high",
        "channel": None,
        "channel_owner": "direct",
        "confidence": "high",
        "rule_results": [],
        "decisions": {},
        "signals": {},
        "missing_info": [],
        "products": [],
        "fairness": {"passed": True, "redactions": 0, "categories": [], "violations": []},
        "review_reasons": [],
        "rulebook_version": "test",
    }
    return SimpleNamespace(**(base | kw))


def _r(id: str, passed: bool, severity: str = "info", reason: str = "r") -> dict[str, Any]:
    return {"id": id, "passed": passed, "severity": severity, "reason": reason, "data": {}}


def test_contact_and_quote_explains_rule_and_ai_path() -> None:
    rec = _rec(
        rule_results=[
            _r("consent.profiling", True),
            _r("data_quality.lead", True),
            _r("underwriting.referral_rules", True),
        ],
        decisions={
            "lead_score": {
                "band": "hot",
                "confidence": "high",
                "score": 0.9,
                "reasons": [{"signal": "pages_viewed", "explanation": "very engaged"}],
            }
        },
        signals={"pages_viewed": 14},
        products=[{"code": "MOTOR_COMP", "fit": "high", "rationale": "fits"}],
    )
    j = justification.build(rec, [])
    assert "contact and quote" in j["summary"]
    assert "hot" in j["summary"]
    keys = [s["key"] for s in j["steps"]]
    assert keys[:3] == ["consent", "data_quality", "underwriting"]
    assert {"decision", "routing", "fairness"} <= set(keys)
    assert (
        "pages viewed = 14: very engaged"
        in next(s for s in j["steps"] if s["key"] == "interest")["details"]
    )
    assert j["criteria_not_met"] == []
    assert j["ai_used"]


def test_knockout_is_refer_and_tells_approver_they_decide() -> None:
    rec = _rec(
        action="refer_to_underwriter",
        queue="underwriting",
        priority="low",
        review_reasons=["Knock-out rule hit: underwriter to decide"],
        rule_results=[
            _r("consent.profiling", True),
            _r("data_quality.lead", True),
            _r("underwriting.min_age", False, "block", "Applicant is under 18."),
        ],
    )
    j = justification.build(rec, [])
    uw = next(s for s in j["steps"] if s["key"] == "underwriting")
    assert uw["status"] == "fail" and "Knock-out" in uw["outcome"]
    assert "Underwriting rules" in j["criteria_not_met"]
    assert not any(s["key"] == "product" for s in j["steps"])
    assert any("you decide" in c for c in j["approver_checks"])
    assert not j["ai_used"]


@pytest.mark.parametrize(
    ("kw", "score", "label"),
    [
        ({"action": "do_not_contact", "rule_results": []}, 0, "Not approachable"),
        ({"action": "request_info", "missing_info": [{"field": "declared.smoker"}]}, None, None),
        ({"action": "refer_to_underwriter", "decisions": {}}, None, "Underwriter first"),
        ({"decisions": {"lead_score": {"score": 0.92}}}, 92, "Highly approachable"),
        ({"decisions": {"lead_score": {"score": 0.5}}}, 50, "Approachable"),
        ({"action": "nurture", "decisions": {"lead_score": {"score": 0.15}}}, 15, "Low priority"),
        (
            {"action": "refer_to_underwriter", "decisions": {"lead_score": {"score": 0.88}}},
            88,
            "On hold: underwriter first",
        ),
    ],
)
def test_approachability(kw, score, label) -> None:
    from insurance_poc.services import approachability

    out = approachability.compute(_rec(**kw))
    assert out["score"] == score
    if label:
        assert out["label"] == label
    assert out["reason"]


@pytest.mark.parametrize(
    ("sig", "expect"),
    [
        ({"requested_callback": True, "days_since_inquiry": 1}, "call back yesterday"),
        ({"days_since_inquiry": 2, "quote_requests_30d": 3}, "within 24 hours"),
        ({"days_since_inquiry": 6}, "this week"),
        ({"days_since_inquiry": 45}, "cooled"),
        ({"pages_viewed": 9}, "researching"),
        ({}, "High priority"),
    ],
)
def test_contact_timing_comes_from_the_customer(sig, expect) -> None:
    from insurance_poc.services.next_steps import timing

    assert expect in timing(sig, "high")


def test_referral_is_never_shown_as_approachable() -> None:
    from insurance_poc.services import approachability

    out = approachability.compute(
        _rec(
            action="refer_to_underwriter",
            decisions={"lead_score": {"score": 0.95}},
            rule_results=[
                {
                    "id": "underwriting.property_age",
                    "passed": False,
                    "severity": "refer",
                    "reason": "Property is more than 100 years old.",
                }
            ],
        )
    )
    assert out["band"] == "hold" and "approachable" not in out["label"].lower()
    assert "property is more than 100 years old" in out["reason"]


def test_referral_reasons_read_as_sentences() -> None:
    from insurance_poc.services.next_steps import _sentences

    raw = [
        "Underwriting referral: Property is more than 100 years old.; "
        "Sum insured above every product limit; manual large-risk review."
    ]
    assert _sentences(s.split(":", 1)[-1] for s in raw) == [
        "Property is more than 100 years old.",
        "Sum insured above every product limit.",
        "Manual large-risk review.",
    ]
