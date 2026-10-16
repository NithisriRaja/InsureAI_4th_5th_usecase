"""Shared string enums used by DB models, rules, graph and API."""

from __future__ import annotations

from enum import StrEnum


class Line(StrEnum):
    # General insurance (broker + direct distribution)
    MOTOR = "motor"
    MEDICAL = "medical"
    HOME = "home"
    PERSONAL_ACCIDENT = "personal_accident"
    # Life, savings (adviser-led, regulated advice)
    LIFE = "life"
    SAVINGS = "savings"
    # Employee benefits (broker / employer; the applicant is a company)
    GROUP = "group"


class ChannelOwner(StrEnum):
    """Who owns the customer relationship. Outreach must go through the owner."""

    ADVISER = "adviser"
    BROKER = "broker"
    DIRECT = "direct"
    EMPLOYER = "employer"


INTERMEDIARY_OWNERS = (ChannelOwner.BROKER, ChannelOwner.EMPLOYER)


class PaymentFrequency(StrEnum):
    ANNUAL = "annual"
    MONTHLY = "monthly"
    SINGLE = "single"


class UseCase(StrEnum):
    ACQUISITION = "acquisition"


class SubjectType(StrEnum):
    LEAD = "lead"


class LeadStatus(StrEnum):
    NEW = "new"
    PROCESSING = "processing"
    RECOMMENDED = "recommended"
    DECIDED = "decided"
    FAILED = "failed"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


ACTIVE_RUN_STATUSES = (RunStatus.QUEUED, RunStatus.RUNNING)
TERMINAL_RUN_STATUSES = (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.SKIPPED)


class BatchKind(StrEnum):
    LEAD_BULK = "lead_bulk"
    LEAD_RUN_ALL = "lead_run_all"  # "Run all" on existing prospects


class RecStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class Decision(StrEnum):
    APPROVED = "approved"
    APPROVED_WITH_EDITS = "approved_with_edits"
    REJECTED = "rejected"


class Queue(StrEnum):
    SALES = "sales"  # direct + broker desk
    ADVISER = "adviser"  # adviser-led relationships, regulated advice
    UNDERWRITING = "underwriting"


class Role(StrEnum):
    SALES = "sales"
    ADVISER = "adviser"
    UNDERWRITER = "underwriter"
    ADMIN = "admin"


class Priority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Channel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    EMAIL_SMS = "email_sms"  # both email and SMS
    INTERMEDIARY = "intermediary"  # task to the owning broker / employer contact


class Action(StrEnum):
    # The agent never declines: knock-outs are referred to an underwriter.
    CONTACT_AND_QUOTE = "contact_and_quote"
    REFER_TO_UNDERWRITER = "refer_to_underwriter"
    REQUEST_INFO = "request_info"
    DO_NOT_CONTACT = "do_not_contact"
    NURTURE = "nurture"
