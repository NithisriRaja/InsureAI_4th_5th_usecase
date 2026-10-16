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
`pitch`: one friendly sentence the team could say to the customer.
`watch_out`: the one thing to check before quoting, in plain words, or null if nothing.
`talking_points` (1-3): a plan for the conversation with THIS customer, as short instructions
for the caller: what to lead with, a question worth asking, or a concern to be ready for (e.g.
"Open with the agency-repair option: their car is only 3 years old"). Each MUST name in
`signal` the fact it comes from. Do not say how or when to contact them (the rules decide that)
and do not repeat the `reasons` word for word.
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
    out = [r.explanation, r.pitch, r.watch_out or ""]
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
        validate=lambda r: validate_ranking(r, codes, signals, other_codes),
    )
