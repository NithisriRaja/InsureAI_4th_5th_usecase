"""Synthetic data: handcrafted edge-case scenarios plus Faker bulk data.

One mixed book of business: general lines sold direct or through brokers (expiry-driven
renewals), life and savings sold through advisers (premium continuation, reviews,
milestones) and employee-benefit schemes through brokers. The product catalogue lives in
``rulebook.PRODUCTS``.

All dates are relative to ``clock.today()`` so the data never goes stale; set AS_OF_DATE
for fully reproducible output. Money is in minor units (fils / cents).
"""

from __future__ import annotations

import calendar
import random
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

from faker import Faker

from renewal_backend import rulebook
from renewal_backend.db.models import Customer, Payment, Policy, Product
from renewal_backend.db.store import DbSession
from renewal_backend.enums import (
    EXPIRY_LIFECYCLES,
    ChannelOwner,
    Line,
    PaymentFrequency,
    PaymentStatus,
    PolicyStatus,
)
from renewal_backend.rulebook import money
from renewal_backend.utils.clock import today, utcnow
from renewal_backend.utils.normalize import norm_phone

SEED = 42
K = rulebook.K
PRODUCTS = rulebook.PRODUCTS

BROKERS = ("Harbour Insurance Brokers", "Northgate Risk Partners", "Tidewater Brokerage")
ADVISERS = ("Omar Haddad", "Leena Rao", "James Whitfield")
CITIES = ("Dubai", "Abu Dhabi", "Sharjah", "Ajman")
POLICY_PREFIX = {
    Line.MOTOR: "MOT",
    Line.MEDICAL: "MED",
    Line.HOME: "HOM",
    Line.PERSONAL_ACCIDENT: "PAC",
    Line.LIFE: "LIF",
    Line.SAVINGS: "SAV",
    Line.GROUP: "GRP",
}


def _dob(age: int, as_of: date, idx: int = 0) -> date:
    """A birthday giving exactly ``age`` on ``as_of``, spread over the year by ``idx``."""
    month = 1 + (idx * 7) % 12
    day = 1 + (idx * 11) % 28
    born = date(as_of.year - age, month, day)
    return born if born <= as_of else date(as_of.year - age - 1, month, day)


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _uae_mobile(idx: int) -> str:
    prefix = ("50", "52", "54", "55", "56", "58")[idx % 6]
    return f"+971 {prefix} {(2_345_671 + idx * 7_919_311) % 9_000_000 + 1_000_000:07d}"


# ------------------------------------------------------------- scenarios ---


@dataclass
class PolicySpec:
    ref: str
    first: str
    last: str
    age: int
    product: str
    prev_premium: int
    premium: int
    sum_insured: int
    end_offset_days: int | None = None  # expiry lifecycles: end of the current term
    status: PolicyStatus = PolicyStatus.ACTIVE
    tenure: int = 2
    claims: int = 0
    docs: list[str] = field(default_factory=list)
    overdue_installments: int = 0  # expiry lifecycles
    monthly: bool = False  # expiry lifecycles paid in instalments
    overdue_days: int = 0  # premium lifecycles: days since the oldest missed premium
    failed_payments: int = 0
    auto_renew: bool = False
    complaints: int = 0
    consent_email: bool = True
    consent_sms: bool = True
    consent_marketing: bool = True
    preferred_channel: str | None = None  # email | sms
    email: str | None = None
    phone: str | None = None
    channel_owner: str = ChannelOwner.DIRECT
    intermediary: str | None = None
    term_years: int = 20
    term_end_offset_days: int | None = None  # premium lifecycles: override the term end
    review_offset_days: int | None = None
    milestone_offset_days: int | None = None
    milestone_label: str | None = None
    add_ons_held: list[str] = field(default_factory=list)


