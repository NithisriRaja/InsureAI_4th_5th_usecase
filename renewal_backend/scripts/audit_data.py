"""Check the CSV data for anything a real insurer's book would never contain.

Usage:
    python -m renewal_backend.scripts.audit_data          # prints every problem, exit 1 if any

Checks customers (names, ages, UAE mobiles, emails), products (catalogue sanity), policies
(term lengths, start / end dates, age at end of cover, policy-number year, cover within
product limits, premium in line with the cover) and payments (count, amounts, dates).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from renewal_backend import rulebook
from renewal_backend.config import get_settings
from renewal_backend.utils.clock import today

UAE_MOBILE = re.compile(r"^971(5[024568]\d{7}|[234679]\d{7})$")  # mobile or landline
EMAIL = re.compile(r"^[a-z0-9][a-z0-9.]*[a-z0-9]@[a-z0-9.-]+\.[a-z]{2,}$")
NAME = re.compile(r"^[A-Za-z][A-Za-z .,'&()-]*$")


def _rows(name: str) -> list[dict[str, str]]:
    with (get_settings().data_dir / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _age(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def audit(data_dir: Path | None = None) -> list[str]:
    if data_dir is not None:
        get_settings().data_dir = data_dir
    as_of = today()
    problems: list[str] = []
    bad = problems.append

    products = {p["code"]: p for p in _rows("products")}
    customers = {c["id"]: c for c in _rows("customers")}
    policies = _rows("policies")
    payments: dict[str, list[dict[str, str]]] = defaultdict(list)
    for pay in _rows("payments"):
        payments[pay["policy_id"]].append(pay)

    for code, p in products.items():
        ref = rulebook.product(code)
        if ref is None:
            bad(f"product {code}: not in the rulebook catalogue")
            continue
        if int(p["min_sum_insured"]) >= int(p["max_sum_insured"]):
            bad(f"product {code}: sum insured range is empty")

    group_customers = {p["customer_id"] for p in policies if p["line"] == "group"}
    for cid, c in customers.items():
        who = f"customer {cid} ({c['first_name']} {c['last_name']})"
        full = f"{c['first_name']} {c['last_name']}".strip()
        if not NAME.match(full):
            bad(f"{who}: name has unexpected characters")
        if not UAE_MOBILE.match(c["phone"] or ""):
            bad(f"{who}: phone {c['phone']!r} is not a UAE mobile number")
        if not EMAIL.match(c["email"] or ""):
            bad(f"{who}: email {c['email']!r} looks invalid")
        if cid in group_customers:
            if c["dob"]:
                bad(f"{who}: a company should have no date of birth")
        elif not c["dob"]:
            bad(f"{who}: person without a date of birth")
        elif not 18 <= _age(date.fromisoformat(c["dob"]), as_of) <= 85:
            bad(f"{who}: age {_age(date.fromisoformat(c['dob']), as_of)} is not plausible")

    numbers = set()
    for p in policies:
        num = p["policy_number"]
        who = f"policy {num}"
        if num in numbers:
            bad(f"{who}: duplicate policy number")
        numbers.add(num)
        prod = products.get(p["product_code"])
        cust = customers.get(p["customer_id"])
        if prod is None or cust is None:
            bad(f"{who}: unknown product or customer")
            continue
        start, end = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
        term_days = (end - start).days
        lifecycle = p["lifecycle_type"]
        fixed_term = lifecycle in ("expiry_renewal", "group_scheme_renewal")
        if num.split("-")[1] != str(start.year):
            bad(f"{who}: policy-number year differs from start year {start.year}")
        if start > as_of:
            bad(f"{who}: starts in the future ({start})")
        if fixed_term and not 364 <= term_days <= 366:
            bad(f"{who}: a yearly policy should run 1 year, runs {term_days} days")
        if not fixed_term:
            years = term_days / 365.25
            if not 4.5 <= years <= 30.5:
                bad(f"{who}: term of {years:.1f} years is not plausible")
            tenure = int(p["tenure_years"])
            on_book = (as_of - start).days / 365.25
            if abs(tenure - on_book) > 1:
                bad(f"{who}: 'customer for {tenure} years' but policy started {start}")
            if cust["dob"]:
                dob = date.fromisoformat(cust["dob"])
                entry, exit_ = _age(dob, start), _age(dob, end)
                if not int(prod["min_age"]) <= entry <= int(prod["max_age"]):
                    bad(f"{who}: entry age {entry} outside product ages")
                if exit_ > rulebook.MAX_COVER_END_AGE.get(p["product_code"], 75):
                    bad(f"{who}: cover ends at age {exit_}")
        elif cust["dob"]:
            age = _age(date.fromisoformat(cust["dob"]), as_of)
            if not int(prod["min_age"]) <= age <= int(prod["max_age"]):
                bad(f"{who}: customer age {age} outside product ages")
        si = int(p["sum_insured"])
        if not int(prod["min_sum_insured"]) <= si <= int(prod["max_sum_insured"]):
            bad(f"{who}: sum insured {si / 100:,.0f} outside the product range")
        lo, hi = rulebook.PREMIUM_RATE_BAND.get(p["product_code"], (0, 1))
        rate = int(p["prev_premium"]) / si if si else 0
        if p["payment_frequency"] != "single" and not lo <= rate <= hi:
            bad(f"{who}: premium {int(p['prev_premium']) / 100:,.0f} is {rate:.2%} of cover")
        change = (int(p["premium"]) - int(p["prev_premium"])) / int(p["prev_premium"]) * 100
        if not -10 <= change <= 35:
            bad(f"{who}: renewal price change {change:.0f}% is not plausible")
        for doc in json.loads(p["docs_outstanding"] or "[]"):
            if doc not in rulebook.RENEWAL_DOCUMENTS.get(p["line"], ()):
                bad(f"{who}: document {doc!r} is not a renewal document for {p['line']}")

        pays = sorted(payments[p["id"]], key=lambda x: x["due_date"])
        if not pays:
            bad(f"{who}: no payments")
            continue
        if any(not start <= date.fromisoformat(x["due_date"]) <= end for x in pays):
            bad(f"{who}: a payment falls outside the policy term")
        if any(date.fromisoformat(x["due_date"]) > as_of for x in pays):
            bad(f"{who}: payment dated in the future")
        amounts = {int(x["amount"]) for x in pays}
        freq = p["payment_frequency"]
        monthly = len(pays) > 1
        expect = int(p["prev_premium"]) // (12 if monthly else 1)
        if amounts != {expect}:
            bad(f"{who}: instalments {sorted(a / 100 for a in amounts)} != {expect / 100:,.2f}")
        if freq == "single" and len(pays) != 1:
            bad(f"{who}: single-premium plan with {len(pays)} payments")
        days = [date.fromisoformat(x["due_date"]).day for x in pays]
        if monthly and len(set(days)) > 2:
            bad(f"{who}: monthly instalments not on a fixed day of the month")
    return problems


def main() -> None:
    problems = audit()
    for line in problems:
        print("-", line)
    print(f"{len(problems)} problem(s) found")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
