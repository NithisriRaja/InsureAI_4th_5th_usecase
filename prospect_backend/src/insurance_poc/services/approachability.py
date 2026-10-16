"""Approachability: one 0-100 score per lead for "should the team reach out, and how keen".

Deterministic, from the stored recommendation:
- the rules forbid contact (no data permission / consent)  -> 0, "not approachable";
- details are missing, or a knock-out sent it to an underwriter before any scoring
                                                          -> no score, with the reason;
- otherwise                                               -> the AI's buying-interest score x 100.
A referral keeps its score but says the underwriter decides first.
"""

from __future__ import annotations

import re
from typing import Any

from insurance_poc.enums import Action

BANDS = (
    (70, "high", "Highly approachable"),
    (40, "medium", "Approachable"),
    (0, "low", "Low priority"),
)


def plain(text: str) -> str:
    """Rule reasons quote codes ('purchased_list'); show them as words (purchased list)."""
    return re.sub(r"'([a-z0-9_]+)'", lambda m: m.group(1).replace("_", " "), text)


def _when(days: int) -> str:
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"


def interest_facts(sig: dict[str, Any]) -> str:
    """The engagement facts behind buying interest, as a short plain phrase."""
    bits: list[str] = []
    if sig.get("requested_callback"):
        bits.append("asked for a call back")
    quotes = sig.get("quote_requests_30d")
    if isinstance(quotes, int):
        bits.append(f"asked for {quotes} quote(s) this month" if quotes else "no quote requested")
    days = sig.get("days_since_inquiry")
    if isinstance(days, int):
        bits.append(f"enquired {_when(days)}")
    pages = sig.get("pages_viewed")
    if isinstance(pages, int):
        bits.append(f"viewed {pages} page(s)")
    if sig.get("requested_callback") is False and not sig.get("requested_callback"):
        bits.append("no call back requested")
    return ", ".join(bits)


def _first_block(rec: Any, prefixes: tuple[str, ...]) -> str | None:
    for r in rec.rule_results or []:
        if not r.get("passed") and str(r.get("id", "")).startswith(prefixes):
            return plain(str(r.get("reason") or "")).rstrip(".")
    return None


def compute(rec: Any | None) -> dict[str, Any]:
    if rec is None:
        return {"score": None, "band": None, "label": "Not checked", "reason": "Run the AI."}
    if rec.action == Action.DO_NOT_CONTACT:
        why = _first_block(rec, ("consent.",)) or "Consent or data-use rules forbid contact"
        return {"score": 0, "band": "none", "label": "Not approachable", "reason": f"{why}."}
    if rec.action == Action.REQUEST_INFO:
        fields = ", ".join(
            str(m.get("field", "")).replace("declared.", "").replace("_", " ")
            for m in rec.missing_info or []
        )
        return {
            "score": None,
            "band": None,
            "label": "Can't score yet",
            "reason": f"Missing details: {fields}." if fields else "Details are missing.",
        }
    interest = ((rec.decisions or {}).get("lead_score") or {}).get("score")
    if interest is None:
        why = _first_block(rec, ("underwriting.",)) or "The risk needs a specialist"
        return {
            "score": None,
            "band": None,
            "label": "Underwriter first",
            "reason": f"{why}; not scored until an underwriter decides.",
        }
    score = max(0, min(100, round(float(interest) * 100)))
    band, label = next((b, lbl) for floor, b, lbl in BANDS if score >= floor)
    facts = interest_facts(rec.signals or {})
    reason = (
        f"Buying interest {score}%"
        + (f": {facts}" if facts else "")
        + ". Consent and data checks passed."
    )
    if rec.action == Action.REFER_TO_UNDERWRITER:
        # Interest is real, but nobody may reach out yet: never shown as "approachable".
        why = _first_block(rec, ("underwriting.",))
        return {
            "score": score,
            "band": "hold",
            "label": "On hold: underwriter first",
            "reason": f"{score}% buying interest, but an underwriter must clear the risk "
            f"before anyone calls" + (f" ({why[0].lower() + why[1:]})." if why else "."),
        }
    if rec.action == Action.NURTURE:
        reason = (
            f"Only {score}% buying interest" + (f" ({facts})" if facts else "") + ". "
            "Risk is checked separately, so a low-risk customer can still be low priority."
        )
    return {"score": score, "band": band, "label": label, "reason": reason}