def scenario_policies() -> list[PolicySpec]:
    return [
        # --- expiry-driven general lines
        PolicySpec(
            "P01-motor-broker-overdue",
            "Liam",
            "Murphy",
            31,
            "MOTOR_COMPREHENSIVE",
            money(3_150),
            money(3_400),
            money(110_000),
            end_offset_days=10,
            tenure=1,
            claims=1,
            overdue_installments=2,
            monthly=True,
            channel_owner=ChannelOwner.BROKER,
            intermediary=BROKERS[0],
        ),
        PolicySpec(
            "P02-home-docs",
            "Olivia",
            "Nguyen",
            44,
            "HOME_CONTENTS",
            money(640),
            money(660),
            money(260_000),
            end_offset_days=30,
            tenure=3,
            docs=["updated_contents_valuation", "ejari_tenancy_contract"],
        ),
        PolicySpec(
            "P03-medical-loyal-price-shock",
            "Grace",
            "Adeyemi",
            45,
            "MEDICAL_FAMILY",
            money(13_800),
            money(16_284),
            money(1_500_000),
            end_offset_days=20,
            tenure=6,
            email="grace.adeyemi@example.com",
            phone="+971 50 100 0203",
        ),
        PolicySpec(
            "P04-motor-low-risk",
            "Henry",
            "Svensson",
            50,
            "MOTOR_TPL",
            money(950),
            money(950),
            money(2_000_000),
            end_offset_days=40,
            tenure=8,
            auto_renew=True,
        ),
        PolicySpec(
            "P05-medical-in-grace",
            "Mia",
            "Rossi",
            36,
            "MEDICAL_ESSENTIAL",
            money(1_080),
            money(1_140),
            money(150_000),
            end_offset_days=-10,
            status=PolicyStatus.GRACE,
            tenure=2,
            overdue_installments=1,
        ),
        PolicySpec(
            "P06-motor-lapsed",
            "Ethan",
            "Brown",
            27,
            "MOTOR_TPL",
            money(1_000),
            money(1_080),
            money(2_000_000),
            end_offset_days=-20,
            status=PolicyStatus.LAPSED,
            tenure=1,
            overdue_installments=1,
        ),
        PolicySpec(
            "P07-motor-already-renewed",
            "Chloe",
            "Martin",
            40,
            "MOTOR_COMPREHENSIVE",
            money(2_900),
            money(2_950),
            money(120_000),
            end_offset_days=15,
            status=PolicyStatus.RENEWED,
            tenure=4,
        ),
        PolicySpec(
            "P08-home-cancelled",
            "Lucas",
            "Silva",
            55,
            "HOME_BUILDINGS_CONTENTS",
            money(2_300),
            money(2_400),
            money(3_200_000),
            end_offset_days=20,
            status=PolicyStatus.CANCELLED,
            tenure=5,
        ),
        PolicySpec(
            "P09-medical-no-contact-consent",
            "Zara",
            "Ahmed",
            33,
            "MEDICAL_ESSENTIAL",
            money(960),
            money(990),
            money(150_000),
            end_offset_days=12,
            tenure=2,
            consent_email=False,
            consent_sms=False,
            consent_marketing=False,
        ),
        PolicySpec(
            "P10-motor-out-of-window",
            "Oscar",
            "Novak",
            48,
            "MOTOR_TPL",
            money(920),
            money(940),
            money(2_000_000),
            end_offset_days=90,
            tenure=3,
        ),
        PolicySpec(
            "P11-home-expires-today-complaints",
            "Ava",
            "Kim",
            61,
            "HOME_BUILDINGS_CONTENTS",
            money(2_200),
            money(2_750),
            money(2_500_000),
            end_offset_days=0,
            tenure=4,
            complaints=2,
        ),
        PolicySpec(
            "P12-group-medical-broker",
            "Gulfline Logistics LLC",
            "",
            40,
            "GROUP_MEDICAL",
            money(180_000),
            money(189_000),
            money(2_000_000),
            end_offset_days=75,
            tenure=3,
            channel_owner=ChannelOwner.BROKER,
            intermediary=BROKERS[1],
            email="hr@gulfline-logistics.example.com",
            phone="+971 4 300 0117",
        ),
        # --- adviser-led life & savings (no annual expiry)
        PolicySpec(
            "P13-term-life-missed-premium",
            "Hassan",
            "Ali",
            41,
            "LIFE_TERM",
            money(3_600),
            money(3_600),
            money(2_000_000),
            tenure=4,
            overdue_days=20,
            channel_owner=ChannelOwner.ADVISER,
            intermediary=ADVISERS[0],
            review_offset_days=150,
        ),
        PolicySpec(
            "P14-unit-linked-review-due",
            "Aisha",
            "Rahman",
            38,
            "LIFE_UNIT_LINKED",
            money(18_000),
            money(18_000),
            money(3_000_000),
            tenure=3,
            term_years=20,
            channel_owner=ChannelOwner.ADVISER,
            intermediary=ADVISERS[1],
            review_offset_days=20,
        ),
        PolicySpec(
            "P15-savings-lapsed",
            "Karan",
            "Mehta",
            33,
            "SAVINGS_REGULAR",
            money(12_000),
            money(12_000),
            money(250_000),
            tenure=2,
            overdue_days=45,
            failed_payments=1,
            term_years=15,
            channel_owner=ChannelOwner.ADVISER,
            intermediary=ADVISERS[2],
            review_offset_days=200,
        ),
        PolicySpec(
            "P16-education-milestone",
            "Noura",
            "Saeed",
            47,
            "SAVINGS_EDUCATION",
            money(24_000),
            money(24_000),
            money(400_000),
            tenure=9,
            term_years=10,
            channel_owner=ChannelOwner.ADVISER,
            intermediary=ADVISERS[0],
            milestone_offset_days=45,
            milestone_label="First university fee payment",
            review_offset_days=120,
        ),
        PolicySpec(
            "P17-term-life-all-clear",
            "Peter",
            "Walsh",
            59,
            "LIFE_TERM",
            money(4_800),
            money(4_800),
            money(1_000_000),
            tenure=15,
            channel_owner=ChannelOwner.ADVISER,
            intermediary=ADVISERS[1],
            term_end_offset_days=20,  # term ends soon: still no expiry-renewal trigger
            review_offset_days=200,
        ),
        PolicySpec(
            "P18-investment-review-no-consent",
            "Sofia",
            "Lindgren",
            66,
            "SAVINGS_SINGLE_PREMIUM",
            money(250_000),
            money(250_000),
            money(250_000),
            tenure=5,
            term_years=10,
            channel_owner=ChannelOwner.ADVISER,
            intermediary=ADVISERS[2],
            review_offset_days=-10,
            consent_email=False,
            consent_sms=False,
            consent_marketing=False,
        ),
    ]


