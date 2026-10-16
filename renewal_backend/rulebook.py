"""The rulebook: every business parameter the POC decides with, as data.

One book of business that mixes two distribution models:

- **General insurance** (motor, medical, home, personal accident): sold direct or through
  brokers, fixed one-year terms, retention runs on **expiry-driven renewals**. A broker may
  own the customer relationship, in which case outreach goes to the broker, not the customer.
- **Life, savings and employee benefits**: adviser-led, retention runs on **premium
  continuation, scheduled reviews and milestones** (no annual expiry). Product suggestions
  are regulated advice and are approved by an adviser.

Rule code (``services/rules``) reads these tables; it holds no thresholds of its own. Every
rule has a stable id that recommendations cite. Values marked ``placeholder`` are POC
assumptions to be replaced by the insurer's approved rules.
"""

from __future__ import annotations

from typing import Any

from renewal_backend.enums import (
    Action,
    ChannelOwner,
    LifecycleType,
    Line,
    PaymentFrequency,
    Queue,
    Trigger,
)

RULEBOOK_VERSION = "2026.10-poc.2"

K = 100  # major -> minor units


def money(major: int) -> int:
    return major * K


# ------------------------------------------------------------------ lines ---
# family: general | life | group. ``owners`` = relationship owners that may hold the line.

LINES: dict[str, dict[str, Any]] = {
    Line.MOTOR: {
        "label": "Motor",
        "family": "general",
        "owners": (ChannelOwner.BROKER, ChannelOwner.DIRECT),
    },
    Line.MEDICAL: {
        "label": "Medical",
        "family": "general",
        "owners": (ChannelOwner.BROKER, ChannelOwner.DIRECT),
    },
    Line.HOME: {
        "label": "Home",
        "family": "general",
        "owners": (ChannelOwner.BROKER, ChannelOwner.DIRECT),
    },
    Line.PERSONAL_ACCIDENT: {
        "label": "Personal accident",
        "family": "general",
        "owners": (ChannelOwner.BROKER, ChannelOwner.DIRECT),
    },
    Line.LIFE: {
        "label": "Life & protection",
        "family": "life",
        "owners": (ChannelOwner.ADVISER,),
    },
    Line.SAVINGS: {
        "label": "Savings & wealth",
        "family": "life",
        "owners": (ChannelOwner.ADVISER,),
    },
    Line.GROUP: {
        "label": "Employee benefits",
        "family": "group",
        "owners": (ChannelOwner.BROKER, ChannelOwner.EMPLOYER),
    },
}


# ------------------------------------------------------------- relationships ---
# Broker-owned relationships: may the insurer message the customer directly? (pilot: no)
BROKER_DIRECT_CONTACT_ALLOWED = False


# ------------------------------------------------------------- catalogue ---
# ``min_age`` / ``max_age`` gate add-on suggestions; ``add_ons`` = extra cover offerable at
# renewal; ``max_discount_pct`` caps retention offers.
# ``verified``: public_page | supplied_list | placeholder (no product here is client-confirmed).

