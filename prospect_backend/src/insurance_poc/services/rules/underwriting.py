"""Underwriting referral rules (declarative, from ``rulebook.UNDERWRITING_RULES``).

Outcome precedence: knockout > refer > clear. The system **never declines**: a knock-out
routes the case to an underwriter with the reasons, and only the underwriter decides. The LLM
risk summary adds colour but never changes the outcome.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from insurance_poc import rulebook
from insurance_poc.services.rules.eligibility import ProductLike, eligible_products
from insurance_poc.services.rules.facts import LeadFacts
from insurance_poc.services.rules.types import RuleResult, Severity


class UWOutcome(StrEnum):
    CLEAR = "clear"  # no referral reasons: sales / adviser may quote
    REFER = "refer"  # underwriter must review
    KNOCKOUT = "knockout"  # hard rule hit: underwriter confirms (only a human may decline)


class UnderwritingResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: UWOutcome
    results: list[RuleResult]
    eligible_products: list[str]


def derived_facts(f: LeadFacts) -> dict[str, Any]:
    """Flat view the declarative rules evaluate against."""
    d, year = f.declared, f.as_of.year
    income = d.get("annual_income") if isinstance(d.get("annual_income"), int) else None
    out: dict[str, Any] = {**d, "age": f.age, "sum_insured": f.sum_insured}
    if isinstance(d.get("vehicle_year"), int):
        out["vehicle_age"] = year - d["vehicle_year"]
    if isinstance(d.get("property_year"), int):
        out["property_age"] = year - d["property_year"]
    if income and f.sum_insured:
        out["cover_income_multiple"] = round(f.sum_insured / income, 2)
    out["pre_existing_conditions"] = list(d.get("pre_existing_conditions") or [])
    return out


def matches(cond: dict[str, Any], facts: dict[str, Any]) -> bool:
    if "all" in cond:
        return all(matches(c, facts) for c in cond["all"])
    if "any" in cond:
        return any(matches(c, facts) for c in cond["any"])
    v, op, ref = facts.get(cond["field"]), cond["op"], cond.get("value")
    if op == "is_true":
        return v is True
    if op == "not_empty":
        return bool(v)
    if op == "intersects":
        return bool(set(v or []) & set(ref))
    if op == "eq":
        return v == ref
    if v is None or not isinstance(v, int | float):
        return False  # missing numeric facts never trigger a rule (data quality covers them)
    return {
        "lt": v < ref,
        "lte": v <= ref,
        "gt": v > ref,
        "gte": v >= ref,
    }[op]


def rule_hits(facts: dict[str, Any], line: str | None) -> list[RuleResult]:
    """Referral / knock-out rules from the rulebook that fire for ``line``."""
    rs: list[RuleResult] = []
    for rule in rulebook.UNDERWRITING_RULES:
        if rule["lines"] != "*" and line not in rule["lines"]:
            continue
        if matches(rule["when"], facts):
            sev = Severity.BLOCK if rule["outcome"] == rulebook.UW_KNOCKOUT else Severity.REFER
            rs.append(RuleResult.fail(rule["id"], sev, rule["reason"]))
    return rs


def assess(f: LeadFacts, products: Iterable[ProductLike]) -> UnderwritingResult:
    products = [p for p in products if p.line == f.product_line]
    facts = derived_facts(f)
    rs = rule_hits(facts, f.product_line)

    line_max_si = max((p.max_sum_insured for p in products), default=0)
    if f.sum_insured and line_max_si and f.sum_insured > line_max_si:
        rs.append(
            RuleResult.fail(
                "underwriting.large_risk",
                Severity.REFER,
                "Sum insured above every product limit; manual large-risk review.",
            )
        )

    eligible, _ = eligible_products(f, products)
    has_ko = any(r.severity == Severity.BLOCK for r in rs)
    has_refer = any(r.severity == Severity.REFER for r in rs)
    if not eligible and not has_ko and not has_refer:
        rs.append(
            RuleResult.fail(
                "underwriting.no_eligible_product",
                Severity.BLOCK,
                "No product in the catalogue fits this applicant.",
            )
        )
        has_ko = True

    if has_ko:
        outcome = UWOutcome.KNOCKOUT
    elif has_refer:
        outcome = UWOutcome.REFER
    else:
        outcome = UWOutcome.CLEAR
        rs.append(
            RuleResult.ok("underwriting.referral_rules", "No underwriting referral rules hit.")
        )
    return UnderwritingResult(outcome=outcome, results=rs, eligible_products=eligible)