# --------------------------------------------------------------- builders ---


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _policy_objects(
    spec: PolicySpec, as_of: date, idx: int
) -> tuple[Customer, Policy, list[Payment]]:
    prod = rulebook.product(spec.product)
    assert prod is not None, spec.product
    line = Line(prod["line"])
    expiry = prod["lifecycle_type"] in EXPIRY_LIFECYCLES
    code = spec.ref.split("-")[0]
    cust_id = f"cust_{code.lower()}"
    email = spec.email or _ascii_email(f"{spec.first}.{spec.last}.{idx}")
    customer = Customer(
        id=cust_id,
        external_ref=f"C-{code}",
        first_name=spec.first,
        last_name=spec.last,
        dob=None if line == Line.GROUP else _dob(spec.age, as_of, idx),
        email=email,
        phone=norm_phone(spec.phone or _uae_mobile(idx)),
        city=CITIES[idx % len(CITIES)],
        consent_marketing=spec.consent_marketing,
        consent_email=spec.consent_email,
        consent_sms=spec.consent_sms,
        preferred_channel=spec.preferred_channel,
        consent_updated_at=utcnow(),
    )
    if expiry:  # yearly cover: the current term runs exactly one year
        end = as_of + timedelta(days=spec.end_offset_days or 0)
        start = _add_years(end, -1)
    else:  # long-term plan: started ``tenure`` years ago, on its premium day of the month
        anchor = as_of - timedelta(days=spec.overdue_days or 5 + idx % 20)
        start = _add_years(anchor, -spec.tenure)
        end = (
            as_of + timedelta(days=spec.term_end_offset_days)
            if spec.term_end_offset_days is not None
            else _add_years(start, spec.term_years)
        )
    policy = Policy(
        id=f"pol_{code.lower()}",
        policy_number=f"{POLICY_PREFIX[line]}-{start.year}-{1000 + idx:05d}",
        customer_id=cust_id,
        product_code=spec.product,
        line=line.value,
        start_date=start,
        end_date=end,
        premium=spec.premium,
        prev_premium=spec.prev_premium,
        sum_insured=spec.sum_insured,
        status=spec.status.value,
        claims_count_3y=spec.claims,
        tenure_years=spec.tenure,
        docs_outstanding=spec.docs,
        auto_renew=spec.auto_renew,
        service_complaints_12m=spec.complaints,
        lifecycle_type=prod["lifecycle_type"].value,
        payment_frequency=prod["payment_frequency"].value,
        channel_owner=str(spec.channel_owner),
        intermediary=spec.intermediary,
        review_due_date=(
            as_of + timedelta(days=spec.review_offset_days)
            if spec.review_offset_days is not None
            else None
        ),
        milestone_date=(
            as_of + timedelta(days=spec.milestone_offset_days)
            if spec.milestone_offset_days is not None
            else None
        ),
        milestone_label=spec.milestone_label,
        add_ons_held=spec.add_ons_held,
    )
    if expiry:
        payments = _term_payments(policy, spec, as_of)
    elif prod["payment_frequency"] == PaymentFrequency.SINGLE:
        payments = [_payment(policy, 0, policy.start_date, spec.prev_premium, PaymentStatus.PAID)]
    else:
        payments = _monthly_premiums(policy, spec, as_of)
    return customer, policy, payments


