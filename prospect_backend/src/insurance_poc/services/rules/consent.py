"""Purpose, consent and channel gates.

- Profiling: a lead may be scored at all only if its source allows profiling and the record
  carries profiling consent (purpose limitation). Otherwise: do not contact, no LLM.
- Prospects: contacting a lead is marketing. Direct / adviser-owned leads need marketing
  consent AND a consented channel. Broker / employer-owned leads are contacted through the
  intermediary (a task to them), never directly.
"""

from __future__ import annotations

from typing import Literal

from insurance_poc import rulebook
from insurance_poc.enums import Channel
from insurance_poc.services.rules.facts import LeadFacts
from insurance_poc.services.rules.routing import owns_via_intermediary
from insurance_poc.services.rules.types import RuleResult, Severity

Purpose = Literal["marketing", "service"]


def allowed_channels(
    *,
    purpose: Purpose,
    consent_marketing: bool,
    consent_email: bool,
    consent_sms: bool,
    has_email: bool,
    has_phone: bool,
) -> list[Channel]:
    if purpose == "marketing" and not consent_marketing:
        return []
    out: list[Channel] = []
    if consent_email and has_email:
        out.append(Channel.EMAIL)
    if consent_sms and has_phone:
        out.append(Channel.SMS)
    if len(out) == 2:  # both consented: may also reach out on both at once
        out.append(Channel.EMAIL_SMS)
    return out


def lead_channels(f: LeadFacts) -> list[Channel]:
    if owns_via_intermediary(f.channel_owner):
        return [Channel.INTERMEDIARY]
    return allowed_channels(
        purpose="marketing",
        consent_marketing=f.consent_marketing,
        consent_email=f.consent_email,
        consent_sms=f.consent_sms,
        has_email=bool(f.email),
        has_phone=bool(f.phone),
    )


def check_lead_permission(f: LeadFacts) -> RuleResult:
    """May this record be profiled / scored at all? Checked before anything else."""
    src = rulebook.SOURCES.get(f.source)
    if src is not None and not src["profiling_allowed"]:
        return RuleResult.fail(
            "consent.source_permission",
            Severity.BLOCK,
            f"Source '{f.source}' is not an approved purpose for profiling.",
        )
    if not f.consent_profiling:
        return RuleResult.fail(
            "consent.profiling", Severity.BLOCK, "No consent to use this data for profiling."
        )
    return RuleResult.ok("consent.profiling", "Data may be used for profiling.")


def check_lead_consent(f: LeadFacts) -> RuleResult:
    """Outreach consent, given the relationship owner."""
    if owns_via_intermediary(f.channel_owner):
        return RuleResult.ok(
            "consent.intermediary",
            f"{f.channel_owner.capitalize()}-owned lead: follow-up goes through the "
            f"{f.channel_owner}.",
            channels=[Channel.INTERMEDIARY.value],
        )
    if not f.consent_marketing:
        return RuleResult.fail(
            "consent.marketing", Severity.BLOCK, "Lead has not given marketing consent."
        )
    channels = lead_channels(f)
    if not channels:
        return RuleResult.fail(
            "consent.channel",
            Severity.BLOCK,
            "No contact channel with consent (email/SMS) and a matching contact detail.",
        )
    return RuleResult.ok(
        "consent.marketing", "Marketing consent present.", channels=[c.value for c in channels]
    )
