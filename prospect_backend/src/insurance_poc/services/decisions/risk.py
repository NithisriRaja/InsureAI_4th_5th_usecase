"""Risk band for an applicant that passed underwriting knock-outs (accept or refer).

The rules' outcome is passed in as context; the LLM adds colour only and cannot change it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from insurance_poc.services.decisions.common import (
    REASON_GUIDE,
    Confidence,
    Reason,
    grounding_errors,
    score_band_errors,
)
from insurance_poc.services.llm.client import LLMClient

PURPOSE = "risk_assessment"
# Score ranges per band; they overlap so borderline cases can sit in either band.
RISK_BAND_RANGES = {"low": (0.0, 0.4), "medium": (0.3, 0.7), "high": (0.6, 1.0)}


class RiskAssessment(BaseModel):
    band: Literal["low", "medium", "high"]
    score: float = Field(ge=0, le=1, description="0 = lowest risk, 1 = highest; inside the band.")
    confidence: Confidence
    reasons: list[Reason] = Field(min_length=1, max_length=5)
    summary: str = Field(max_length=400, description="One or two sentences for the underwriter.")


INSTRUCTIONS = f"""
You are an insurance underwriting assistant preparing a risk summary for an underwriter.
Rate the applicant's insurance risk for the requested line as low, medium or high, with a
score from 0 (lowest) to 1 (highest) inside the band (low 0-0.4, medium 0.3-0.7, high
0.6-1), using only
the risk facts provided (e.g. vehicle or property age, claims history, driving experience,
smoker status, BMI, declared conditions, occupation risk, cover versus income, employee count,
sum insured).
You give indicators only; you never accept, decline or price. The rule outcome
(clear/refer) is already final; do not contradict or restate it as a decision. Ignore
engagement/marketing signals for risk.
{REASON_GUIDE}
""".strip()


async def assess_risk(
    llm: LLMClient, signals: dict[str, Any], uw_outcome: str, rule_reasons: list[str]
) -> RiskAssessment:
    return await llm.structured(
        RiskAssessment,
        purpose=PURPOSE,
        instructions=INSTRUCTIONS,
        task="Assess the risk of this applicant.",
        data={
            "signals": signals,
            "underwriting_outcome": uw_outcome,
            "underwriting_rule_findings": rule_reasons,
        },
        validate=lambda r: (
            grounding_errors(r.reasons, signals)
            + score_band_errors(r.score, r.band, RISK_BAND_RANGES)
        ),
    )
