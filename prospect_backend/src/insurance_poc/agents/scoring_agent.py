"""Scoring agent: rank the leads by buying interest.

Lead priority is a fixed points formula (``services/decisions/lead_score.py``), not the AI."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from insurance_poc.agents.base import node
from insurance_poc.agents.state import GraphState, deps
from insurance_poc.services.decisions.lead_score import score_lead
from insurance_poc.utils.audit import audit


@node("scoring")
async def scoring(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    d = deps(config)
    risk_band = (state["decisions"].get("risk") or {}).get("band")
    result = score_lead(state["signals"], risk_band)
    await audit(
        d.db,
        "node.scoring",
        {"band": result["band"], "confidence": result["confidence"], "score": result["score"]},
        subject_type="lead",
        subject_id=state["subject_id"],
    )
    return {"decisions": {"lead_score": result}}
