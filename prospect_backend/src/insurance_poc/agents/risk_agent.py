"""Risk agent: summarise the risk and flag cases for an underwriter.

Underwriting referral rules first; LLM risk summary only if no knock-out.

A knock-out never becomes a decline here: the case goes to an underwriter, who decides.
Also finds products from other lines the applicant qualifies for (``rules.cross_sell``).
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from insurance_poc.agents.base import node
from insurance_poc.agents.state import GraphState, deps
from insurance_poc.services.decisions import features
from insurance_poc.services.decisions.features import major
from insurance_poc.services.decisions.risk import assess_risk
from insurance_poc.services.rules import cross_sell, screening, underwriting
from insurance_poc.services.rules.types import dump
from insurance_poc.utils.audit import audit


def _summary(p: Any) -> dict[str, Any]:
    return {
        "code": p.code,
        "name": p.name,
        "tier": p.tier,
        "description": p.description,
        "payment_frequency": p.payment_frequency,
        "base_premium": major(p.base_premium),
        "min_sum_insured": major(p.min_sum_insured),
        "max_sum_insured": major(p.max_sum_insured),
    }


@node("risk")
async def risk(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    d = deps(config)
    facts = state["lead_facts"]
    catalogue = list(await d.catalogue.list_products())
    by_code = {p.code: p for p in catalogue}
    uw = underwriting.assess(facts, catalogue)
    eligible = [_summary(by_code[c]) for c in uw.eligible_products]
    update: dict[str, Any] = {
        "uw_outcome": uw.outcome.value,
        "eligible_products": eligible,
        "cross_sell_candidates": [],
        "rule_results": dump(uw.results),
        # Rule-only view of the whole catalogue (why each product does or does not fit).
        "decisions": {"product_screening": {"products": screening.screen(facts, catalogue)}},
    }
    found: list[cross_sell.CrossLineCandidate] = []
    if uw.outcome == underwriting.UWOutcome.KNOCKOUT:
        update["gate"] = "knockout"
    else:
        found = cross_sell.candidates(facts, catalogue)
        update["cross_sell_candidates"] = [
            cross_sell.describe(c, _summary(by_code[c.code])) for c in found
        ]
        signals = dict(state["signals"])
        for line in cross_sell.signal_lines(found):
            for k, v in features.line_signals(facts, line).items():
                signals.setdefault(k, v)
        update["signals"] = signals
        findings = [r.reason for r in uw.results if not r.passed]
        decision = await assess_risk(d.llm, state["signals"], uw.outcome.value, findings)
        update["decisions"]["risk"] = decision.model_dump(mode="json")
        if uw.outcome == underwriting.UWOutcome.REFER:
            update["forced_review"] = ["Underwriting referral: " + "; ".join(findings)]
    await audit(
        d.db,
        "node.risk",
        {
            "uw_outcome": uw.outcome.value,
            "rules_hit": [r.id for r in uw.results if not r.passed],
            "eligible": uw.eligible_products,
            "cross_sell_candidates": [c.code for c in found],
            "risk_band": update.get("decisions", {}).get("risk", {}).get("band"),
        },
        subject_type="lead",
        subject_id=state["subject_id"],
    )
    return update


def route_after_risk(state: GraphState) -> str:
    return "finalize" if state.get("gate") == "knockout" else "scoring"
