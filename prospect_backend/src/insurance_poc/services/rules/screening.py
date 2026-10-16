"""Product screening: every catalogue product, with whether it suits the applicant and why not.

Pure rules, no LLM. Requested-line products use the full eligibility check; other lines use
the cross-line check (``rules.cross_sell``). Stored on the recommendation so a reviewer can
see why each product was or was not considered.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from insurance_poc import rulebook
from insurance_poc.services.rules.cross_sell import check_other_line
from insurance_poc.services.rules.eligibility import ProductLike, check_product, evidence
from insurance_poc.services.rules.facts import LeadFacts

ELIGIBLE = "eligible"
NOT_SUITABLE = "not_suitable"
NOT_ASSESSED = "not_assessed"


def screen(f: LeadFacts, products: Iterable[ProductLike]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in products:
        if p.line not in rulebook.LINES:
            continue
        proof: list[str] = []
        if p.line == f.product_line:
            fails = check_product(f, p).failures
            status, reasons = (NOT_SUITABLE, [r.reason for r in fails]) if fails else (ELIGIBLE, [])
            if not fails:
                proof = evidence(f, p)
        else:
            check = check_other_line(f, p)
            status, reasons = check.status, check.reasons
            if check.candidate is not None:  # assessed as that line, cover agreed later
                as_line = f.model_copy(
                    update={"product_line": p.line, "channel_owner": check.candidate.channel_owner}
                )
                proof = evidence(as_line, p, cover_checked=False)
        out.append(
            {
                "code": p.code,
                "name": p.name,
                "line": p.line,
                "requested_line": p.line == f.product_line,
                "status": status,
                "reasons": reasons,
                "evidence": proof,
            }
        )
    return out
