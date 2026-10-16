"""Product eligibility: which catalogue products a lead may be offered at all.

Conditions are the product's ``rules`` dict (``rule_*`` columns of products.csv); every failure
carries a rule id. The LLM may only rank products returned as eligible here.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from insurance_poc.config import get_settings
from insurance_poc.services.rules.facts import LeadFacts
from insurance_poc.services.rules.types import RuleResult, Severity


class ProductLike(Protocol):
    code: str
    line: str
    name: str
    min_age: int
    max_age: int
    min_sum_insured: int
    max_sum_insured: int
    rules: dict[str, Any]
    channels: list[Any]


class ProductEligibility(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    eligible: bool
    failures: list[RuleResult]


def _years_since(year: Any, as_of_year: int) -> int | None:
    return as_of_year - year if isinstance(year, int) else None


def check_product(f: LeadFacts, p: ProductLike) -> ProductEligibility:
    fails: list[RuleResult] = []

    def fail(rule: str, reason: str) -> None:
        fails.append(RuleResult.fail(f"eligibility.{rule}", Severity.BLOCK, reason, product=p.code))

    r, d = p.rules or {}, f.declared
    if f.product_line != p.line:
        fail("line", f"{p.name} is a {p.line.replace('_', ' ')} product.")
    if p.channels and f.channel_owner not in p.channels:
        sold = who(p.channels)
        fail(
            "channel",
            f"Only {sold} can sell this, and this customer is handled by their {f.channel_owner}.",
        )
    if not r.get("group_scheme") and (f.age is None or not p.min_age <= f.age <= p.max_age):
        fail("age", f"Aged {f.age}: the product covers ages {p.min_age} to {p.max_age}.")
    if f.sum_insured is None or not p.min_sum_insured <= f.sum_insured <= p.max_sum_insured:
        fail(
            "sum_insured",
            f"Asked for {_amount(f.sum_insured)} of cover: the product offers "
            f"{_amount(p.min_sum_insured)} to {_amount(p.max_sum_insured)}.",
        )

    vehicle_age = _years_since(d.get("vehicle_year"), f.as_of.year)
    property_age = _years_since(d.get("property_year"), f.as_of.year)
    term = int(d.get("term_years") or 0)
    term_end_age = f.age + term if f.age is not None else None
    income = d.get("annual_income") if isinstance(d.get("annual_income"), int) else None

    if "max_vehicle_age" in r and vehicle_age is not None and vehicle_age > r["max_vehicle_age"]:
        fail(
            "vehicle_age",
            f"Car is {vehicle_age} years old: accepted up to {r['max_vehicle_age']}.",
        )
    if "min_driving_years" in r and (d.get("driving_years") or 0) < r["min_driving_years"]:
        fail(
            "driving_years",
            f"Has driven for {d.get('driving_years') or 0} years: needs at least "
            f"{r['min_driving_years']}.",
        )
    if (
        "max_property_age" in r
        and property_age is not None
        and property_age > r["max_property_age"]
    ):
        fail(
            "property_age",
            f"Home is {property_age} years old: accepted up to {r['max_property_age']}.",
        )
    if "min_dependents" in r and (d.get("dependents") or 0) < r["min_dependents"]:
        fail(
            "dependents",
            f"Has {d.get('dependents') or 0} dependant(s): needs at least {r['min_dependents']}.",
        )
    if r.get("non_smoker_only") and d.get("smoker") is not False:
        fail("non_smoker", "For non-smokers only.")
    if "min_term_years" in r and term < r["min_term_years"]:
        fail("term", f"Plan of {term} years: needs at least {r['min_term_years']}.")
    if (
        "max_term_end_age" in r
        and term_end_age is not None
        and term_end_age > r["max_term_end_age"]
    ):
        fail(
            "term_end_age",
            f"Plan would end at age {term_end_age}: must end by {r['max_term_end_age']}.",
        )
    if (
        "max_cover_income_multiple" in r
        and income
        and f.sum_insured is not None
        and f.sum_insured > income * r["max_cover_income_multiple"]
    ):
        fail(
            "cover_income_multiple",
            f"Cover is more than {r['max_cover_income_multiple']} times their yearly income.",
        )
    if "min_employees" in r and (d.get("employee_count") or 0) < r["min_employees"]:
        fail(
            "employees",
            f"{d.get('employee_count') or 0} staff: the scheme needs at least "
            f"{r['min_employees']}.",
        )

    return ProductEligibility(code=p.code, eligible=not fails, failures=fails)


WHO = {
    "adviser": "advisers",
    "broker": "brokers",
    "direct": "our direct team",
    "employer": "employers",
}


def who(channels: Any) -> str:
    """'advisers', 'brokers or our direct team': who is allowed to sell a product."""
    return " or ".join(WHO.get(str(c), str(c)) for c in channels)


def _amount(minor: int | None) -> str:
    return "?" if minor is None else f"{get_settings().currency} {minor / 100:,.0f}"


OWNER_SELLS = {
    "broker": "Their broker can sell this product",
    "employer": "It is offered through their employer",
    "adviser": "A licensed adviser can arrange it",
    "direct": "We can sell it to them directly",
}


def evidence(f: LeadFacts, p: ProductLike, *, cover_checked: bool = True) -> list[str]:
    """The checks a product passed for this applicant, as plain sentences with their values."""
    r, d = p.rules or {}, f.declared
    out: list[str] = []
    if r.get("group_scheme"):
        out.append("A company scheme for staff, and this applicant is a company")
    elif f.age is not None:
        out.append(f"Aged {f.age}: the product covers ages {p.min_age} to {p.max_age}")
    if cover_checked and f.sum_insured is not None:
        out.append(
            f"Asked for {_amount(f.sum_insured)} of cover: the product offers "
            f"{_amount(p.min_sum_insured)} to {_amount(p.max_sum_insured)}"
        )
    out.append(OWNER_SELLS.get(f.channel_owner, f"Sold through {f.channel_owner}"))
    vehicle_age = _years_since(d.get("vehicle_year"), f.as_of.year)
    property_age = _years_since(d.get("property_year"), f.as_of.year)
    term = int(d.get("term_years") or 0)
    if "max_vehicle_age" in r and vehicle_age is not None:
        out.append(f"Car is {vehicle_age} years old: accepted up to {r['max_vehicle_age']}")
    if "min_driving_years" in r:
        out.append(
            f"Has driven for {d.get('driving_years') or 0} years: "
            f"needs at least {r['min_driving_years']}"
        )
    if "max_property_age" in r and property_age is not None:
        out.append(f"Home is {property_age} years old: accepted up to {r['max_property_age']}")
    if "min_dependents" in r:
        out.append(
            f"Has {d.get('dependents') or 0} dependant(s): needs at least {r['min_dependents']}"
        )
    if "min_term_years" in r:
        out.append(f"Plan of {term} years: needs at least {r['min_term_years']}")
    if "max_term_end_age" in r and f.age is not None:
        out.append(f"Plan ends at age {f.age + term}: must end by {r['max_term_end_age']}")
    if "min_employees" in r:
        out.append(
            f"{d.get('employee_count') or 0} staff: the scheme needs at least {r['min_employees']}"
        )
    return out


def eligible_products(
    f: LeadFacts, products: Iterable[ProductLike]
) -> tuple[list[str], list[ProductEligibility]]:
    checks = [check_product(f, p) for p in products if p.line == f.product_line]
    return [c.code for c in checks if c.eligible], checks
