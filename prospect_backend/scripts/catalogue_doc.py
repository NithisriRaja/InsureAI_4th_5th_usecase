"""Regenerate docs/product_catalogue.md from prospect_backend/data_csv/products.csv.

Usage:
    python scripts/catalogue_doc.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from insurance_poc import rulebook
from insurance_poc.config import get_settings

RULE_TEXT = {
    "max_vehicle_age": "car ≤ {} yrs",
    "min_driving_years": "≥ {} yrs driving",
    "max_property_age": "property ≤ {} yrs",
    "min_dependents": "≥ {} dependent(s)",
    "non_smoker_only": "non-smokers only",
    "max_term_end_age": "term ends by age {}",
    "min_term_years": "term ≥ {} yrs",
    "max_cover_income_multiple": "cover ≤ {}× income",
    "min_employees": "≥ {} employees",
    "group_scheme": "company applicant",
}


def _k(text: str) -> str:
    n = float(text)
    return (
        f"{n / 1_000_000:g}M" if n >= 1_000_000 else f"{n / 1_000:g}k" if n >= 1_000 else f"{n:g}"
    )


def main() -> None:
    root = Path(__file__).resolve().parents[2]  # project root (docs/ sits next to prospect_backend/)
    rows = list(
        csv.DictReader((get_settings().data_dir / "products.csv").open(encoding="utf-8-sig"))
    )
    out = [
        "# Product catalogue",
        "",
        f"Generated from `prospect_backend/data_csv/products.csv` ({len(rows)} products) by "
        "`prospect_backend/scripts/catalogue_doc.py`. Edit the CSV, not this page. Amounts are whole "
        "currency units.",
        "",
    ]
    for line, spec in rulebook.LINES.items():
        items = [r for r in rows if r["line"] == line]
        if not items:
            continue
        out += [
            f"## {spec['label']}",
            "",
            f"- **Sold through:** {', '.join(str(o) for o in spec['owners'])}",
            f"- **Facts needed before the AI can assess:** "
            f"{', '.join(k.replace('_', ' ') for k in spec['required'])}",
            f"- **Application documents:** "
            f"{', '.join(d.replace('_', ' ') for d in spec['documents'])}",
            "",
            "| Product | What it covers | Age | Cover | Base premium | Rules | Active |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in items:
            rules = [
                RULE_TEXT[k].format(r[f"rule_{k}"])
                for k in RULE_TEXT
                if r.get(f"rule_{k}") and r[f"rule_{k}"] != "false"
            ]
            age = (
                "n/a" if r.get("rule_group_scheme") == "true" else f"{r['min_age']}–{r['max_age']}"
            )
            out.append(
                f"| **{r['name']}** (`{r['code']}`) | {r['description']} | {age} | "
                f"{_k(r['min_sum_insured'])} – {_k(r['max_sum_insured'])} | "
                f"{_k(r['base_premium'])} / {r['payment_frequency']} | "
                f"{'; '.join(rules) or '—'} | {r['active']} |"
            )
        out.append("")
    out += [
        "## How the agent uses this",
        "",
        "- A product is offered only if the applicant's age, requested cover and the "
        "product's rules pass, and it is sold through the customer's relationship owner.",
        "- The AI ranks only those products, and may add up to two products from other lines "
        "the rules also allow (see business_rules.md, section 5).",
        "",
    ]
    (root / "docs" / "product_catalogue.md").write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote docs/product_catalogue.md ({len(rows)} products)")


if __name__ == "__main__":
    main()
