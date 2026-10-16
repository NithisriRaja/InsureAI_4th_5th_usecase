"""Scoring agent: rank the leads by buying interest.

Lead priority (LLM)."""

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
    result = await score_lead(d.llm, state["signals"], state.get("notes"))
    await audit(
        d.db,
        "node.scoring",
        {"band": result.band, "confidence": result.confidence, "score": result.score},
        subject_type="lead",
        subject_id=state["subject_id"],
    )
    return {"decisions": {"lead_score": result.model_dump(mode="json")}}