PRODUCTS: list[dict[str, Any]] = [
    # --- motor
    dict(
        code="MOTOR_TPL",
        line=Line.MOTOR,
        name="Motor Third Party Liability",
        tier="basic",
        description="UAE-compulsory cover for injury to others and damage to their property, with"
        " third-party property damage up to AED 2,000,000.",
        min_age=18,
        max_age=80,
        min_sum_insured=money(1_000_000),
        max_sum_insured=money(2_000_000),
        base_premium=money(850),
        max_discount_pct=10,
        lifecycle_type=LifecycleType.EXPIRY_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.DIRECT],
        grace_days=0,
        regulated=False,
        add_ons=["PA_INDIVIDUAL"],
    ),
    dict(
        code="MOTOR_COMPREHENSIVE",
        line=Line.MOTOR,
        name="Motor Comprehensive",
        tier="premium",
        description="Own damage, theft, fire and third-party liability, with agency or premier-"
        "garage repair and UAE-wide roadside assistance.",
        min_age=18,
        max_age=75,
        min_sum_insured=money(20_000),
        max_sum_insured=money(800_000),
        base_premium=money(1_800),
        max_discount_pct=15,
        lifecycle_type=LifecycleType.EXPIRY_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.DIRECT],
        grace_days=0,
        regulated=False,
        add_ons=["PA_INDIVIDUAL"],
    ),
    # --- medical
    dict(
        code="MEDICAL_ESSENTIAL",
        line=Line.MEDICAL,
        name="Essential Health Plan",
        tier="basic",
        description="Basic health cover meeting the Dubai Essential Benefits Plan, annual limit "
        "AED 150,000 within a restricted network.",
        min_age=18,
        max_age=65,
        min_sum_insured=money(150_000),
        max_sum_insured=money(250_000),
        base_premium=money(950),
        max_discount_pct=5,
        lifecycle_type=LifecycleType.EXPIRY_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.DIRECT],
        grace_days=30,
        regulated=False,
        add_ons=["PA_INDIVIDUAL"],
    ),
    dict(
        code="MEDICAL_FAMILY",
        line=Line.MEDICAL,
        name="Enhanced Family Health Plan",
        tier="premium",
        description="Family health cover with a wide UAE network, out-patient, maternity and "
        "dental benefits, annual limit up to AED 5,000,000.",
        min_age=18,
        max_age=65,
        min_sum_insured=money(1_000_000),
        max_sum_insured=money(5_000_000),
        base_premium=money(12_000),
        max_discount_pct=12,
        lifecycle_type=LifecycleType.EXPIRY_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.DIRECT],
        grace_days=30,
        regulated=False,
        add_ons=["PA_INDIVIDUAL"],
    ),
    # --- home
    dict(
        code="HOME_CONTENTS",
        line=Line.HOME,
        name="Home Contents Insurance",
        tier="basic",
        description="Contents and personal belongings for tenants and owners against fire, theft,"
        " water damage and accidental damage.",
        min_age=18,
        max_age=85,
        min_sum_insured=money(50_000),
        max_sum_insured=money(750_000),
        base_premium=money(450),
        max_discount_pct=10,
        lifecycle_type=LifecycleType.EXPIRY_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.DIRECT],
        grace_days=15,
        regulated=False,
        add_ons=[],
    ),
    dict(
        code="HOME_BUILDINGS_CONTENTS",
        line=Line.HOME,
        name="Home Buildings & Contents Insurance",
        tier="premium",
        description="Building and contents cover for owner-occupied villas and apartments, "
        "including alternative accommodation.",
        min_age=21,
        max_age=85,
        min_sum_insured=money(500_000),
        max_sum_insured=money(8_000_000),
        base_premium=money(1_800),
        max_discount_pct=15,
        lifecycle_type=LifecycleType.EXPIRY_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.DIRECT],
        grace_days=15,
        regulated=False,
        add_ons=[],
    ),
    # --- personal accident (standalone and as add-on cover)
    dict(
        code="PA_INDIVIDUAL",
        line=Line.PERSONAL_ACCIDENT,
        name="Personal Accident Cover",
        tier="standard",
        description="Lump sum for accidental death or permanent disability, worldwide, 24 hours a"
        " day.",
        min_age=18,
        max_age=65,
        min_sum_insured=money(100_000),
        max_sum_insured=money(2_000_000),
        base_premium=money(300),
        max_discount_pct=10,
        lifecycle_type=LifecycleType.EXPIRY_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.DIRECT],
        grace_days=15,
        regulated=False,
        add_ons=[],
    ),
    # --- life & protection (adviser-led)
    dict(
        code="LIFE_TERM",
        line=Line.LIFE,
        name="Term Life Protection",
        tier="standard",
        description="Level life cover for a fixed term of 10 to 30 years; pays a lump sum on "
        "death or terminal illness.",
        min_age=18,
        max_age=60,
        min_sum_insured=money(250_000),
        max_sum_insured=money(10_000_000),
        base_premium=money(1_500),
        max_discount_pct=0,
        lifecycle_type=LifecycleType.PREMIUM_CONTINUATION,
        payment_frequency=PaymentFrequency.MONTHLY,
        channels=[ChannelOwner.ADVISER],
        grace_days=30,
        regulated=True,
        add_ons=["LIFE_CRITICAL_ILLNESS"],
    ),
    dict(
        code="LIFE_CRITICAL_ILLNESS",
        line=Line.LIFE,
        name="Critical Illness Protection",
        tier="standard",
        description="Lump sum on first diagnosis of a listed critical illness such as cancer, "
        "heart attack or stroke.",
        min_age=18,
        max_age=55,
        min_sum_insured=money(100_000),
        max_sum_insured=money(3_000_000),
        base_premium=money(1_200),
        max_discount_pct=0,
        lifecycle_type=LifecycleType.PREMIUM_CONTINUATION,
        payment_frequency=PaymentFrequency.MONTHLY,
        channels=[ChannelOwner.ADVISER],
        grace_days=30,
        regulated=True,
        add_ons=[],
    ),
    dict(
        code="LIFE_UNIT_LINKED",
        line=Line.LIFE,
        name="Unit-Linked Protection & Savings Plan",
        tier="premium",
        description="Regular-premium plan for 10 to 25 years combining life cover with savings "
        "invested in a choice of funds.",
        min_age=18,
        max_age=60,
        min_sum_insured=money(250_000),
        max_sum_insured=money(10_000_000),
        base_premium=money(12_000),
        max_discount_pct=0,
        lifecycle_type=LifecycleType.PREMIUM_CONTINUATION,
        payment_frequency=PaymentFrequency.MONTHLY,
        channels=[ChannelOwner.ADVISER],
        grace_days=30,
        regulated=True,
        add_ons=["LIFE_CRITICAL_ILLNESS"],
    ),
    # --- savings & wealth (adviser-led)
    dict(
        code="SAVINGS_EDUCATION",
        line=Line.SAVINGS,
        name="Education Savings Plan",
        tier="standard",
        description="Regular savings towards a child's university fees, with life cover that "
        "keeps the plan going if the parent dies.",
        min_age=21,
        max_age=55,
        min_sum_insured=money(100_000),
        max_sum_insured=money(2_000_000),
        base_premium=money(6_000),
        max_discount_pct=0,
        lifecycle_type=LifecycleType.MILESTONE,
        payment_frequency=PaymentFrequency.MONTHLY,
        channels=[ChannelOwner.ADVISER],
        grace_days=30,
        regulated=True,
        add_ons=["LIFE_TERM"],
    ),
    dict(
        code="SAVINGS_REGULAR",
        line=Line.SAVINGS,
        name="Regular Savings Plan",
        tier="standard",
        description="Flexible monthly savings for 10 to 25 years into a choice of funds, with a "
        "death benefit.",
        min_age=18,
        max_age=60,
        min_sum_insured=money(100_000),
        max_sum_insured=money(5_000_000),
        base_premium=money(6_000),
        max_discount_pct=0,
        lifecycle_type=LifecycleType.PREMIUM_CONTINUATION,
        payment_frequency=PaymentFrequency.MONTHLY,
        channels=[ChannelOwner.ADVISER],
        grace_days=30,
        regulated=True,
        add_ons=["LIFE_TERM"],
    ),
    dict(
        code="SAVINGS_SINGLE_PREMIUM",
        line=Line.SAVINGS,
        name="Single-Premium Investment Plan",
        tier="premium",
        description="One-off investment into a managed fund range with a death benefit; reviewed "
        "with the adviser every year.",
        min_age=18,
        max_age=75,
        min_sum_insured=money(100_000),
        max_sum_insured=money(20_000_000),
        base_premium=money(100_000),
        max_discount_pct=0,
        lifecycle_type=LifecycleType.SCHEDULED_REVIEW,
        payment_frequency=PaymentFrequency.SINGLE,
        channels=[ChannelOwner.ADVISER],
        grace_days=0,
        regulated=True,
        add_ons=[],
    ),
    # --- employee benefits
    dict(
        code="GROUP_MEDICAL",
        line=Line.GROUP,
        name="Group Health Insurance",
        tier="standard",
        description="Employer health scheme for staff and dependants, meeting UAE mandatory "
        "health insurance rules.",
        min_age=0,
        max_age=200,
        min_sum_insured=money(150_000),
        max_sum_insured=money(5_000_000),
        base_premium=money(60_000),
        max_discount_pct=8,
        lifecycle_type=LifecycleType.GROUP_SCHEME_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.EMPLOYER],
        grace_days=30,
        regulated=False,
        add_ons=[],
    ),
    dict(
        code="GROUP_LIFE",
        line=Line.GROUP,
        name="Group Life Insurance",
        tier="standard",
        description="Employer-paid death-in-service cover, usually a multiple of each employee's "
        "salary.",
        min_age=0,
        max_age=200,
        min_sum_insured=money(500_000),
        max_sum_insured=money(20_000_000),
        base_premium=money(15_000),
        max_discount_pct=8,
        lifecycle_type=LifecycleType.GROUP_SCHEME_RENEWAL,
        payment_frequency=PaymentFrequency.ANNUAL,
        channels=[ChannelOwner.BROKER, ChannelOwner.EMPLOYER],
        grace_days=30,
        regulated=False,
        add_ons=[],
    ),
]


