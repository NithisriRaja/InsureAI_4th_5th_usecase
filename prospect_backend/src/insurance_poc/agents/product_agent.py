"""Product agent: match the prospect to suitable products.

Rank eligible products and suggest products from other lines (LLM, inside the rules)."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from insurance_poc.agents.base import node
from insurance_poc.agents.state import GraphState, deps
from insurance_poc.services.decisions.product_fit import rank_products
from insurance_poc.utils.audit import audit


@node("product")
async def product(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    d = deps(config)
    lead_score = state["decisions"]["lead_score"]
    risk = state["decisions"].get("risk") or {}
    eligible = state.get("eligible_products") or []

    ranked: list[dict[str, Any]] = []
    llm_review: tuple[bool, str | None] = (False, None)
    decisions: dict[str, Any] = {}

    if eligible:
        others = state.get("cross_sell_candidates") or []
        ranking = await rank_products(
            d.llm,
            signals=state["signals"],
            eligible=eligible,
            lead_band=lead_score["band"],
            risk_band=risk.get("band"),
            uw_outcome=state["uw_outcome"],
            other_products=others,
        )
        names = {p["code"]: p["name"] for p in eligible}
        ranked = [{**p.model_dump(), "name": names.get(p.code)} for p in ranking.ranked]
        explanation = ranking.explanation
        llm_review = (ranking.needs_review, ranking.review_reason)
        fit = ranking.model_dump(mode="json")
        # Keep the rule facts (line, owner, referral) next to each suggestion for the reviewer.
        by_code = {p["code"]: p for p in others}
        fit["also_suggest"] = [
            {**by_code[s["code"]], **s} for s in fit["also_suggest"] if s["code"] in by_code
        ]
        decisions = {"product_fit": fit}
    else:
        # Refer with no eligible product (e.g. sum insured above every limit).
        explanation = "No catalogue product fits; manual underwriting needed."

    await audit(
        d.db,
        "node.product",
        {
            "ranked": [p["code"] for p in ranked],
            "also_suggest": [
                s["code"] for s in decisions.get("product_fit", {}).get("also_suggest", [])
            ],
        },
        subject_type="lead",
        subject_id=state["subject_id"],
    )
    return {
        "decisions": decisions,
        "products": ranked,
        "explanation": explanation,
        "forced_review": [f"LLM flagged: {llm_review[1] or 'no reason given'}"]
        if llm_review[0]
        else [],
    }
