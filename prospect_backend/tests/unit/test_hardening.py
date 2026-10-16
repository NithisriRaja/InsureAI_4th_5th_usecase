"""Regression tests for AI-safety and storage fixes found in code review."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

from insurance_poc import csv_data
from insurance_poc.services.decisions.features import lead_notes
from insurance_poc.services.decisions.product_fit import ProductRanking, validate_ranking
from insurance_poc.services.rules.facts import LeadFacts
from insurance_poc.services.rules.fairness import redact_text, scan_payload


def _facts(notes: str) -> LeadFacts:
    return LeadFacts(
        lead_id="lead_x",
        as_of=date(2026, 10, 15),
        product_line="motor",
        first_name="Maya",
        last_name="Singh",
        dob=None,
        age=None,
        email="maya@example.com",
        phone="+971 50 123 4567",
        sum_insured=None,
        notes=notes,
    )


def test_notes_lose_name_email_and_phone_before_the_llm() -> None:
    text, _ = lead_notes(
        _facts("Maya asked for a call on +971 50 123 4567 or maya.s@work.example; SINGH ok.")
    )
    assert text is not None
    for leaked in ("Maya", "SINGH", "971", "maya.s@work.example"):
        assert leaked not in text
    assert "asked for a call" in text


def test_origin_phrase_at_sentence_start_is_caught() -> None:
    for note in ("Originally from Poland, keen on cover.", "Born in Lagos. Wants cover."):
        assert scan_payload({"notes": note}), note
        redacted, report = redact_text(note)
        assert "nationality" in report.categories and not scan_payload({"notes": redacted})
    assert not scan_payload({"notes": "Born in the spring; drives daily."})


def _ranking(recommended: str) -> ProductRanking:
    reason = {"signal": "age_band", "explanation": "Fits."}
    return ProductRanking.model_validate(
        {
            "ranked": [
                {"code": "MOTOR_X", "fit": "high", "rationale": "Best fit."},
                {"code": "MOTOR_Y", "fit": "low", "rationale": "Weaker."},
            ],
            "recommended_code": recommended,
            "reasons": [reason],
            "explanation": "Offer the first one.",
            "pitch": "Good cover.",
            "talking_points": [reason],
            "pain_points": [reason],
            "strategies": [{"title": "T", "how": "H", "signal": "age_band"}],
            "confidence": "high",
            "needs_review": False,
        }
    )


def test_recommended_product_must_be_ranked_first() -> None:
    signals: dict[str, Any] = {"age_band": "30-39"}
    assert validate_ranking(_ranking("MOTOR_X"), ["MOTOR_X", "MOTOR_Y"], signals) == []
    errs = validate_ranking(_ranking("MOTOR_Y"), ["MOTOR_X", "MOTOR_Y"], signals)
    assert any("first product in ranked" in e for e in errs)


def test_extra_lead_columns_survive_a_save() -> None:
    lead = SimpleNamespace(
        id="lead_1",
        sum_insured_requested=None,
        declared={"vehicle_year": 2022, "campaign": "spring"},
        protected={},
        status="new",
        created_at=None,
    )
    cols = csv_data.lead_columns([lead])
    assert "campaign" in cols and cols[-2:] == ["status", "created_at"]
    row = csv_data.lead_row(lead)  # type: ignore[arg-type]
    assert row["campaign"] == "spring" and row["vehicle_year"] == "2022"
