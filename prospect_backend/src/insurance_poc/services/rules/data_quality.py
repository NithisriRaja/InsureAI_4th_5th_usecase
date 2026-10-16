"""Mandatory fields and format checks for leads. Failures produce a ``missing_info`` list.

Line-specific required fields come from ``rulebook.LINES``. Company lines (employee
benefits) have no personal date of birth.
"""

from __future__ import annotations

from typing import Any

from email_validator import EmailNotValidError, validate_email

from insurance_poc import rulebook
from insurance_poc.services.rules.facts import LeadFacts
from insurance_poc.services.rules.types import RuleResult, Severity
from insurance_poc.utils.normalize import norm_phone

MAX_AGE_YEARS = 110


def _missing(field: str, reason: str) -> dict[str, str]:
    return {"field": field, "reason": reason}


def check_lead_data(f: LeadFacts) -> tuple[list[RuleResult], list[dict[str, Any]]]:
    """Returns (rule results, missing_info). Any failure here is BLOCK -> request_info."""
    missing: list[dict[str, Any]] = []

    for field in ("first_name", "last_name"):
        if not (getattr(f, field) or "").strip():
            missing.append(_missing(field, "required"))

    if f.product_line not in rulebook.LINES:
        missing.append(_missing("product_line", "required: " + "|".join(rulebook.LINES)))

    if f.product_line not in rulebook.COMPANY_LINES:
        if f.dob is None:
            missing.append(_missing("dob", "required"))
        elif f.dob > f.as_of:
            missing.append(_missing("dob", "date of birth is in the future"))
        elif f.age is not None and f.age > MAX_AGE_YEARS:
            missing.append(_missing("dob", f"implausible age {f.age}"))

    if not f.email and not f.phone:
        missing.append(_missing("email|phone", "at least one contact detail required"))
    if f.email:
        try:
            validate_email(f.email, check_deliverability=False)
        except EmailNotValidError:
            missing.append(_missing("email", "invalid format"))
    if f.phone:
        digits = norm_phone(f.phone) or ""
        if not 7 <= len(digits) <= 15:
            missing.append(_missing("phone", "invalid format"))

    if f.sum_insured is None or f.sum_insured <= 0:
        missing.append(_missing("sum_insured", "required, must be positive"))

    line = rulebook.LINES.get(f.product_line or "")
    for field in line["required"] if line else ():
        if f.declared.get(field) is None:
            missing.append(_missing(f"declared.{field}", "required for this line"))

    for field in ("vehicle_year", "property_year"):
        year = f.declared.get(field)
        if isinstance(year, int) and year > f.as_of.year + 1:
            missing.append(_missing(f"declared.{field}", "year is in the future"))

    if missing:
        result = RuleResult.fail(
            "data_quality.lead",
            Severity.BLOCK,
            f"{len(missing)} missing or invalid field(s).",
            fields=[m["field"] for m in missing],
        )
    else:
        result = RuleResult.ok("data_quality.lead", "All mandatory fields present and valid.")
    return [result], missing
