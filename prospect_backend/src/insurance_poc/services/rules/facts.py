"""Facts = the only inputs hard rules and LLM feature builders may see.

Built from ORM rows by ``lead_facts``. They deliberately carry **no
protected attributes** (gender, religion, nationality, ...) and no city/postcode; a unit test
asserts this so a future field can't sneak in.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from insurance_poc.db.models import Lead
from insurance_poc.services.rules.routing import resolve_lead_owner


def age_at(dob: date | None, as_of: date) -> int | None:
    if dob is None:
        return None
    years = as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))
    return years


class LeadFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    lead_id: str
    as_of: date
    product_line: str | None
    first_name: str | None
    last_name: str | None
    dob: date | None
    age: int | None
    email: str | None
    phone: str | None
    sum_insured: int | None
    declared: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    source: str = "web"
    channel_owner: str = "direct"
    documents_provided: list[str] = Field(default_factory=list)
    consent_profiling: bool = True
    consent_marketing: bool = False
    consent_email: bool = False
    consent_sms: bool = False
    existing_customer: bool = False


def lead_facts(lead: Lead, as_of: date) -> LeadFacts:
    return LeadFacts(
        lead_id=lead.id,
        as_of=as_of,
        product_line=lead.product_line,
        first_name=lead.first_name,
        last_name=lead.last_name,
        dob=lead.dob,
        age=age_at(lead.dob, as_of),
        email=lead.email,
        phone=lead.phone,
        sum_insured=lead.sum_insured_requested,
        declared=dict(lead.declared or {}),
        notes=lead.notes,
        source=lead.source,
        channel_owner=resolve_lead_owner(lead.product_line, lead.source, lead.channel_owner),
        documents_provided=list(lead.documents_provided or []),
        consent_profiling=lead.consent_profiling is not False,
        consent_marketing=lead.consent_marketing,
        consent_email=lead.consent_email,
        consent_sms=lead.consent_sms,
        existing_customer=lead.existing_customer_id is not None,
    )
