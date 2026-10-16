"""The rulebook: every business parameter the new-customer agent decides with, as data.

One book of business that mixes two distribution models:

- **General insurance** (motor, medical, home, personal accident): sold direct or through
  brokers. A broker may own the customer relationship; then outreach goes to the broker.
- **Life, savings and employee benefits**: adviser-led (or employer / broker for schemes).
  Product suggestions are regulated advice and are approved by an adviser.

Rule code (``services/rules``) reads these tables; the product catalogue itself is
``data_csv/products.csv``. Every rule has a stable id that recommendations cite. Values are
POC placeholders to be replaced by the insurer's approved rules.
"""

from __future__ import annotations

from typing import Any

from insurance_poc.enums import Action, ChannelOwner, Line, Queue

RULEBOOK_VERSION = "2026.10-poc.3"

K = 100  # major -> minor units


def money(major: int) -> int:
    return major * K


# ------------------------------------------------------------------ lines ---
# family: general | life | group. ``required`` = declared fields the data-quality gate needs.
# ``documents`` = application documents (missing ones lower completeness, they never block).
# ``signals`` = declared fields the LLM may see (allow-list; anything else never leaves).

LINES: dict[str, dict[str, Any]] = {
    Line.MOTOR: {
        "label": "Motor",
        "family": "general",
        "owners": (ChannelOwner.BROKER, ChannelOwner.DIRECT),
        "required": ("vehicle_year", "driving_years"),
        "documents": ("national_id", "driving_licence", "vehicle_registration"),
        "signals": (
            "vehicle_year",
            "vehicle_value",
            "driving_years",
            "prior_claims_3y",
            "annual_mileage",
        ),
    },
    Line.MEDICAL: {
        "label": "Medical",
        "family": "general",
        "owners": (ChannelOwner.BROKER, ChannelOwner.DIRECT),
        "required": ("smoker",),
        "documents": ("national_id", "medical_declaration"),
        "signals": ("smoker", "bmi", "pre_existing_conditions", "dependents"),
    },
    Line.HOME: {
        "label": "Home",
        "family": "general",
        "owners": (ChannelOwner.BROKER, ChannelOwner.DIRECT),
        "required": ("property_year", "rebuild_value"),
        "documents": ("national_id", "title_deed_or_tenancy"),
        "signals": (
            "property_type",
            "property_year",
            "rebuild_value",
            "prior_claims_3y",
            "security_alarm",
        ),
    },
    Line.PERSONAL_ACCIDENT: {
        "label": "Personal accident",
        "family": "general",
        "owners": (ChannelOwner.BROKER, ChannelOwner.DIRECT),
        "required": ("occupation_risk",),
        "documents": ("national_id",),
        "signals": ("occupation_risk", "dependents"),
    },
    Line.LIFE: {
        "label": "Life & protection",
        "family": "life",
        "owners": (ChannelOwner.ADVISER,),
        "required": ("smoker", "term_years", "annual_income"),
        "documents": ("national_id", "proof_of_income", "medical_questionnaire"),
        "signals": (
            "smoker",
            "bmi",
            "occupation_risk",
            "term_years",
            "pre_existing_conditions",
            "dependents",
            "annual_income",
            "existing_cover",
        ),
    },
    Line.SAVINGS: {
        "label": "Savings & wealth",
        "family": "life",
        "owners": (ChannelOwner.ADVISER,),
        "required": ("term_years", "annual_income", "savings_goal"),
        "documents": ("national_id", "proof_of_income", "source_of_funds"),
        "signals": ("term_years", "annual_income", "savings_goal", "dependents", "risk_appetite"),
    },
    Line.GROUP: {
        "label": "Employee benefits",
        "family": "group",
        "owners": (ChannelOwner.BROKER, ChannelOwner.EMPLOYER),
        "required": ("employee_count",),
        "documents": ("trade_licence", "employee_census"),
        "signals": ("employee_count", "average_employee_age", "prior_claims_3y", "industry_risk"),
    },
}

# Money-valued declared fields (stored in minor units, shown to the LLM in major units).
MONEY_FIELDS = ("vehicle_value", "rebuild_value", "annual_income", "existing_cover")

# Lines where the applicant is a company: no date of birth / personal age checks.
COMPANY_LINES = (Line.GROUP,)


# ---------------------------------------------------------------- sources ---
# Where a lead came from decides the default relationship owner and whether the data may be
# used for profiling at all (purpose limitation). ``profiling_allowed=False`` -> blocked.

SOURCES: dict[str, dict[str, Any]] = {
    "web": {"owner": ChannelOwner.DIRECT, "profiling_allowed": True},
    "campaign": {"owner": ChannelOwner.DIRECT, "profiling_allowed": True},
    "partner": {"owner": ChannelOwner.DIRECT, "profiling_allowed": True},
    "referral": {"owner": ChannelOwner.DIRECT, "profiling_allowed": True},
    "broker_portal": {"owner": ChannelOwner.BROKER, "profiling_allowed": True},
    "adviser_crm": {"owner": ChannelOwner.ADVISER, "profiling_allowed": True},
    "employer": {"owner": ChannelOwner.EMPLOYER, "profiling_allowed": True},
    # Bought / scraped lists: no consented purpose for profiling.
    "purchased_list": {"owner": ChannelOwner.DIRECT, "profiling_allowed": False},
}
DEFAULT_SOURCE = "web"

# Broker-owned relationships: may the insurer message the customer directly? (pilot: no)
BROKER_DIRECT_CONTACT_ALLOWED = False


# ------------------------------------------------------------- catalogue ---
# Products live in data_csv/products.csv (one ``rule_*`` column per eligibility rule; the
# rule keys are listed in services/rules/eligibility.py).


