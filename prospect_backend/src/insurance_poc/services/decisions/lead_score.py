"""Lead priority score: a plain points formula, no AI.

A customer who is easy and sensible to quote scores high. Four parts add up to 100, so the same
customer always gets the same score and every point can be explained:

- risk (40): low 40, medium 20, high 0;
- dependants (20): the fewer people relying on them, the higher (0-1: 20, 2: 14, 3: 8, 4+: 3);
- cover amount (25): reasonable for them. Up to 10x yearly income (the rulebook's protection
  need) is fully reasonable; savings must stay within 15% of income; motor and home cover
  should not exceed the vehicle or rebuild value;
- application and interest (15): how much of the form is done (10), plus up to 5 for asking
  for a call back or quotes or filling it in themselves. An enquiry over a month old takes 10 off.

70+ is hot (contact today), 40-69 warm (this week), below 40 cold (keep warm only).
Insurability itself is still decided by the underwriting rules, not here.
"""

from __future__ import annotations

from typing import Any

from insurance_poc import rulebook

HOT_FROM = 70
WARM_FROM = 40
RISK_POINTS = {"low": 40, "medium": 20, "high": 0}
INTENT_KEYS = ("requested_callback", "quote_requests_30d", "days_since_inquiry", "pages_viewed")
UNKNOWN = "was not given"


def _number(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _risk(risk_band: str | None) -> tuple[int, str]:
    if risk_band not in RISK_POINTS:
        return 20, "Risk was not rated, so it counts as average."
    return RISK_POINTS[risk_band], f"{risk_band.capitalize()} risk."


def _dependants(sig: dict[str, Any]) -> tuple[int, str]:
    n = _number(sig.get("dependents"))
    if n is None:
        return 10, "Number of dependants " + UNKNOWN + ", so it counts as average."
    n = int(n)
    pts = 20 if n <= 1 else 14 if n == 2 else 8 if n == 3 else 3
    return pts, "No one depends on them." if n == 0 else f"{n} dependant(s) rely on them."


def _amount(sig: dict[str, Any]) -> tuple[int, str, str]:
    cover = _number(sig.get("sum_insured"))
    income = _number(sig.get("annual_income"))
    saving = _number(sig.get("saving_pct_of_income"))
    limit = rulebook.SAVINGS_AFFORDABILITY_MAX_PCT
    if saving is not None:
        ok = saving <= limit
        text = f"Saving {saving:g}% of income, " + ("within" if ok else "above") + f" {limit}%."
        return (25 if ok else 8), text, "saving_pct_of_income"
    if cover and income:
        times = cover / income
        pts = 25 if times <= 10 else 15 if times <= 15 else 8 if times <= 20 else 0
        word = "reasonable" if pts == 25 else "on the high side" if pts else "very high"
        return pts, f"Cover is {times:.1f}x yearly income, {word}.", "sum_insured"
    for key, label in (("vehicle_value", "vehicle"), ("rebuild_value", "rebuild")):
        value = _number(sig.get(key))
        if cover and value:
            ok = cover <= value
            side = "within" if ok else "above"
            return (25 if ok else 8), f"Cover asked for is {side} the {label} value.", "sum_insured"
    if cover:
        return 15, "A cover amount was asked for, with nothing to compare it with.", "sum_insured"
    return 10, "Cover amount " + UNKNOWN + ".", "sum_insured"


def _interest(sig: dict[str, Any]) -> tuple[int, str, str]:
    pct = _number(sig.get("application_completeness_pct"))
    pts = round(max(0.0, min(100.0, pct)) * 0.10) if pct is not None else 0
    bits = [f"{round(pct)}% of the application is done"] if pct is not None else []
    key = "application_completeness_pct"
    if not any(k in sig for k in INTENT_KEYS):
        pts += 3
        bits.append("they filled it in themselves")
    else:
        extra = 0
        if sig.get("requested_callback"):
            extra += 3
            bits.append("asked for a call back")
            key = "requested_callback"
        if (_number(sig.get("quote_requests_30d")) or 0) >= 1:
            extra += 2
            bits.append("asked for a quote")
        pts += min(extra, 5)
        days = _number(sig.get("days_since_inquiry"))
        if days is not None and days > 30:
            pts -= 10
            bits.append("last enquired over a month ago, so interest has cooled")
            key = "days_since_inquiry"
    return pts, (", ".join(bits).capitalize() + ".") if bits else "No sign of interest yet.", key


def score_lead(signals: dict[str, Any], risk_band: str | None) -> dict[str, Any]:
    risk_pts, risk_text = _risk(risk_band)
    dep_pts, dep_text = _dependants(signals)
    amt_pts, amt_text, amt_key = _amount(signals)
    int_pts, int_text, int_key = _interest(signals)
    parts = [
        ("Risk", risk_pts, 40, risk_text, "risk_band"),
        ("Dependants", dep_pts, 20, dep_text, "dependents"),
        ("Cover amount", amt_pts, 25, amt_text, amt_key),
        ("Application and interest", int_pts, 15, int_text, int_key),
    ]
    total = max(0, sum(p[1] for p in parts))
    band = "hot" if total >= HOT_FROM else "warm" if total >= WARM_FROM else "cold"
    known = sum(
        1
        for ok in (
            risk_band in RISK_POINTS,
            "dependents" in signals,
            UNKNOWN not in amt_text,
            "application_completeness_pct" in signals,
        )
        if ok
    )
    return {
        "band": band,
        "score": round(total / 100, 2),
        "confidence": "high" if known >= 4 else "medium" if known >= 3 else "low",
        "reasons": [
            {"signal": key, "explanation": f"{label} {pts}/{top}: {text}"}
            for label, pts, top, text, key in sorted(parts, key=lambda p: -p[1])
        ],
        "breakdown": [{"label": p[0], "points": p[1], "max": p[2], "why": p[3]} for p in parts],
    }
