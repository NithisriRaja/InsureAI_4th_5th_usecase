"""Prospect agent: find the right prospects (approved data and consent only).

Load the lead and apply the permission, consent and data-quality gates. No LLM here.

Order: data permission (purpose) -> outreach consent (given the relationship owner) -> data
quality -> application prep checklist. A lead stopped early is never profiled.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from insurance_poc.agents.base import node
from insurance_poc.agents.state import GraphState, deps
from insurance_poc.services.decisions import features
from insurance_poc.services.rules import application, consent, data_quality
from insurance_poc.services.rules.facts import lead_facts
from insurance_poc.services.rules.types import dump
from insurance_poc.utils.audit import audit


class SubjectNotFound(LookupError):
    code = "subject_not_found"


@node("prospect")
async def prospect(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
    d = deps(config)
    lead = await d.crm.get_lead(state["subject_id"])
    if lead is None:
        raise SubjectNotFound(f"lead {state['subject_id']} not found")
    facts = lead_facts(lead, state["as_of"])
    update: dict[str, Any] = {
        "lead_facts": facts,
        "first_name": lead.first_name,
        "channel_owner": facts.channel_owner,
    }

    missing: list[dict[str, Any]] = []
    checklist: dict[str, Any] = {}
    permission = consent.check_lead_permission(facts)
    results = [permission]
    if not permission.passed:
        gate = "do_not_contact"
    else:
        outreach = consent.check_lead_consent(facts)
        results.append(outreach)
        if not outreach.passed:
            gate = "do_not_contact"
        else:
            dq_results, missing = data_quality.check_lead_data(facts)
            results += dq_results
            gate = "pass" if not missing else "request_info"
            if gate == "pass":
                checklist, app_results = application.prepare(facts)
                results += app_results
                update["forced_review"] = [
                    f"Suitability: {r.reason}"
                    for r in app_results
                    if r.id.startswith("suitability.") and not r.passed
                ]

    if permission.passed:
        notes, fairness_report = features.lead_notes(facts)
        signals = features.lead_signals(facts, checklist)
    else:
        # Purpose limitation: data we may not profile is not turned into signals at all.
        notes, fairness_report = None, features.redact_text(None)[1]
        signals = {
            "product_line": facts.product_line,
            "source": facts.source,
            "channel_owner": facts.channel_owner,
        }
    update.update(
        gate=gate,
        rule_results=dump(results),
        missing_info=missing,
        checklist=checklist,
        signals=signals,
        notes=notes,
        fairness=fairness_report.model_dump(),
    )
    await audit(
        d.db,
        "node.prospect",
        {
            "gate": gate,
            "channel_owner": facts.channel_owner,
            "rules": [r.id for r in results if not r.passed],
            "missing": [m["field"] for m in missing],
            "documents_missing": checklist.get("documents_missing", []),
            "notes_redactions": fairness_report.redactions,
        },
        subject_type="lead",
        subject_id=lead.id,
    )
    return update


def route_after_prospect(state: GraphState) -> str:
    return "risk" if state["gate"] == "pass" else "finalize"