# --------------------------------------------------------------- lifecycle ---
# Which triggers each lifecycle type may fire, and their windows. Expiry triggers can only
# fire for EXPIRY lifecycles; premium-based products never get an "upcoming expiry".

LIFECYCLES: dict[str, dict[str, Any]] = {
    LifecycleType.EXPIRY_RENEWAL: {
        "triggers": (
            Trigger.UPCOMING_EXPIRY,
            Trigger.MISSING_DOCUMENT,
            Trigger.PAYMENT_OVERDUE,
            Trigger.LAPSE_RISK_SIGNAL,
        ),
        "notice_days": (45, 30, 14, 7),
        "missing_document_before_days": 30,
        "reinstatement_lookback_days": 60,
        "kpi": "renewal_rate",
    },
    LifecycleType.GROUP_SCHEME_RENEWAL: {
        "triggers": (
            Trigger.SCHEME_ANNIVERSARY,
            Trigger.MISSING_DOCUMENT,
            Trigger.PAYMENT_OVERDUE,
            Trigger.LAPSE_RISK_SIGNAL,
        ),
        "notice_days": (90, 60, 30),
        "missing_document_before_days": 60,
        "reinstatement_lookback_days": 60,
        "kpi": "scheme_renewal_rate",
    },
    LifecycleType.PREMIUM_CONTINUATION: {
        "triggers": (
            Trigger.PREMIUM_MISSED,
            Trigger.LAPSE_RISK_SIGNAL,
            Trigger.SCHEDULED_REVIEW,
            Trigger.MISSING_DOCUMENT,
        ),
        "review_notice_days": 30,
        "reinstatement_lookback_days": 90,
        "kpi": "persistency",
    },
    LifecycleType.MILESTONE: {
        "triggers": (
            Trigger.PREMIUM_MISSED,
            Trigger.LAPSE_RISK_SIGNAL,
            Trigger.MILESTONE,
            Trigger.SCHEDULED_REVIEW,
            Trigger.MISSING_DOCUMENT,
        ),
        "milestone_notice_days": 60,
        "review_notice_days": 30,
        "reinstatement_lookback_days": 90,
        "kpi": "persistency",
    },
    LifecycleType.SCHEDULED_REVIEW: {
        "triggers": (Trigger.SCHEDULED_REVIEW, Trigger.MISSING_DOCUMENT),
        "review_notice_days": 30,
        "reinstatement_lookback_days": 0,
        "kpi": "reviews_completed",
    },
}

