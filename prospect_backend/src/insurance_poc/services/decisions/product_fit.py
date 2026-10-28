"""Rank rule-eligible products, explain why the top one suits the applicant, and optionally
suggest products from other lines the rules also allow.

The LLM may only use codes from the lists it is given; anything else fails validation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from insurance_poc.services.decisions.common import (
    STYLE_GUIDE,
    Confidence,
    Reason,
    grounding_errors,
)
from insurance_poc.services.llm.client import LLMClient
from insurance_poc.services.rules.fairness import redact_text

PURPOSE = "product_fit"
MAX_ALSO_SUGGEST = 2
CONFIDENCE_RANGES = {"high": (70, 100), "medium": (40, 85), "low": (0, 55)}


class RankedProduct(BaseModel):
    code: str
    fit: Literal["high", "medium", "low"]
    rationale: str = Field(max_length=300)


class AlsoSuggest(BaseModel):
    code: str
    rationale: str = Field(max_length=300, description="One line: the need this product meets.")
    reasons: list[Reason] = Field(min_length=1, max_length=3)


class Strategy(BaseModel):
    title: str = Field(max_length=70, description="Short name of the marketing angle.")
    how: str = Field(max_length=260, description="What the team should say or do, in plain words.")
    signal: str = Field(description="Exact key of the signal this strategy is based on.")


class ProductRanking(BaseModel):
    ranked: list[RankedProduct] = Field(min_length=1)
    recommended_code: str
    reasons: list[Reason] = Field(
        min_length=1,
        max_length=4,
        description="Why the recommended product suits this applicant, each citing a signal.",
    )
    also_suggest: list[AlsoSuggest] = Field(default_factory=list, max_length=MAX_ALSO_SUGGEST)
    justification: str | None = Field(
        default=None,
        max_length=420,
        description="A short story: why this product is the right one for this customer.",
    )
    explanation: str = Field(max_length=700, description="Plain-language summary for staff.")
    pitch: str = Field(
        max_length=240,
        description="One sentence the sales / marketing team could say to the customer.",
    )
    watch_out: str | None = Field(
        default=None, max_length=240, description="The one thing to check before quoting."
    )
    talking_points: list[Reason] = Field(
        min_length=1,
        max_length=3,
        description="What to lead with, ask or prepare for in the conversation, each citing "
        "the signal it comes from.",
    )
    pain_points: list[Reason] = Field(
        min_length=1,
        max_length=3,
        description="What is likely worrying this customer or in their way, each citing a signal.",
    )
    strategies: list[Strategy] = Field(
        min_length=1,
        max_length=3,
        description="Marketing strategies that speak to those pain points.",
    )
    confidence: Confidence
    confidence_score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="How sure you are that the recommended product is the right one, 0-100.",
    )
    confidence_reason: str | None = Field(
        default=None,
        max_length=220,
        description="One short plain sentence: why you are this sure about the pick.",
    )
    needs_review: bool = Field(description="True if a human should look closely before acting.")
    review_reason: str | None = Field(default=None, max_length=300)


INSTRUCTIONS = (
    """
You help a sales and marketing team (or a broker desk / licensed adviser) decide what to offer a
prospect. Rank ONLY the eligible products provided (every one of them, best fit first) and pick
one to recommend. Base fit on the customer's needs (cover asked for, family, car / home facts,
term, protection gap or savings affordability where given) and the product descriptions.

Write for a marketing colleague, not an underwriter:
- Plain everyday words. Refer to products by their NAME, never by their code.
- No insurance jargon: say "cover amount" not "sum insured", and never use words like
  placement, binding, underwriting appetite, eligibility, dependant eligibility, risk profile.
- Talk about what the customer gets and why it matters to them.