def _payment(policy: Policy, n: int, due: date, amount: int, status: PaymentStatus) -> Payment:
    return Payment(
        id=f"pay_{policy.id}_{n:02d}",
        policy_id=policy.id,
        due_date=due,
        amount=amount,
        status=status.value,
        paid_at=utcnow() if status == PaymentStatus.PAID else None,
    )


def _term_payments(policy: Policy, spec: PolicySpec, as_of: date) -> list[Payment]:
    """Yearly products: one annual payment, or 12 monthly instalments on the start day."""
    if not spec.monthly:
        status = PaymentStatus.OVERDUE if spec.overdue_installments else PaymentStatus.PAID
        return [_payment(policy, 0, policy.start_date, spec.prev_premium, status)]
    dues = [_add_months(policy.start_date, k) for k in range(12)]
    dues = [d for d in dues if d <= as_of]
    out = [
        _payment(policy, n, d, spec.prev_premium // 12, PaymentStatus.PAID)
        for n, d in enumerate(dues)
    ]
    for p in out[len(out) - spec.overdue_installments :] if spec.overdue_installments else []:
        p.status, p.paid_at = PaymentStatus.OVERDUE.value, None
    return out


def _monthly_premiums(policy: Policy, spec: PolicySpec, as_of: date) -> list[Payment]:
    """Long-term plans: the last 12 monthly premiums, all on the policy's premium day. The
    oldest missed one is ``overdue_days`` old; ``failed_payments`` marks the latest paid ones
    as failed."""
    amount = spec.prev_premium // 12
    if spec.overdue_days:  # the start date was aligned to this day (see _policy_objects)
        anchor = as_of - timedelta(days=spec.overdue_days)
    else:  # the latest premium day (the policy's day of the month) on or before today
        anchor = _add_months(policy.start_date, 0)
        while _add_months(anchor, 1) <= as_of:
            anchor = _add_months(anchor, 1)
    missed: list[date] = []
    if spec.overdue_days:
        d = anchor
        while d <= as_of:
            missed.append(d)
            d = _add_months(d, 1)
    paid = [_add_months(anchor, -k) for k in range(12 - len(missed), 0, -1)]
    if not spec.overdue_days:
        paid.append(anchor)
    paid = [d for d in paid if d >= policy.start_date]
    out = [_payment(policy, n, d, amount, PaymentStatus.PAID) for n, d in enumerate(paid)]
    for p in out[len(out) - spec.failed_payments :] if spec.failed_payments else []:
        p.status, p.paid_at = PaymentStatus.FAILED.value, None
    out += [
        _payment(policy, len(paid) + n, d, amount, PaymentStatus.OVERDUE)
        for n, d in enumerate(missed)
    ]
    return out


# ---------------------------------------------------------------- faker ---

# A realistic UAE customer mix, written in Latin letters (as on Emirates ID / passports).
# First and last names are paired within a community so every name reads naturally.
NAME_POOLS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (  # Emirati
        (
            "Ahmed",
            "Fatima",
            "Mohammed",
            "Mariam",
            "Khalid",
            "Noura",
            "Saeed",
            "Hessa",
            "Rashid",
            "Shaikha",
            "Hamdan",
            "Amna",
            "Sultan",
            "Maitha",
        ),
        (
            "Al Mansoori",
            "Al Nuaimi",
            "Al Hashimi",
            "Al Shamsi",
            "Al Falasi",
            "Al Mazrouei",
            "Al Ketbi",
            "Al Suwaidi",
            "Al Marri",
            "Al Dhaheri",
        ),
    ),
    (  # Levant / Arab expatriates
        ("Omar", "Layla", "Karim", "Rania", "Tariq", "Dina", "Yousef", "Sara", "Faisal", "Reem"),
        ("Haddad", "Khoury", "Nasser", "Saleh", "Farouk", "Mansour", "Aziz", "Hamdan"),
    ),
    (  # Indian
        (
            "Rahul",
            "Priya",
            "Arjun",
            "Anjali",
            "Vikram",
            "Deepa",
            "Rohan",
            "Kavya",
            "Suresh",
            "Meera",
        ),
        ("Menon", "Nair", "Sharma", "Iyer", "Pillai", "Kapoor", "Reddy", "Patel", "Varghese"),
    ),
    (  # Pakistani
        ("Imran", "Sana", "Bilal", "Hiba", "Usman", "Ayesha", "Hamza", "Zainab"),
        ("Khan", "Qureshi", "Siddiqui", "Malik", "Chaudhry", "Butt"),
    ),
    (  # Filipino
        ("Joseph", "Maria", "Mark", "Angelica", "Paolo", "Kristine", "Jerome", "Joy"),
        ("Santos", "Reyes", "Cruz", "Bautista", "Garcia", "Mendoza", "Dela Cruz"),
    ),
    (  # British / Irish / other Western
        (
            "James",
            "Olivia",
            "Daniel",
            "Sophie",
            "Michael",
            "Hannah",
            "David",
            "Emma",
            "Thomas",
            "Grace",
        ),
        ("Smith", "Taylor", "Brown", "Wilson", "Evans", "Murphy", "O'Connor", "Clarke", "Walsh"),
    ),
    (  # European
        ("Marco", "Chiara", "Andrei", "Elena", "Lukas", "Anna", "Julien", "Camille"),
        ("Rossi", "Bianchi", "Weber", "Moreau", "Schneider", "Dubois", "Martin", "Novak"),
    ),
)
COMPANIES = (
    "Al Noor Trading",
    "Desert Rose Hospitality",
    "Gulf Bridge Logistics",
    "Marina Tech Solutions",
    "Palm Coast Contracting",
    "Emirates Fresh Foods",
    "Falcon Engineering",
    "Oasis Retail Group",
    "Blue Dhow Shipping",
    "Sand Dune Real Estate",
    "Pearl Medical Centre",
    "Horizon Facilities",
    "Creek Side Interiors",
    "Jumeirah Events",
    "Al Khaleej Printing",
    "Corniche Auto Services",
    "Golden Sands Travel",
    "Saffron Restaurants",
    "Skyline Elevators",
    "Liwa Agro Industries",
)
TERM_PRODUCTS = {"LIFE_TERM", "LIFE_CRITICAL_ILLNESS", "LIFE_UNIT_LINKED"}


