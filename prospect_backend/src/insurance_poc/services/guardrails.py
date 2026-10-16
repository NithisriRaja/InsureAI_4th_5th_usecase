"""Non-negotiable guardrails, enforced in code (not only in prompts).

The agent never binds or issues cover, never sets a price, never declines, never acts without
approval and never goes around the broker / employer that owns the relationship.
``check_recommendation`` runs on every recommendation before it is stored; a violation raises
(the run fails) and is written to the audit log by the caller.
"""

from __future__ import annotations

from typing import Any

from insurance_poc import rulebook
from insurance_poc.enums import Channel
from insurance_poc.services.rules.routing import owns_via_intermediary

CUSTOMER_CHANNELS = (Channel.EMAIL, Channel.SMS, Channel.EMAIL_SMS)


class GuardrailViolation(Exception):
    code = "guardrail_violation"

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


def assert_agent_may(action: str) -> None:
    """Only actions in the approval matrix may be proposed; forbidden ones never."""
    if action in rulebook.FORBIDDEN_AGENT_ACTIONS:
        raise GuardrailViolation("guardrail.forbidden_action", f"agent may not '{action}'")
    if action not in rulebook.APPROVAL_MATRIX:
        raise GuardrailViolation("guardrail.unknown_action", f"'{action}' not in approval matrix")


def check_recommendation(rec: dict[str, Any]) -> None:
    """Raise if a recommendation draft breaks a guardrail. ``rec`` = column values."""
    action = rec["action"]
    assert_agent_may(action)
    channel = rec.get("channel")
    if channel in CUSTOMER_CHANNELS and owns_via_intermediary(rec.get("channel_owner")):
        raise GuardrailViolation(
            "guardrail.bypass_intermediary",
            f"{rec.get('channel_owner')}-owned relationship cannot be messaged directly",
        )
    if rec.get("status") not in (None, "pending_approval"):
        raise GuardrailViolation(
            "guardrail.auto_execute", "recommendations must wait for human approval"
        )
