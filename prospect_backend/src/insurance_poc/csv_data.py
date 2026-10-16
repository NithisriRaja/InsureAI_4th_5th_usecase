"""The CSV files the POC runs on: ``leads.csv``, ``products.csv`` and ``customers.csv``.

They are made for people: one column per fact, money in whole currency units, lists separated
by ``;`` (``none`` = an empty list), booleans as ``true`` / ``false``, blank = not given.
``load`` validates every row (all problems reported with file, row and column) and writes it
to the working copy the agents run on; the ``*_row`` helpers write it back the same way.
``result_row`` is the one-row-per-lead summary in ``results/ai_results.csv``.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc import rulebook
from insurance_poc.db.models import Customer, Lead, Product
from insurance_poc.utils.clock import utcnow
from insurance_poc.utils.ids import new_id
from insurance_poc.utils.normalize import lead_dedupe_hash, norm_phone

LIST_SEP = ";"
EMPTY_LIST = "none"
ENCODING = "utf-8-sig"  # Excel-friendly

# Declared facts (lead.declared) and how to read them. Money is whole units in the CSV and
# minor units in the database. Unknown extra columns are kept as text.
DECLARED: dict[str, str] = {
    # engagement
    "quote_requests_30d": "int",
    "pages_viewed": "int",
    "requested_callback": "bool",
    "days_since_inquiry": "int",
    # motor
    "vehicle_year": "int",
    "vehicle_value": "money",
    "driving_years": "int",
    "annual_mileage": "int",
    "prior_claims_3y": "int",
    # home
    "property_type": "str",
    "property_year": "int",
    "rebuild_value": "money",
    "security_alarm": "bool",
    # health / life
    "smoker": "bool",
    "bmi": "float",
    "pre_existing_conditions": "list",
    "occupation_risk": "str",
    "dependents": "int",
    "term_years": "int",
    "annual_income": "money",
    "existing_cover": "money",
    # savings
    "savings_goal": "str",
    "risk_appetite": "str",
    # employee benefits
    "employee_count": "int",
    "average_employee_age": "int",
    "industry_risk": "str",
}
PROTECTED = ("gender", "religion", "marital_status", "nationality")  # stored, never used

LEAD_BASE: dict[str, str] = {
    "lead_id": "str",
    "external_ref": "str",
    "first_name": "str",
    "last_name": "str",
    "dob": "date",
    "email": "str",
    "phone": "str",
    "city": "str",
    "product_line": "str",
    "sum_insured": "money",
    "source": "str",
    "channel_owner": "str",
    "intermediary": "str",
    "documents_provided": "list",
    "consent_profiling": "bool",
    "consent_marketing": "bool",
    "consent_email": "bool",
    "consent_sms": "bool",
    "existing_customer_id": "str",
    "notes": "str",
}
# Kept up to date by the app (csv storage); blank on a new row = "new" / now.
LEAD_STATE: dict[str, str] = {"status": "str", "created_at": "datetime"}
LEAD_COLUMNS = [*LEAD_BASE, *DECLARED, *(f"protected_{k}" for k in PROTECTED), *LEAD_STATE]

PRODUCT_BASE: dict[str, str] = {
    "code": "str",
    "line": "str",
    "name": "str",
    "tier": "str",
    "description": "str",
    "min_age": "int",
    "max_age": "int",
    "min_sum_insured": "money",
    "max_sum_insured": "money",
    "base_premium": "money",
    "payment_frequency": "str",
    "channels": "list",
    "regulated": "bool",
    "active": "bool",
}
# Keys of ``products.rules`` understood by services/rules/eligibility.py.
PRODUCT_RULES: dict[str, str] = {
    "max_vehicle_age": "int",
    "min_driving_years": "int",
    "max_property_age": "int",
    "min_dependents": "int",
    "non_smoker_only": "bool",
    "max_term_end_age": "int",
    "min_term_years": "int",
    "max_cover_income_multiple": "int",
    "min_employees": "int",
    "group_scheme": "bool",
}
PRODUCT_COLUMNS = [*PRODUCT_BASE, *(f"rule_{k}" for k in PRODUCT_RULES)]

CUSTOMER_BASE: dict[str, str] = {
    "customer_id": "str",
    "external_ref": "str",
    "first_name": "str",
    "last_name": "str",
    "dob": "date",
    "email": "str",
    "phone": "str",
    "city": "str",
    "consent_marketing": "bool",
    "consent_email": "bool",
    "consent_sms": "bool",
}
CUSTOMER_COLUMNS = [*CUSTOMER_BASE, *(f"protected_{k}" for k in PROTECTED)]

TRUE = {"true", "yes", "y", "1"}
FALSE = {"false", "no", "n", "0"}


class CsvError(ValueError):
    """Every problem found in the input files, with file, row and column."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