REVIEW_INTERVAL_MONTHS = 12  # placeholder: plan review every year

# Trigger -> intervention it makes available.
TRIGGER_ACTIONS: dict[str, Action] = {
    Trigger.UPCOMING_EXPIRY: Action.REMINDER,
    Trigger.SCHEME_ANNIVERSARY: Action.REMINDER,
    Trigger.PAYMENT_OVERDUE: Action.PAYMENT_REMINDER,
    Trigger.PREMIUM_MISSED: Action.PAYMENT_REMINDER,
    Trigger.LAPSE_RISK_SIGNAL: Action.SERVICE_FOLLOW_UP,
    Trigger.SCHEDULED_REVIEW: Action.PLAN_REVIEW,
    Trigger.MILESTONE: Action.PLAN_REVIEW,
    Trigger.MISSING_DOCUMENT: Action.DOCUMENT_REQUEST,
}

# Retention signals (placeholders).
LAPSE_SIGNAL_PRICE_SHOCK_PCT = 15.0  # renewal premium up >= 15% (expiry lifecycles)
OFFER_MIN_TENURE_YEARS = 2
OFFER_MAX_CLAIMS_3Y = 1
ADD_ON_MIN_TENURE_YEARS = 1
LAPSED_REC_TTL_DAYS = 14
EVENT_REC_TTL_DAYS = 14  # reviews / milestones / documents


