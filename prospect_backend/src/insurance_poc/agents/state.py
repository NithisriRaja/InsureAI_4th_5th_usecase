"""Shared graph state and injected dependencies.

Nodes return partial updates. List/dict fields that several nodes contribute to use reducers
so updates accumulate instead of overwrite.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig

from insurance_poc.db.session import Database
from insurance_poc.integrations.base import CRM, Catalogue
from insurance_poc.services.llm.client import LLMClient
from insurance_poc.services.rules.facts import LeadFacts

Gate = Literal["pass", "do_not_contact", "request_info", "knockout"]


def merge_dicts(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    return {**(a or {}), **(b or {})}


class GraphState(TypedDict, total=False):
    # identity
    run_id: str
    use_case: str
    subject_type: str
    subject_id: str
    cycle_key: str
    as_of: date

    # loaded context (never sent to the LLM as-is)
    lead_facts: LeadFacts
    first_name: str | None
    eligible_products: list[dict[str, Any]]
    cross_sell_candidates: list[dict[str, Any]]
    uw_outcome: str
    channel_owner: str | None
    checklist: dict[str, Any]

    # accumulated evidence
    gate: Gate
    signals: dict[str, Any]
    notes: str | None
    fairness: dict[str, Any]
    rule_results: Annotated[list[dict[str, Any]], operator.add]
    missing_info: list[dict[str, Any]]
    decisions: Annotated[dict[str, Any], merge_dicts]
    forced_review: Annotated[list[str], operator.add]

    # recommendation draft
    action: str
    queue: str
    priority: str
    band: str | None
    confidence: str | None
    explanation: str | None
    products: list[dict[str, Any]]
    channel: str | None

    # output
    recommendation_id: str | None


@dataclass
class GraphDeps:
    db: Database
    llm: LLMClient
    crm: CRM
    catalogue: Catalogue


def deps(config: RunnableConfig) -> GraphDeps:
    return config["configurable"]["deps"]
