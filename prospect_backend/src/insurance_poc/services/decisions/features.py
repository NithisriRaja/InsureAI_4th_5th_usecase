"""LLM-safe feature payloads built from an explicit allow-list.

Nothing reaches a decision prompt unless it is listed here. No names, no contact details, no
DOB (age band only), no city/postcode, no protected attributes, no intermediary names. Each
prompt gets only the slice it needs: line-specific facts come from ``rulebook.LINES``.
Free-text notes are redacted and wrapped as untrusted data.
"""

from __future__ import annotations

import re
from typing import Any

from insurance_poc import rulebook
from insurance_poc.config import get_settings
from insurance_poc.services.rules.facts import LeadFacts
from insurance_poc.services.rules.fairness import REDACTED, FairnessReport, redact_text

ENGAGEMENT_ALLOW = (
    "quote_requests_30d",
    "pages_viewed",
    "requested_callback",
    "days_since_inquiry",
)
MAX_NOTES_CHARS = 600
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")


def major(minor: int | None) -> float | None:
    """LLM sees whole currency units; the DB stores minor units (cents)."""
    return None if minor is None else round(minor / 100, 2)


def age_band(age: int | None) -> str | None:
    if age is None:
        return None
    if age < 18:
        return "under_18"
    for lo, hi in ((18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 74)):
        if lo <= age <= hi:
            return f"{lo}-{hi}"
    return "75+"


def lead_signals(f: LeadFacts, checklist: dict[str, Any] | None = None) -> dict[str, Any]:
    """Measurable lead signals; LLM reasons must cite these keys."""
    d = f.declared
    sig: dict[str, Any] = {
        "product_line": f.product_line,
        "channel_owner": f.channel_owner,
        "age_band": age_band(f.age),
        "sum_insured": major(f.sum_insured),
        "currency": get_settings().currency,
        "source": f.source,
        "existing_customer": f.existing_customer,
    }
    for k in ENGAGEMENT_ALLOW:
        if k in d:
            sig[k] = d[k]
    sig.update(line_signals(f, f.product_line))
    if isinstance(d.get("vehicle_year"), int):
        sig["vehicle_age_years"] = f.as_of.year - d["vehicle_year"]
    if isinstance(d.get("property_year"), int):
        sig["property_age_years"] = f.as_of.year - d["property_year"]
    if checklist:
        sig["application_completeness_pct"] = checklist.get("completeness_pct")
        sig["documents_missing_count"] = len(checklist.get("documents_missing") or [])
        needs = checklist.get("needs") or {}
        if needs.get("type") == "protection":
            sig["protection_gap"] = needs["protection_gap"]
        elif needs.get("type") == "savings":
            sig["saving_pct_of_income"] = needs["saving_pct_of_income"]
    return sig


def line_signals(f: LeadFacts, line: str | None) -> dict[str, Any]:
    """Declared facts on ``line``'s allow-list (used for the requested line and for any other
    line the applicant is matched against)."""
    d = f.declared
    spec = rulebook.LINES.get(line or "")
    out: dict[str, Any] = {}
    for k in spec["signals"] if spec else ():
        if k in d:
            v = d[k]
            out[k] = major(v) if k in rulebook.MONEY_FIELDS and isinstance(v, int) else v
    return out


def _strip_contact(f: LeadFacts, text: str | None) -> str | None:
    """Notes are free text: drop the customer's name, emails and phone numbers."""
    if not text:
        return text
    out = _PHONE.sub(REDACTED, _EMAIL.sub(REDACTED, text))
    for name in (f.first_name, f.last_name):
        if name and len(name.strip()) > 1:
            out = re.sub(rf"\b{re.escape(name.strip())}\b", REDACTED, out, flags=re.IGNORECASE)
    return out


def lead_notes(f: LeadFacts) -> tuple[str | None, FairnessReport]:
    redacted, report = redact_text(_strip_contact(f, f.notes))
    if redacted and len(redacted) > MAX_NOTES_CHARS:
        redacted = redacted[:MAX_NOTES_CHARS] + "..."
    return redacted, report
