"""The new-customer (acquisition) LangGraph.

START -> router -> prospect -(gate fail)-> finalize
                   prospect -> risk -(knock-out: underwriter decides)-> finalize
                   risk -> scoring -> product -> engagement -> finalize -> END

One node per agent in the use case: prospect, risk, scoring, product, engagement.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from insurance_poc.agents.engagement_agent import engagement
from insurance_poc.agents.finalize import finalize
from insurance_poc.agents.product_agent import product
from insurance_poc.agents.prospect_agent import prospect, route_after_prospect
from insurance_poc.agents.risk_agent import risk, route_after_risk
from insurance_poc.agents.router import router
from insurance_poc.agents.scoring_agent import scoring
from insurance_poc.agents.state import GraphDeps, GraphState
from insurance_poc.utils.clock import today
from insurance_poc.utils.context import run_context


def build_graph() -> Any:
    g = StateGraph(GraphState)
    for name, fn in [
        ("router", router),
        ("prospect", prospect),
        ("risk", risk),
        ("scoring", scoring),
        ("product", product),
        ("engagement", engagement),
        ("finalize", finalize),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "router")
    g.add_edge("router", "prospect")
    g.add_conditional_edges("prospect", route_after_prospect, ["risk", "finalize"])
    g.add_conditional_edges("risk", route_after_risk, ["scoring", "finalize"])
    g.add_edge("scoring", "product")
    g.add_edge("product", "engagement")
    g.add_edge("engagement", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


@lru_cache
def get_graph() -> Any:
    return build_graph()


def cycle_key_for(use_case: str, subject_id: str) -> str:
    """One recommendation cycle per lead (a re-run supersedes the open recommendation)."""
    return subject_id


async def run_graph(
    *,
    run_id: str,
    use_case: str,
    subject_type: str,
    subject_id: str,
    cycle_key: str,
    deps: GraphDeps,
) -> GraphState:
    state: GraphState = {
        "run_id": run_id,
        "use_case": use_case,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "cycle_key": cycle_key,
        "as_of": today(),
        "rule_results": [],
        "decisions": {},
        "forced_review": [],
    }
    with run_context(run_id):
        return await get_graph().ainvoke(state, config={"configurable": {"deps": deps}})
