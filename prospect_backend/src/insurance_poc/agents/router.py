from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from insurance_poc.agents.base import node
from insurance_poc.agents.state import GraphState
from insurance_poc.enums import SubjectType, UseCase

EXPECTED_SUBJECT = {UseCase.ACQUISITION: SubjectType.LEAD}


@node("router")
async def router(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    use_case = state.get("use_case")
    if use_case not in EXPECTED_SUBJECT:
        raise ValueError(f"unknown use_case: {use_case!r}")
    if state.get("subject_type") != EXPECTED_SUBJECT[use_case]:
        raise ValueError(f"{use_case} expects subject_type {EXPECTED_SUBJECT[use_case]}")
    return {}