# ------------------------------------------------------------------ cells ---


def parse(kind: str, raw: str | None) -> Any:
    text = (raw or "").strip()
    if text == "":
        return None
    if kind == "str":
        return text
    if kind == "int":
        return int(float(text.replace(",", "")))
    if kind == "float":
        return float(text.replace(",", ""))
    if kind == "money":  # whole units in the file -> minor units
        return round(float(text.replace(",", "")) * 100)
    if kind == "bool":
        low = text.lower()
        if low in TRUE:
            return True
        if low in FALSE:
            return False
        raise ValueError(f"expected true/false, got {text!r}")
    if kind == "list":  # "none" = declared empty (e.g. no conditions), blank = not given
        if text.lower() == EMPTY_LIST:
            return []
        return [p.strip() for p in text.split(LIST_SEP) if p.strip()]
    if kind == "date":
        return date.fromisoformat(text)
    if kind == "datetime":
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    raise ValueError(f"unknown column type {kind}")


def show(kind: str, value: Any) -> str:
    if value is None:
        return ""
    if kind == "money":
        whole = value / 100
        return str(int(whole)) if whole == int(whole) else f"{whole:.2f}"
    if kind == "bool":
        return "true" if value else "false"
    if kind == "list":
        return LIST_SEP.join(str(v) for v in value) if value else EMPTY_LIST
    if kind in ("date", "datetime"):
        return value.isoformat()
    return str(value)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding=ENCODING, newline="") as f:
        return [{(k or "").strip(): v for k, v in row.items()} for row in csv.DictReader(f)]


