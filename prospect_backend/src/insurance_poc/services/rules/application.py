"""Application preparation (UC4): completeness, evidence checklist and needs review.

Nothing here blocks or decides. It produces the checklist an adviser, broker or sales
colleague works through before quoting, and that the underwriter sees with the referral.
It complements the insurer's own quote / application tools; it never replaces them.
"""

from __future__ import annotations

from typing import Any

from insurance_poc import rulebook
from insurance_poc.enums import Line
from insurance_poc.services.rules.facts import LeadFacts
from insurance_poc.services.rules.types import RuleResult, Severity


def _major(minor: int | None) -> float | None:
    return None if minor is None else round(minor / 100, 2)


def evidence_requirements(f: LeadFacts) -> list[dict[str, Any]]:
    """Medical / financial evidence for life cover, from the rulebook bands."""
    if f.product_line != Line.LIFE:
        return []
    out = []
    si = f.sum_insured or 0
    for band in rulebook.MEDICAL_REQUIREMENTS:
        by_age = band["min_age"] is not None and f.age is not None and f.age >= band["min_age"]
        if by_age or si >= band["min_sum_insured"]:
            out.extend({"item": item, "rule": band["id"]} for item in band["items"])
    return out


def needs_review(f: LeadFacts) -> dict[str, Any]:
    """Adviser-led lines only: protection gap and savings affordability (no advice given)."""
    d = f.declared
    income = d.get("annual_income") if isinstance(d.get("annual_income"), int) else None
    if f.product_line == Line.LIFE and income:
        need = income * rulebook.PROTECTION_NEED_INCOME_MULTIPLE
        existing = int(d.get("existing_cover") or 0)
        return {
            "type": "protection",
            "protection_need": _major(need),
            "existing_cover": _major(existing),
            "protection_gap": _major(max(0, need - existing)),
            "requested_cover": _major(f.sum_insured),
            "rule": "needs.protection_gap",
        }
    if f.product_line == Line.SAVINGS and income and f.sum_insured:
        years = max(1, int(d.get("term_years") or 1))
        yearly = f.sum_insured / years
        pct = round(yearly / income * 100, 1)
        return {
            "type": "savings",
            "goal": d.get("savings_goal"),
            "target_amount": _major(f.sum_insured),
            "term_years": years,
            "implied_yearly_saving": _major(round(yearly)),
            "saving_pct_of_income": pct,
            "affordable": pct <= rulebook.SAVINGS_AFFORDABILITY_MAX_PCT,
            "rule": "needs.savings_affordability",
        }
    return {}


def prepare(f: LeadFacts) -> tuple[dict[str, Any], list[RuleResult]]:
    line = rulebook.LINES.get(f.product_line or "")
    required_docs = list(line["documents"]) if line else []
    provided = set(f.documents_provided)
    missing_docs = [d for d in required_docs if d not in provided]
    required_fields = list(line["required"]) if line else []
    have_fields = sum(f.declared.get(k) is not None for k in required_fields)
    total = len(required_docs) + len(required_fields)
    held = have_fields + len(required_docs) - len(missing_docs)
    completeness = round(held / total * 100) if total else 100
    evidence = evidence_requirements(f)
    needs = needs_review(f)

    results: list[RuleResult] = []
    if missing_docs:
        results.append(
            RuleResult.fail(
                "application.documents",
                Severity.WARN,
                f"{len(missing_docs)} application document(s) still to collect.",
                missing=missing_docs,
            )
        )
    else:
        results.append(RuleResult.ok("application.documents", "All application documents held."))
    if needs.get("type") == "savings" and not needs["affordable"]:
        results.append(
            RuleResult.fail(
                "suitability.affordability",
                Severity.WARN,
                f"Planned saving is {needs['saving_pct_of_income']}% of income "
                f"(guide: <= {rulebook.SAVINGS_AFFORDABILITY_MAX_PCT}%); adviser to review.",
            )
        )
    checklist = {
        "completeness_pct": completeness,
        "documents_required": required_docs,
        "documents_missing": missing_docs,
        "evidence_required": evidence,
        "needs": needs,
    }
    return checklist, results