# ---------------------------------------------------------- approval matrix ---
# What the agent may do per action and who approves. ``agent``: draft (writes the message or
# task for approval). Nothing is ever executed without approval.
# Actions the agent must never take on its own are listed in FORBIDDEN_AGENT_ACTIONS.

APPROVAL_MATRIX: dict[str, dict[str, Any]] = {
    Action.REMINDER: {"agent": "draft", "queue": Queue.RETENTION},
    Action.PAYMENT_REMINDER: {"agent": "draft", "queue": Queue.RETENTION},
    Action.DOCUMENT_REQUEST: {"agent": "draft", "queue": Queue.RETENTION},
    Action.SERVICE_FOLLOW_UP: {"agent": "draft", "queue": Queue.RETENTION},
    Action.RETENTION_OFFER: {"agent": "draft", "queue": Queue.RETENTION},
    Action.REINSTATEMENT: {"agent": "draft", "queue": Queue.RETENTION},
    Action.INTERNAL_TASK: {"agent": "draft", "queue": Queue.RETENTION},
    Action.PLAN_REVIEW: {"agent": "draft", "queue": Queue.ADVISER},
    Action.ADD_ON_OFFER: {"agent": "draft", "queue": Queue.ADVISER, "regulated_advice": True},
}

# Service-team actions that stay with the service team even on adviser-owned policies.
SERVICE_TEAM_ACTIONS = (Action.PAYMENT_REMINDER,)

FORBIDDEN_AGENT_ACTIONS = frozenset(
    {
        "bind_cover",
        "issue_policy",
        "renew_policy",
        "set_price",
        "decline",
        "decline_application",
        "underwriting_decision",
        "auto_send",
    }
)

AUTO_SEND_MESSAGES = False  # pilot: every message waits for human approval


# ------------------------------------------------------ realism of the book ---
# Used by the seed data generator and checked by ``scripts/audit_data.py`` so the demo book
# looks like a real UAE insurer's: placeholders, not any company's actual rates.

# Annual premium as a share of the sum insured (min, max) for a believable policy.
PREMIUM_RATE_BAND: dict[str, tuple[float, float]] = {
    "MOTOR_TPL": (0.0003, 0.002),
    "MOTOR_COMPREHENSIVE": (0.015, 0.06),
    "MEDICAL_ESSENTIAL": (0.003, 0.012),
    "MEDICAL_FAMILY": (0.002, 0.04),
    "HOME_CONTENTS": (0.001, 0.008),
    "HOME_BUILDINGS_CONTENTS": (0.0004, 0.0025),
    "PA_INDIVIDUAL": (0.001, 0.005),
    "LIFE_TERM": (0.0005, 0.012),
    "LIFE_CRITICAL_ILLNESS": (0.002, 0.02),
    "LIFE_UNIT_LINKED": (0.004, 0.06),
    "SAVINGS_EDUCATION": (0.02, 0.25),
    "SAVINGS_REGULAR": (0.02, 0.25),
    "GROUP_MEDICAL": (0.01, 1.0),
    "GROUP_LIFE": (0.0005, 0.006),
}