def _write(path: Path, columns: list[str], rows: Iterable[dict[str, str]]) -> int:
    rows = list(rows)
    with path.open("w", encoding=ENCODING, newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def _cells(
    row: dict[str, str], types: dict[str, str], where: str, problems: list[str]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col, kind in types.items():
        try:
            out[col] = parse(kind, row.get(col))
        except ValueError as e:
            problems.append(f"{where}, column {col}: {e}")
    return out


# --------------------------------------------------------------- reading ---


def read_products(path: Path, problems: list[str]) -> list[Product]:
    out: list[Product] = []
    for i, row in enumerate(_read(path), start=2):
        where = f"{path.name} row {i}"
        v = _cells(row, PRODUCT_BASE, where, problems)
        rules = {
            k: val
            for k, val in _cells(
                {k: row.get(f"rule_{k}", "") for k in PRODUCT_RULES}, PRODUCT_RULES, where, problems
            ).items()
            if val is not None
        }
        if not v.get("code"):
            problems.append(f"{where}: code is required")
            continue
        if v.get("line") not in rulebook.LINES:
            problems.append(f"{where}: line must be one of {sorted(rulebook.LINES)}")
        for col in ("name", "min_age", "max_age", "min_sum_insured", "max_sum_insured"):
            if v.get(col) is None:
                problems.append(f"{where}: {col} is required")
        out.append(
            Product(
                code=v["code"],
                line=v.get("line"),
                name=v.get("name"),
                tier=v.get("tier") or "standard",
                description=v.get("description") or "",
                min_age=v.get("min_age"),
                max_age=v.get("max_age"),
                min_sum_insured=v.get("min_sum_insured"),
                max_sum_insured=v.get("max_sum_insured"),
                base_premium=v.get("base_premium") or 0,
                rules=rules,
                payment_frequency=v.get("payment_frequency") or "annual",
                channels=v.get("channels") or [],
                regulated=bool(v.get("regulated")),
                active=v.get("active") is not False,
            )
        )
    return out


def read_customers(path: Path, problems: list[str]) -> list[Customer]:
    out: list[Customer] = []
    for i, row in enumerate(_read(path), start=2):
        where = f"{path.name} row {i}"
        v = _cells(row, CUSTOMER_BASE, where, problems)
        for col in ("customer_id", "first_name", "last_name"):
            if not v.get(col):
                problems.append(f"{where}: {col} is required")
        out.append(
            Customer(
                id=v.get("customer_id") or "",
                external_ref=v.get("external_ref"),
                first_name=v.get("first_name") or "",
                last_name=v.get("last_name") or "",
                dob=v.get("dob"),
                email=v.get("email"),
                phone=norm_phone(v.get("phone")),
                city=v.get("city"),
                consent_marketing=bool(v.get("consent_marketing")),
                consent_email=bool(v.get("consent_email")),
                consent_sms=bool(v.get("consent_sms")),
                consent_updated_at=utcnow(),
                protected={
                    k: row[f"protected_{k}"].strip() for k in PROTECTED if row.get(f"protected_{k}")
                },
            )
        )
    _unique(out, "id", path.name, "customer_id", problems)
    return out


def read_leads(path: Path, problems: list[str], customer_ids: set[str]) -> list[Lead]:
    rows = _read(path)
    known = set(LEAD_COLUMNS)
    extra = [c for c in (rows[0].keys() if rows else []) if c and c not in known]
    out: list[Lead] = []
    for i, row in enumerate(rows, start=2):
        where = f"{path.name} row {i}"
        v = _cells(row, LEAD_BASE, where, problems)
        state = _cells(row, LEAD_STATE, where, problems)
        declared = {
            k: val for k, val in _cells(row, DECLARED, where, problems).items() if val is not None
        }
        declared.update({c: row[c].strip() for c in extra if (row.get(c) or "").strip()})
        protected = {
            k: row[f"protected_{k}"].strip() for k in PROTECTED if row.get(f"protected_{k}")
        }
        cust = v.get("existing_customer_id")
        if cust and cust not in customer_ids:
            problems.append(f"{where}: existing_customer_id {cust!r} is not in customers.csv")
        out.append(
            Lead(
                id=v.get("lead_id") or new_id("lead"),
                external_ref=v.get("external_ref"),
                dedupe_hash=lead_dedupe_hash(
                    product_line=v.get("product_line"),
                    email=v.get("email"),
                    phone=v.get("phone"),
                    first_name=v.get("first_name"),
                    last_name=v.get("last_name"),
                    dob=v.get("dob"),
                ),
                first_name=v.get("first_name"),
                last_name=v.get("last_name"),
                dob=v.get("dob"),
                email=v.get("email"),
                phone=v.get("phone"),
                city=v.get("city"),
                product_line=v.get("product_line"),
                sum_insured_requested=v.get("sum_insured"),
                declared=declared,
                notes=v.get("notes"),
                source=v.get("source") or rulebook.DEFAULT_SOURCE,
                channel_owner=v.get("channel_owner"),
                intermediary=v.get("intermediary"),
                documents_provided=v.get("documents_provided") or [],
                consent_profiling=v.get("consent_profiling") is not False,
                consent_marketing=bool(v.get("consent_marketing")),
                consent_email=bool(v.get("consent_email")),
                consent_sms=bool(v.get("consent_sms")),
                protected=protected,
                existing_customer_id=cust,
                status=state.get("status") or "new",
                **({"created_at": state["created_at"]} if state.get("created_at") else {}),
            )
        )
    _unique(out, "id", path.name, "lead_id", problems)
    _unique(out, "external_ref", path.name, "external_ref", problems)
    _unique(out, "dedupe_hash", path.name, "the same person and product line", problems)
    return out


def _unique(rows: list[Any], attr: str, file: str, label: str, problems: list[str]) -> None:
    seen: dict[Any, int] = {}
    for i, r in enumerate(rows, start=2):
        key = getattr(r, attr)
        if key is None:
            continue
        if key in seen:
            problems.append(f"{file} rows {seen[key]} and {i}: duplicate {label}")
        seen.setdefault(key, i)


async def load(s: AsyncSession, folder: Path) -> dict[str, int]:
    """Validate the CSVs in ``folder`` and add them to the database (one transaction)."""
    problems: list[str] = []
    products_csv, leads_csv = folder / "products.csv", folder / "leads.csv"
    customers_csv = folder / "customers.csv"
    for required in (products_csv, leads_csv):
        if not required.exists():
            problems.append(f"missing file: {required}")
    if problems:
        raise CsvError(problems)
    products = read_products(products_csv, problems)
    customers = read_customers(customers_csv, problems) if customers_csv.exists() else []
    leads = read_leads(leads_csv, problems, {c.id for c in customers})
    if problems:
        raise CsvError(problems)
    s.add_all(products)
    s.add_all(customers)
    await s.flush()
    s.add_all(leads)
    return {"products": len(products), "customers": len(customers), "leads": len(leads)}


# --------------------------------------------------------------- writing ---


def product_row(p: Any) -> dict[str, str]:
    row = {c: show(k, getattr(p, c)) for c, k in PRODUCT_BASE.items()}
    row["active"] = show("bool", p.active is not False)  # unsaved rows have no default yet
    for k, kind in PRODUCT_RULES.items():
        row[f"rule_{k}"] = show(kind, (p.rules or {}).get(k))
    return row


def customer_row(c: Customer) -> dict[str, str]:
    row = {col: show(k, getattr(c, col, None)) for col, k in CUSTOMER_BASE.items()}
    row["customer_id"] = c.id
    for k in PROTECTED:
        row[f"protected_{k}"] = str((c.protected or {}).get(k) or "")
    return row


def lead_columns(leads: Iterable[Lead]) -> list[str]:
    """Known columns, then any extra columns read from leads.csv (so a save never drops
    them). Extras go before the app-managed status/created_at columns."""
    known = set(LEAD_COLUMNS)
    extra = sorted({k for lead in leads for k in (lead.declared or {}) if k not in known})
    base = LEAD_COLUMNS[: -len(LEAD_STATE)]
    return [*base, *extra, *LEAD_STATE]


def lead_row(lead: Lead) -> dict[str, str]:
    attrs = {
        "lead_id": lead.id,
        "sum_insured": lead.sum_insured_requested,
    }
    row = {c: show(k, attrs.get(c, getattr(lead, c, None))) for c, k in LEAD_BASE.items()}
    for k, kind in DECLARED.items():
        row[k] = show(kind, (lead.declared or {}).get(k))
    for k, v in (lead.declared or {}).items():
        if k not in DECLARED:  # extra column the user added: keep it as text
            row[k] = "" if v is None else str(v)
    for k in PROTECTED:
        row[f"protected_{k}"] = str((lead.protected or {}).get(k) or "")
    row["status"] = lead.status or "new"
    row["created_at"] = show("datetime", lead.created_at)
    return row


# --------------------------------------------------------------- results ---

RESULT_COLUMNS = [
    "lead_id",
    "customer",
    "product_line",
    "lead_status",
    "ai_status",
    "approachability",
    "next_action",
    "priority",
    "team",
    "buying_interest",
    "interest_pct",
    "risk_band",
    "risk_pct",
    "underwriting",
    "best_product",
    "why_it_suits",
    "pain_points",
    "marketing_strategies",
    "also_suits",
    "not_suitable",
    "next_steps",
    "needs_review",
    "review_reasons",
    "ai_confidence",
    "recommendation_id",
    "checked_at",
]


def _pct(x: Any) -> str:
    return "" if x is None else str(round(float(x) * 100))


def result_row(lead: Lead, rec: Any | None) -> dict[str, str]:
    from insurance_poc.services import approachability, next_steps

    row = {
        "lead_id": lead.id,
        "customer": f"{lead.first_name or ''} {lead.last_name or ''}".strip(),
        "product_line": lead.product_line or "",
        "lead_status": lead.status,
        "ai_status": "not checked" if rec is None else rec.status,
    }
    if rec is None:
        return row
    dec: dict[str, Any] = rec.decisions or {}
    risk, interest = dec.get("risk") or {}, dec.get("lead_score") or {}
    fit = dec.get("product_fit") or {}
    uw = [r for r in rec.rule_results or [] if str(r.get("id", "")).startswith("underwriting.")]
    hits = [r for r in uw if not r.get("passed")]
    screening = (dec.get("product_screening") or {}).get("products") or []
    top = (rec.products or [{}])[0]
    subject = {
        "first_name": lead.first_name,
        "email": lead.email,
        "phone": lead.phone,
        "consent_email": lead.consent_email,
        "consent_sms": lead.consent_sms,
        "intermediary": lead.intermediary,
    }
    reach = approachability.compute(rec)
    row.update(
        approachability="" if reach["score"] is None else str(reach["score"]),
        next_action=rec.action,
        priority=rec.priority,
        team=rec.queue,
        buying_interest=interest.get("band") or "",
        interest_pct=_pct(interest.get("score")),
        risk_band=risk.get("band") or "",
        risk_pct=_pct(risk.get("score")),
        underwriting=(
            "knockout"
            if any(r.get("severity") == "block" for r in hits)
            else "refer"
            if hits
            else "clear"
            if uw
            else "not checked"
        ),
        best_product=str(top.get("name") or top.get("code") or ""),
        why_it_suits=" | ".join(r.get("explanation", "") for r in fit.get("reasons") or []),
        pain_points=" | ".join(r.get("explanation", "") for r in fit.get("pain_points") or []),
        marketing_strategies=" | ".join(
            f"{x.get('title', '')}: {x.get('how', '')}" for x in fit.get("strategies") or []
        ),
        also_suits=" | ".join(
            f"{x.get('name') or x.get('code')}: {x.get('rationale', '')}"
            for x in fit.get("also_suggest") or []
        ),
        not_suitable=" | ".join(
            f"{p['name']}: {'; '.join(p['reasons'])}"
            for p in screening
            if p.get("status") == "not_suitable"
        ),
        next_steps=" | ".join(
            f"{i}. {s['title']} ({s['owner']})"
            for i, s in enumerate(next_steps.for_lead(rec, subject), start=1)
        ),
        needs_review="true" if rec.needs_review else "false",
        review_reasons=" | ".join(str(r) for r in rec.review_reasons or []),
        ai_confidence=rec.confidence or "",
        recommendation_id=rec.id,
        checked_at=rec.created_at.isoformat() if rec.created_at else "",
    )
    return row


async def write_results(s: AsyncSession, path: Path) -> int:
    """One row per lead with its latest AI recommendation (or "not checked")."""
    from sqlalchemy import select

    from insurance_poc.db.models import Recommendation

    leads = (await s.execute(select(Lead).order_by(Lead.id))).scalars().all()
    recs = (
        (
            await s.execute(
                select(Recommendation)
                .where(Recommendation.subject_type == "lead")
                .order_by(Recommendation.created_at)
            )
        )
        .scalars()
        .all()
    )
    latest = {r.subject_id: r for r in recs}  # ordered by time: last one wins
    path.parent.mkdir(parents=True, exist_ok=True)
    return _write(path, RESULT_COLUMNS, (result_row(lead, latest.get(lead.id)) for lead in leads))
