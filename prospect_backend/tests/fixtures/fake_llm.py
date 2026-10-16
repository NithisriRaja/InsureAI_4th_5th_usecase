"""Deterministic, rule-respecting fake LLM for graph tests (never used by the app)."""

from __future__ import annotations

import json
import re
from typing import Any

from insurance_poc.services.llm.client import LLMClient
from insurance_poc.services.llm.providers.fake import FakeProvider
from insurance_poc.services.llm.ratelimit import RateLimiter
from insurance_poc.services.llm.recorder import DbRecorder
from insurance_poc.services.llm.retry import RetryPolicy
from insurance_poc.services.llm.types import ChatMessage

_DATA = re.compile(r"<data>\n(.*)\n</data>", re.DOTALL)


def payload(messages: list[ChatMessage]) -> dict[str, Any]:
    user = next(m.content for m in messages if m.role == "user")
    return json.loads(_DATA.search(user).group(1))


def _reason(signals: dict[str, Any]) -> list[dict[str, str]]:
    key = next(iter(sorted(signals)))
    return [{"signal": key, "explanation": f"based on {key}"}]


def smart_responder(purpose: str, messages: list[ChatMessage]) -> dict[str, Any]:
    data = payload(messages)
    sig = data.get("signals", {})
    if purpose == "lead_score":
        if sig.get("requested_callback"):
            band, score = "hot", 0.85
        elif (sig.get("days_since_inquiry") or 0) > 30:
            band, score = "cold", 0.15
        else:
            band, score = "warm", 0.5
        return {"band": band, "score": score, "confidence": "high", "reasons": _reason(sig)}
    if purpose == "risk_assessment":
        return {
            "band": "medium",
            "score": 0.5,
            "confidence": "medium",
            "reasons": _reason(sig),
            "summary": "Average risk.",
        }
    if purpose == "product_fit":
        codes = [p["code"] for p in data["eligible_products"]]
        others = [p["code"] for p in data.get("other_products", [])]
        return {
            "ranked": [{"code": c, "fit": "high", "rationale": "fits"} for c in codes],
            "recommended_code": codes[0],
            "reasons": _reason(sig),
            "also_suggest": [
                {"code": c, "rationale": "also fits", "reasons": _reason(sig)} for c in others[:1]
            ],
            "explanation": "Recommend the first eligible product.",
            "pitch": "This cover fits what you told us.",
            "watch_out": None,
            "talking_points": _reason(sig),
            "pain_points": _reason(sig),
            "strategies": [
                {
                    "title": "Lead with the benefit",
                    "how": "Explain what the cover gives them.",
                    "signal": next(iter(sorted(sig))),
                }
            ],
            "confidence": "high",
            "needs_review": False,
            "review_reason": None,
        }
    raise AssertionError(f"unexpected purpose {purpose}")


def fake_llm(responder=smart_responder) -> tuple[LLMClient, FakeProvider]:
    async def no_sleep(_: float) -> None:
        return None

    provider = FakeProvider(responder)
    client = LLMClient(
        provider,
        mode="prompt",
        limiter=RateLimiter(0, 4),
        retry=RetryPolicy(max_attempts=2, max_total_wait_s=1, base_s=0, cap_s=0, sleep=no_sleep),
        recorder=DbRecorder(),
    )
    return client, provider