# Term in years (min, max) for long-term plans, and the latest age cover may run to.
TERM_YEARS: dict[str, tuple[int, int]] = {
    "LIFE_TERM": (10, 30),
    "LIFE_CRITICAL_ILLNESS": (10, 20),
    "LIFE_UNIT_LINKED": (10, 25),
    "SAVINGS_EDUCATION": (5, 18),
    "SAVINGS_REGULAR": (10, 25),
    "SAVINGS_SINGLE_PREMIUM": (5, 10),
}
MAX_COVER_END_AGE: dict[str, int] = {
    "LIFE_TERM": 70,
    "LIFE_CRITICAL_ILLNESS": 65,
    "LIFE_UNIT_LINKED": 75,
    "SAVINGS_EDUCATION": 70,
    "SAVINGS_REGULAR": 75,
    "SAVINGS_SINGLE_PREMIUM": 85,
}

# Documents an insurer typically still needs at renewal / review time, per line (codes).
RENEWAL_DOCUMENTS: dict[str, tuple[str, ...]] = {
    Line.MOTOR: (
        "mulkiya_copy",
        "valid_driving_licence",
        "vehicle_inspection_report",
        "no_claims_certificate",
    ),
    Line.MEDICAL: ("renewed_emirates_id", "residence_visa_copy", "dependant_details_update"),
    Line.HOME: (
        "updated_contents_valuation",
        "ejari_tenancy_contract",
        "title_deed_copy",
        "high_value_items_list",
    ),
    Line.PERSONAL_ACCIDENT: ("occupation_declaration", "beneficiary_nomination_form"),
    Line.LIFE: (
        "beneficiary_nomination_form",
        "fatca_crs_self_certification",
        "renewed_emirates_id",
        "reinstatement_health_declaration",
    ),
    Line.SAVINGS: (
        "fatca_crs_self_certification",
        "source_of_funds_declaration",
        "renewed_emirates_id",
        "investment_risk_profile",
    ),
    Line.GROUP: ("updated_employee_census", "renewed_trade_licence", "signed_renewal_acceptance"),
}


DOCUMENT_LABELS: dict[str, str] = {
    "mulkiya_copy": "Vehicle registration (Mulkiya) copy",
    "valid_driving_licence": "Valid UAE driving licence",
    "vehicle_inspection_report": "Vehicle inspection report",
    "no_claims_certificate": "No-claims certificate",
    "renewed_emirates_id": "Renewed Emirates ID",
    "residence_visa_copy": "Residence visa copy",
    "dependant_details_update": "Updated dependant details",
    "updated_contents_valuation": "Updated contents valuation",
    "ejari_tenancy_contract": "Ejari tenancy contract",
    "title_deed_copy": "Title deed copy",
    "high_value_items_list": "List of high-value items",
    "occupation_declaration": "Occupation declaration",
    "beneficiary_nomination_form": "Beneficiary nomination form",
    "fatca_crs_self_certification": "FATCA / CRS self-certification form",
    "reinstatement_health_declaration": "Health declaration for reinstatement",
    "source_of_funds_declaration": "Source of funds declaration",
    "investment_risk_profile": "Updated investment risk profile",
    "updated_employee_census": "Updated employee census",
    "renewed_trade_licence": "Renewed trade licence",
    "signed_renewal_acceptance": "Signed renewal acceptance",
}


def document_label(code: str) -> str:
    return DOCUMENT_LABELS.get(code, code.replace("_", " ").capitalize())


def product(code: str) -> dict[str, Any] | None:
    return next((p for p in PRODUCTS if p["code"] == code), None)
