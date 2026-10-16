"""Engagement agent: plan the next best action, for staff approval.

Plan the next step: action, queue, priority and channel (rules + lead band, no LLM).

The engagement agent never contacts anyone. It decides who acts, how soon and by which route;
the personalised outreach (talking points, opener) comes from the product decision and is
turned into the team's to-do list by ``services/next_steps.py`` once a person approves.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from insurance_poc import rulebook
from insurance_poc.agents.base import BAND_PRIORITY, node
from insurance_poc.agents.state import GraphState, deps
from insurance_poc.enums import Action, Channel, Priority
from insurance_poc.services.rules.routing import owns_via_intermediary, route_queue
from insurance_poc.utils.audit import audit


@node("engagement")
async def engagement(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    d = deps(config)
    lead_score = state["decisions"]["lead_score"]
    owner = state.get("channel_owner")
    line = state["lead_facts"].product_line

    # Action/queue/priority are deterministic: rules + lead band, never free LLM choice.
    priority = Priority(BAND_PRIORITY[lead_score["band"]])
    if state["uw_outcome"] == "refer":
        action = Action.REFER_TO_UNDERWRITER
        priority = Priority.MEDIUM if priority == Priority.LOW else priority
    else:
        action = Action.NURTURE if lead_score["band"] == "cold" else Action.CONTACT_AND_QUOTE
    regulated = rulebook.LINES.get(line or "", {}).get("family") == "life"
    queue = route_queue(action, owner, regulated_product=regulated)
    channel = Channel.INTERMEDIARY.value if owns_via_intermediary(owner) else None

    await audit(
        d.db,
        "node.engagement",
        {"action": action, "queue": queue, "priority": priority, "channel_owner": owner},
        subject_type="lead",
        subject_id=state["subject_id"],
    )
    return {
        "action": action.value,
        "queue": queue.value,
        "priority": priority.value,
        "channel": channel,
        "band": lead_score["band"],
        "confidence": lead_score["confidence"],
    }