# ----------------------------------------------------------- underwriting ---
# Declarative referral / knock-out rules over derived lead facts (see underwriting.py for the
# field list). Outcome precedence: knockout > refer > clear. A knock-out is **not** a decline:
# the case goes to an underwriter, who alone may decline. All values are placeholders.

UW_KNOCKOUT = "knockout"
UW_REFER = "refer"

UNDERWRITING_RULES: list[dict[str, Any]] = [
    {
        "id": "underwriting.min_age",
        "lines": "*",
        "when": {"field": "age", "op": "lt", "value": 18},
        "outcome": UW_KNOCKOUT,
        "reason": "Applicant is under 18.",
    },
    {
        "id": "underwriting.vehicle_age",
        "lines": (Line.MOTOR,),
        "when": {"field": "vehicle_age", "op": "gt", "value": 20},
        "outcome": UW_KNOCKOUT,
        "reason": "Vehicle is more than 20 years old.",
    },
    {
        "id": "underwriting.claims_history",
        "lines": (Line.MOTOR, Line.HOME, Line.GROUP),
        "when": {"field": "prior_claims_3y", "op": "gte", "value": 3},
        "outcome": UW_REFER,
        "reason": "Three or more claims in the last 3 years.",
    },
    {
        "id": "underwriting.inexperienced_driver",
        "lines": (Line.MOTOR,),
        "when": {"field": "driving_years", "op": "lt", "value": 1},
        "outcome": UW_REFER,
        "reason": "Less than one year of driving experience.",
    },
    {
        "id": "underwriting.property_age",
        "lines": (Line.HOME,),
        "when": {"field": "property_age", "op": "gt", "value": 100},
        "outcome": UW_REFER,
        "reason": "Property is more than 100 years old.",
    },
    {
        "id": "underwriting.pre_existing",
        "lines": (Line.MEDICAL,),
        "when": {"field": "pre_existing_conditions", "op": "not_empty"},
        "outcome": UW_REFER,
        "reason": "Pre-existing condition declared.",
    },
    {
        "id": "underwriting.bmi",
        "lines": (Line.MEDICAL, Line.LIFE),
        "when": {"field": "bmi", "op": "gte", "value": 40},
        "outcome": UW_REFER,
        "reason": "BMI of 40 or above.",
    },
    {
        "id": "underwriting.smoker_age",
        "lines": (Line.LIFE,),
        "when": {
            "all": [
                {"field": "smoker", "op": "is_true"},
                {"field": "age", "op": "gte", "value": 50},
            ]
        },
        "outcome": UW_REFER,
        "reason": "Smoker aged 50 or over.",
    },
    {
        "id": "underwriting.serious_condition",
        "lines": (Line.LIFE,),
        "when": {
            "field": "pre_existing_conditions",
            "op": "intersects",
            "value": ["heart_disease", "cancer", "stroke"],
        },
        "outcome": UW_REFER,
        "reason": "Serious medical condition declared.",
    },
    {
        "id": "underwriting.occupation",
        "lines": (Line.LIFE, Line.PERSONAL_ACCIDENT),
        "when": {"field": "occupation_risk", "op": "eq", "value": "high"},
        "outcome": UW_REFER,
        "reason": "High-risk occupation.",
    },
    {
        "id": "underwriting.cover_vs_income",
        "lines": (Line.LIFE,),
        "when": {"field": "cover_income_multiple", "op": "gt", "value": 20},
        "outcome": UW_REFER,
        "reason": "Cover above 20x annual income needs financial underwriting.",
    },
    {
        "id": "underwriting.industry_risk",
        "lines": (Line.GROUP,),
        "when": {"field": "industry_risk", "op": "eq", "value": "high"},
        "outcome": UW_REFER,
        "reason": "High-risk industry for an employee scheme.",
    },
]

# Medical / financial evidence an adviser must arrange before the underwriter decides
# (life line only). First matching band adds its items; bands are cumulative.
MEDICAL_REQUIREMENTS: list[dict[str, Any]] = [
    {"id": "evidence.base", "min_age": 0, "min_sum_insured": 0, "items": ["medical_questionnaire"]},
    {
        "id": "evidence.paramedical",
        "min_age": 45,
        "min_sum_insured": money(2_000_000),
        "items": ["paramedical_exam", "blood_profile"],
    },
    {
        "id": "evidence.full_medical",
        "min_age": 55,
        "min_sum_insured": money(5_000_000),
        "items": ["full_medical_exam", "ecg"],
    },
    {
        "id": "evidence.financial",
        "min_age": None,
        "min_sum_insured": money(5_000_000),
        "items": ["financial_questionnaire"],
    },
]

# Needs review for adviser-led lines (placeholders).
PROTECTION_NEED_INCOME_MULTIPLE = 10  # protection need = income x 10
SAVINGS_AFFORDABILITY_MAX_PCT = 15  # planned yearly saving <= 15% of income


# ---------------------------------------------------------- approval matrix ---
# Who approves each action. The agent only recommends; nothing is executed without approval.
# Actions the agent must never take on its own are listed in FORBIDDEN_AGENT_ACTIONS.

APPROVAL_MATRIX: dict[str, dict[str, Any]] = {
    Action.CONTACT_AND_QUOTE: {"agent": "recommend", "queue": Queue.SALES},
    Action.NURTURE: {"agent": "recommend", "queue": Queue.SALES},
    Action.REQUEST_INFO: {"agent": "recommend", "queue": Queue.SALES},
    Action.DO_NOT_CONTACT: {"agent": "recommend", "queue": Queue.SALES},
    Action.REFER_TO_UNDERWRITER: {"agent": "recommend", "queue": Queue.UNDERWRITING},
}

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
