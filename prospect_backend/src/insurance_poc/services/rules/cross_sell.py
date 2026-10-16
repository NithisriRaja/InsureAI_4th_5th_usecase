"""Cross-line matching: products from *other* lines the applicant also qualifies for.

The requested line stays the main recommendation. Another line's product is a candidate only
when the rules can actually assess it from facts already on the lead:

- the line's required declared fields (``rulebook.LINES[...]["required"]``) are all present;
- individual and company applicants never cross (employee benefits stay with companies);
- a broker / employer-owned relationship only gets products that owner can sell (the broker is
  never bypassed); otherwise the line's own non-intermediary owner sells it (e.g. an adviser);
- the product's eligibility rules pass, except the cover amount: the requested sum insured
  belongs to the main line, so cover for a suggestion is agreed later;
- no knock-out rule fires for that line. A referral keeps it, flagged for an underwriter.

The LLM may only suggest codes returned here.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict

from insurance_poc import rulebook
from insurance_poc.enums import INTERMEDIARY_OWNERS
from insurance_poc.services.rules.eligibility import ProductLike, check_product, who
from insurance_poc.services.rules.facts import LeadFacts
from insurance_poc.services.rules.types import Severity
from insurance_poc.services.rules.underwriting import derived_facts, rule_hits

# Eligibility checks that depend on the cover amount, which is not chosen yet for a suggestion.
COVER_DEPENDENT = ("eligibility.sum_insured", "eligibility.cover_income_multiple")


class CrossLineCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    line: str
    channel_owner: str
    needs_underwriter: bool
    referral_reasons: list[str]


def _owner_for(f: LeadFacts, p: ProductLike) -> str | None:
    channels = [str(c) for c in p.channels or []]
    if f.channel_owner in INTERMEDIARY_OWNERS:
        return f.channel_owner if f.channel_owner in channels else None
    if not channels or f.channel_owner in channels:
        return f.channel_owner
    line_owners = [str(o) for o in rulebook.LINES[p.line]["owners"]]
    return next(
        (o for o in line_owners if o in channels and o not in INTERMEDIARY_OWNERS),
        None,
    )


class OtherLineCheck(BaseModel):
    """Result of matching one other-line product: a candidate, or why it is not one."""

    model_config = ConfigDict(frozen=True)

    status: str  # eligible | not_suitable | not_assessed
    reasons: list[str]
    candidate: CrossLineCandidate | None = None


def check_other_line(f: LeadFacts, p: ProductLike) -> OtherLineCheck:
    line = rulebook.LINES[p.line]
    if (p.line in rulebook.COMPANY_LINES) != (f.product_line in rulebook.COMPANY_LINES):
        why = (
            "Employee-benefit scheme for companies, not individuals."
            if p.line in rulebook.COMPANY_LINES
            else "Personal product; this applicant is a company."
        )
        return OtherLineCheck(status="not_suitable", reasons=[why])
    owner = _owner_for(f, p)
    if owner is None:
        sold = who(p.channels or [])
        return OtherLineCheck(
            status="not_suitable",
            reasons=[
                f"Only {sold} can sell this, and this customer is handled by their "
                f"{f.channel_owner}."
            ],
        )
    missing = [k for k in line["required"] if f.declared.get(k) is None]
    if missing:
        fields = ", ".join(k.replace("_", " ") for k in missing)
        return OtherLineCheck(status="not_assessed", reasons=[f"Not known yet: {fields}."])
    as_line = f.model_copy(update={"product_line": p.line, "channel_owner": owner})
    fails = [r.reason for r in check_product(as_line, p).failures if r.id not in COVER_DEPENDENT]
    if fails:
        return OtherLineCheck(status="not_suitable", reasons=fails)
    hits = rule_hits(derived_facts(as_line.model_copy(update={"sum_insured": None})), p.line)
    if any(r.severity == Severity.BLOCK for r in hits):
        return OtherLineCheck(status="not_suitable", reasons=[r.reason for r in hits])
    return OtherLineCheck(
        status="eligible",
        reasons=[],
        candidate=CrossLineCandidate(
            code=p.code,
            line=p.line,
            channel_owner=owner,
            needs_underwriter=bool(hits),
            referral_reasons=[r.reason for r in hits],
        ),
    )


def candidates(f: LeadFacts, products: Iterable[ProductLike]) -> list[CrossLineCandidate]:
    out: list[CrossLineCandidate] = []
    for p in products:
        if p.line not in rulebook.LINES or p.line == f.product_line:
            continue
        found = check_other_line(f, p).candidate
        if found is not None:
            out.append(found)
    return out


def signal_lines(found: Iterable[CrossLineCandidate]) -> list[str]:
    """Lines whose allow-listed facts the LLM needs to judge the suggestions."""
    return sorted({c.line for c in found})


def describe(c: CrossLineCandidate, summary: dict[str, Any]) -> dict[str, Any]:
    """Candidate as the LLM and the reviewer see it: product summary plus routing facts."""
    return {
        **summary,
        "line": c.line,
        "sold_through": c.channel_owner,
        "needs_underwriter": c.needs_underwriter,
        "referral_reasons": c.referral_reasons,
    }