def _ascii_email(local: str) -> str:
    ascii_local = unicodedata.normalize("NFKD", local).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9.]", "", ascii_local.lower()) + "@example.com"


def _round(minor: int, step: int) -> int:
    """Round minor units to a step given in whole AED."""
    unit = step * K
    return max(unit, int(round(minor / unit)) * unit)


def _cover_and_premium(code: str, rng: random.Random, age: int, term: int) -> tuple[int, int]:
    """(sum insured, annual premium) in minor units, priced like a real UAE policy."""
    pick = rng.choice
    if code == "MOTOR_TPL":
        return money(2_000_000), _round(money(rng.randint(750, 1_600)), 10)
    if code == "MOTOR_COMPREHENSIVE":
        value = money(
            pick([45_000, 60_000, 75_000, 90_000, 120_000, 150_000, 180_000, 250_000, 350_000])
        )
        rate = rng.uniform(0.022, 0.04) if value < money(150_000) else rng.uniform(0.017, 0.03)
        return value, _round(max(money(1_500), int(value * rate)), 10)
    if code == "MEDICAL_ESSENTIAL":
        return money(150_000), _round(money(rng.randint(750, 1_400)), 10)
    if code == "MEDICAL_FAMILY":
        limit = money(pick([1_000_000, 2_000_000, 3_000_000, 5_000_000]))
        base = {1: 9_000, 2: 14_000, 3: 19_000, 5: 28_000}[limit // money(1_000_000)]
        return limit, _round(money(int(base * (1 + max(0, age - 35) * 0.025))), 10)
    if code == "HOME_CONTENTS":
        value = money(pick([75_000, 100_000, 150_000, 200_000, 300_000, 400_000]))
        return value, _round(max(money(350), int(value * rng.uniform(0.0022, 0.0035))), 10)
    if code == "HOME_BUILDINGS_CONTENTS":
        value = money(pick([1_000_000, 1_500_000, 2_000_000, 3_000_000, 4_500_000, 6_000_000]))
        return value, _round(int(value * rng.uniform(0.0006, 0.001)), 10)
    if code == "LIFE_TERM":
        cover = money(
            pick([500_000, 750_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000, 5_000_000])
        )
        rate = 0.0008 * 1.07 ** max(0, age - 25)
        return cover, _round(int(cover * rate), 120)
    if code == "LIFE_CRITICAL_ILLNESS":
        cover = money(pick([200_000, 300_000, 500_000, 750_000, 1_000_000]))
        rate = 0.0025 * 1.06 ** max(0, age - 25)
        return cover, _round(int(cover * rate), 120)
    if code == "LIFE_UNIT_LINKED":
        cover = money(pick([500_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000]))
        return cover, _round(int(cover * rng.uniform(0.008, 0.03)), 120)
    if code == "SAVINGS_EDUCATION":
        target = money(pick([150_000, 250_000, 400_000, 600_000]))
        return target, _round(int(target / term * rng.uniform(0.65, 0.9)), 120)
    if code == "SAVINGS_REGULAR":
        cover = money(pick([100_000, 200_000, 300_000, 500_000, 750_000, 1_000_000]))
        return cover, _round(int(cover * rng.uniform(0.04, 0.12)), 120)
    if code == "SAVINGS_SINGLE_PREMIUM":
        invest = money(pick([100_000, 250_000, 500_000, 750_000, 1_000_000, 2_000_000]))
        return invest * 101 // 100, invest
    if code == "GROUP_MEDICAL":
        staff = rng.randint(10, 60)
        limit = money(pick([500_000, 1_000_000, 2_000_000]))
        return limit, _round(money(staff * rng.randint(3_200, 6_000)), 100)
    if code == "GROUP_LIFE":
        staff = rng.randint(15, 120)
        cover = min(money(staff * rng.choice([100_000, 150_000, 200_000])), money(20_000_000))
        return cover, _round(int(cover * rng.uniform(0.0012, 0.003)), 100)
    raise ValueError(code)


def _fake_policy_spec(
    fake: Faker, rng: random.Random, i: int, used_companies: set[str]
) -> PolicySpec:
    prod = rng.choice([p for p in PRODUCTS if p["code"] != "PA_INDIVIDUAL"])
    code, line = prod["code"], Line(prod["line"])
    expiry = prod["lifecycle_type"] in EXPIRY_LIFECYCLES
    term = 1
    if expiry:
        age = rng.randint(max(prod["min_age"], 22), min(prod["max_age"], 66))
        tenure = rng.choice([1, 1, 2, 3, 4, 5, 7, 9])
    else:
        lo, hi = rulebook.TERM_YEARS[code]
        max_end = rulebook.MAX_COVER_END_AGE[code]
        term = rng.randint(lo, hi)
        tenure = rng.randint(1, max(1, min(term - 2, 9)))
        # entry age within product limits and cover ending by the maximum age
        entry_hi = min(prod["max_age"], max_end - term)
        entry_lo = max(prod["min_age"], 24)
        if entry_hi < entry_lo:
            term = max(lo, max_end - entry_lo)
            entry_hi = min(prod["max_age"], max_end - term)
        age = rng.randint(entry_lo, max(entry_lo, entry_hi)) + tenure
    cover, prev = _cover_and_premium(code, rng, age, term)
    change = rng.choice([0, 0, 2, 3, 5, 5, 8, 10, 12, 18, 25]) if expiry else 0
    step = 120 if prod["payment_frequency"] != PaymentFrequency.ANNUAL else 10
    premium = _round(prev * (100 + change) // 100, step) if change else prev
    owner = rng.choice(prod["channels"])
    if line == Line.GROUP:  # every scheme belongs to a different employer
        first, last = f"{next(c for c in COMPANIES if c not in used_companies)} LLC", ""
        used_companies.add(first.removesuffix(" LLC"))
    else:
        firsts, lasts = rng.choice(NAME_POOLS)
        first, last = rng.choice(firsts), rng.choice(lasts)
    docs_pool = rulebook.RENEWAL_DOCUMENTS[line]
    spec = PolicySpec(
        ref=f"PF{i:03d}-{line.value}",
        first=first,
        last=last,
        age=age,
        product=code,
        prev_premium=prev,
        premium=premium,
        sum_insured=cover,
        tenure=tenure,
        claims=rng.choice([0, 0, 0, 0, 1, 1, 2]) if expiry else 0,
        docs=rng.choice([[], [], [], [rng.choice(docs_pool)]]),
        auto_renew=expiry and rng.random() < 0.3,
        complaints=rng.choice([0, 0, 0, 0, 1, 2]),
        consent_email=rng.random() > 0.1,
        consent_sms=rng.random() > 0.3,
        consent_marketing=rng.random() > 0.2,
        preferred_channel=rng.choice([None, None, "email", "sms"]),
        channel_owner=owner,
        intermediary=(
            rng.choice(ADVISERS)
            if owner == ChannelOwner.ADVISER
            else rng.choice(BROKERS)
            if owner in (ChannelOwner.BROKER, ChannelOwner.EMPLOYER)
            else None
        ),
        term_years=term,
    )
    if expiry:
        spec.end_offset_days = rng.randint(-25, 120)
        spec.overdue_installments = rng.choice([0, 0, 0, 0, 0, 1])
        spec.monthly = code == "MEDICAL_FAMILY" and rng.random() < 0.4
    else:
        spec.overdue_days = rng.choice([0, 0, 0, 0, 0, 10, 25, 50])
        spec.failed_payments = rng.choice([0, 0, 0, 1])
        spec.review_offset_days = rng.randint(-20, 300)
        if prod["lifecycle_type"] == "milestone":
            spec.milestone_offset_days = rng.randint(10, 400)
            spec.milestone_label = "University fee payment"
    return spec


# ------------------------------------------------------------------ main ---

SIZES = {"small": 0, "full": 80}  # target total policies


async def seed(s: DbSession, size: str = "small") -> dict[str, int]:
    from renewal_backend.services import lifecycle  # late import: services import the graph

    as_of = today()
    s.add_all(Product(**p) for p in PRODUCTS)

    customers: list[Customer] = []
    policies: list[Policy] = []
    payments: list[Payment] = []
    for idx, spec in enumerate(scenario_policies()):
        c, p, pays = _policy_objects(spec, as_of, idx)
        customers.append(c)
        policies.append(p)
        payments.extend(pays)

    used_companies = {"Gulfline Logistics"}  # the handcrafted group scheme
    target_policies = SIZES[size]
    if target_policies:
        fake = Faker("en_US")
        Faker.seed(SEED)
        rng = random.Random(SEED)
        for i in range(max(0, target_policies - len(policies))):
            spec = _fake_policy_spec(fake, rng, i, used_companies)
            c, p, pays = _policy_objects(spec, as_of, 100 + i)
            customers.append(c)
            policies.append(p)
            payments.extend(pays)

    s.add_all(customers)
    await s.flush()
    s.add_all(policies)
    await s.flush()
    s.add_all(payments)
    await s.flush()
    # Lifecycle monitor's first pass: store each policy's next event.
    for p in policies:
        a = await lifecycle.assess_policy(s, p)
        if a is not None:
            lifecycle.record_next_event(p, a)
    return {
        "products": len(PRODUCTS),
        "customers": len(customers),
        "policies": len(policies),
        "payments": len(payments),
    }
