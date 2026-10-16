"""Lead priority: hot / warm / cold with confidence and grounded reasons."""

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

PURPOSE = "lead_score"
BAND_RANGES = {"hot": (0.6, 1.0), "warm": (0.3, 0.7), "cold": (0.0, 0.4)}


class LeadScore(BaseModel):
    band: Literal["hot", "warm", "cold"]
    score: float = Field(ge=0, le=1, description="Secondary numeric indicator within the band.")
    confidence: Confidence
    reasons: list[Reason] = Field(min_length=1, max_length=5)


INSTRUCTIONS = f"""
You are a sales-prioritisation analyst at an insurer. Classify how promising a new lead is
for the owner of the relationship (adviser, broker or direct sales, see channel_owner) to
follow up now: hot (today), warm (this week), cold (nurture only).
Consider purchase intent and engagement (quote requests, pages viewed, callback request,
recency of inquiry), source, application completeness, and whether they are an existing
customer.
Do NOT judge insurability or risk; underwriting is handled separately by rules.
Score ranges: hot 0.6-1.0, warm 0.3-0.7, cold 0.0-0.4.
Use confidence "low" when the signals are sparse or conflicting.
{REASON_GUIDE}
""".strip()


async def score_lead(llm: LLMClient, signals: dict[str, Any], notes: str | None) -> LeadScore:
    return await llm.structured(
        LeadScore,
        purpose=PURPOSE,
        instructions=INSTRUCTIONS,
        task="Classify this lead.",
        data={"signals": signals, "notes": notes},
        validate=lambda r: (
            grounding_errors(r.reasons, signals) + score_band_errors(r.score, r.band, BAND_RANGES)
        ),
    )