`reasons` (1-4): why the recommended product suits THIS customer, one short sentence each,
starting from the customer's fact (e.g. "Has 2 children, so family cover protects them too").
Each MUST name in `signal` the exact key of the signal it is based on. Do not invent facts.
`justification`: the first thing the reader sees, so write it the way a friendly adviser would
explain it out loud to someone who knows nothing about insurance. One short paragraph, 2-3
natural sentences, at most 50 words, no lists.
- Say it as a little story about the person: who they are, what they want, and why this policy
  is the right answer for them. Example: "Vijay wants AED 1,000,000 of life cover for 5 years.
  He only has part of that covered today, so this plan fills the missing amount, which is why it
  beats the other options."
- Explain every number in words. Always give the currency, and say what it means ("still
  missing AED 700,000 of cover", never just "a 700,000 protection gap").
- No insurance jargon at all: avoid protection gap, sum insured, underwriting, eligibility,
  term, premium, risk profile. Say "cover amount", "how long the plan runs", "what they would
  pay".
- Use the first name if the signals give it, otherwise "they". Contractions are fine.
- Reasonable inference is fine but say it as likely ("probably"), never as fact the signals do
  not show. Do not claim policy features that are not in the product description.
- Never mention or guess religion, nationality, gender or marital status. No prices or promises.
`confidence_score`: a whole number 0-100 for how sure you are that the recommended product is
the right one for this customer. Keep it consistent with `confidence`: high 70-100, medium
40-85, low 0-55. Lower it when facts are missing, borderline or conflicting, or when the next
product is almost as good a fit.
`confidence_reason`: one short plain sentence (at most 25 words) saying why you are that sure
about the pick: what makes it a clear choice, or what holds the confidence back (a fact that is
missing, a borderline answer, or a close second option). No jargon, no codes.
`pitch`: one friendly sentence the team could say to the customer.
`watch_out`: the one thing to check before quoting, in plain words, or null if nothing.
`talking_points` (1-3): how the call with THIS customer could go, written as friendly, natural
sentences the caller can follow, like a colleague talking them through it: "Start by asking
Vijay how long he has been thinking about life cover, then explain that this plan is built for
exactly his situation." One or two sentences each, plain everyday words, in the order the call
would flow (open, explain, check). Use the customer's first name. Say what to talk about and why
it matters to them, and when something needs a gentle question, give the question. Never use
insurance jargon (say "cover amount", not "sum insured"), always give currency with amounts, and
do not repeat the `reasons` word for word. Each MUST name in `signal` the fact it comes from.
Do not say how or when to contact them (the rules decide that).
`pain_points` (1-3): what is likely worrying THIS customer or standing in their way, in plain
words, worked out from their facts (e.g. "A new car is expensive to repair", "Family relies on
one income"). Never use or guess personal traits such as religion, nationality or gender.
Each MUST name in `signal` the exact key of the fact it comes from.
`strategies` (1-3): marketing strategies that speak to those pain points, each with a short
`title` (e.g. "Lead with family security") and `how` (what to say or do, with the benefit to
the customer). Never promise a price, discount, approval or guaranteed outcome, never say how
or when to make contact (the rules decide that) and never pressure. For life and savings
products talk about protection and needs only, never investment returns. Each MUST name in
`signal` the fact it is based on.
`explanation`: 1-2 sentences for the team: what to offer and why, without repeating every reason.
Each product `rationale`: one short line in the same plain style.

`other_products` are products from other lines the customer also qualifies for. In
`also_suggest`, pick at most two ONLY if a fact shows a real need (e.g. children for accident
or life cover); otherwise return an empty list. Each needs a plain one-line rationale and 1-3
grounded reasons. Never suggest a code not in `other_products`.
This is an internal suggestion; an authorised person decides. Set needs_review true when facts
are borderline or conflicting.
""".strip()
    + f"\n{STYLE_GUIDE}"
)


def _texts(r: ProductRanking) -> list[str]:
    out = [r.explanation, r.pitch, r.watch_out or "", r.justification or ""]
    out.append(r.confidence_reason or "")
    out += [x.explanation for x in r.reasons + r.talking_points + r.pain_points]
    out += [p.rationale for p in r.ranked] + [f"{x.title} {x.how}" for x in r.strategies]
    for s in r.also_suggest:
        out += [s.rationale] + [x.explanation for x in s.reasons]
    return out


def validate_ranking(
    r: ProductRanking,
    eligible: list[str],
    signals: dict[str, Any] | None = None,
    others: list[str] | None = None,
) -> list[str]:
    errs: list[str] = []
    codes = [p.code for p in r.ranked]
    if r.confidence_score is not None:
        lo, hi = CONFIDENCE_RANGES[str(r.confidence)]
        if not lo <= r.confidence_score <= hi:
            errs.append(
                f"confidence_score {r.confidence_score} does not match confidence "
                f"'{r.confidence}' (expected {lo}-{hi})"
            )
    unknown = [c for c in codes if c not in eligible]
    if unknown:
        errs.append(f"ranked: codes {unknown} are not eligible; allowed: {eligible}")
    if len(set(codes)) != len(codes):
        errs.append("ranked: duplicate codes")
    if set(codes) != set(eligible) and not unknown:
        errs.append(f"ranked: must rank every eligible product exactly once: {eligible}")
    if r.recommended_code not in codes:
        errs.append("recommended_code must be one of the ranked codes")
    elif r.recommended_code != codes[0]:
        # Everything downstream (UI, next steps, results CSV) treats ranked[0] as the pick.
        errs.append("recommended_code must be the first product in ranked")
    if signals is not None:
        errs += grounding_errors(r.reasons, signals)
        errs += [f"talking_points.{e}" for e in grounding_errors(r.talking_points, signals)]
        errs += [f"pain_points.{e}" for e in grounding_errors(r.pain_points, signals)]
        errs += [
            f"strategies[{i}].signal: '{x.signal}' is not one of the provided signals "
            f"{sorted(signals)}"
            for i, x in enumerate(r.strategies)
            if x.signal not in signals
        ]
    allowed = others or []
    extra = [s.code for s in r.also_suggest]
    bad = [c for c in extra if c not in allowed]
    if bad:
        errs.append(f"also_suggest: codes {bad} are not allowed; allowed: {allowed}")
    if len(set(extra)) != len(extra):
        errs.append("also_suggest: duplicate codes")
    codes_in_text = sorted({c for c in [*eligible, *allowed] if any(c in t for t in _texts(r))})
    if codes_in_text:
        errs.append(f"use product names, not codes, in the text: {codes_in_text}")
    if signals is not None:
        for i, s in enumerate(r.also_suggest):
            errs += [f"also_suggest[{i}].{e}" for e in grounding_errors(s.reasons, signals)]
    return errs


async def rank_products(
    llm: LLMClient,
    *,
    signals: dict[str, Any],
    eligible: list[dict[str, Any]],
    lead_band: str,
    risk_band: str | None,
    uw_outcome: str,
    other_products: list[dict[str, Any]] | None = None,
) -> ProductRanking:
    codes = [p["code"] for p in eligible]
    others = other_products or []
    other_codes = [p["code"] for p in others]
    return await llm.structured(
        ProductRanking,
        purpose=PURPOSE,
        instructions=INSTRUCTIONS,
        task="Rank the eligible products, recommend one with reasons, and suggest any other "
        "products that clearly fit.",
        data={
            "signals": signals,
            # Catalogue text can trip the fairness scan (accident cover mentions "disability").
            "eligible_products": [
                {**p, "description": redact_text(p.get("description"))[0]} for p in eligible
            ],
            "other_products": [
                # No descriptions: catalogue text can trip the fairness scan (e.g. "disability").
                {k: p[k] for k in ("code", "name", "line", "needs_underwriter")}
                for p in others
            ],
            "lead_priority_band": lead_band,
            "risk_band": risk_band,
            "underwriting_outcome": uw_outcome,
        },
        validate=lambda r: validate_ranking(r, codes, signals, other_codes)
        + ([] if (r.justification or "").strip() else ["justification: write the short story"]),
    )
