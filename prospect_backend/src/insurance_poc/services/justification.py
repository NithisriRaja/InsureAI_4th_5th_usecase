"""Explain a stored recommendation to the approver: which rules and AI judgements led to it.

Built on read from what the run already stored (rule results, LLM decisions, run audit), so
it needs no extra LLM call and works for every recommendation ever created. The output is a
decision path (one step per stage, each marked as a hard rule, an AI judgement or fixed
policy), the criteria met / not met, and what the approver should check before deciding.
"""

from __future__ import annotations

from typing import Any

from insurance_poc import rulebook
from insurance_poc.enums import Action, ChannelOwner, Queue
from insurance_poc.services.approachability import plain

ACTION_TEXT = {
    Action.CONTACT_AND_QUOTE: "contact and quote",
    Action.NURTURE: "nurture",
    Action.REQUEST_INFO: "request missing information",
    Action.DO_NOT_CONTACT: "do not contact",
    Action.REFER_TO_UNDERWRITER: "refer to an underwriter",
}
QUEUE_TEXT = {
    Queue.SALES: "Sales",
    Queue.ADVISER: "Adviser",
    Queue.UNDERWRITING: "Underwriting",
}
OWNER_TEXT = {o.value: o.value.replace("_", " ") for o in ChannelOwner}


def _act(action: str) -> str:
    return ACTION_TEXT.get(action, action.replace("_", " "))  # type: ignore[call-overload]


def _human(key: str) -> str:
    return key.replace("declared.", "").replace("_", " ")


def _step(
    key: str,
    title: str,
    basis: str,
    status: str,
    outcome: str,
    details: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "basis": basis,  # rule | ai | policy
        "status": status,  # pass | fail | warn | skipped | info
        "outcome": outcome,
        "details": [d for d in details or [] if d],
    }


def _rules(rules: list[dict[str, Any]], *prefixes: str) -> list[dict[str, Any]]:
    return [r for r in rules if r.get("id", "").startswith(prefixes)]


def _rule_status(rules: list[dict[str, Any]]) -> str:
    if any(not r["passed"] and r["severity"] in ("block", "refer") for r in rules):
        return "fail"
    if any(not r["passed"] and r["severity"] == "warn" for r in rules):
        return "warn"
    return "pass"


def _ai_reasons(d: dict[str, Any] | None, signals: dict[str, Any], limit: int = 3) -> list[str]:
    out = []
    for r in (d or {}).get("reasons", [])[:limit]:
        sig = r.get("signal", "")
        val = signals.get(sig)
        shown = f" = {val}" if val is not None and not isinstance(val, (dict, list)) else ""
        out.append(f"{_human(sig)}{shown}: {r.get('explanation', '')}")
    return out


def _ai_line(name: str, d: dict[str, Any] | None) -> str:
    if not d:
        return ""
    score = d.get("score")
    pct = f", score {round(score * 100)}/100" if isinstance(score, (int, float)) else ""
    return f"{name}: {d.get('band')} ({d.get('confidence')} confidence{pct})"


def _routing(rec: Any) -> dict[str, Any]:
    entry = rulebook.APPROVAL_MATRIX.get(rec.action) or {}
    base = entry.get("queue")
    details = [
        f"Approval matrix sends '{_act(rec.action)}' to the {QUEUE_TEXT.get(base, base)} queue."
    ]
    if base and base != rec.queue and rec.queue == Queue.ADVISER:
        details.append(
            "Moved to the Adviser queue: an adviser owns this relationship or the product "
            "is regulated advice."
        )
    if rec.channel == "intermediary":
        details.append(
            f"Relationship owned by the {OWNER_TEXT.get(rec.channel_owner or '', 'intermediary')}: "
            "contact goes through them, never directly to the customer."
        )
    if entry.get("regulated_advice"):
        details.append("Regulated advice: needs a licensed adviser's approval.")
    return _step(
        "routing",
        "Who approves",
        "policy",
        "info",
        f"{QUEUE_TEXT.get(rec.queue, rec.queue)} queue, {rec.priority} priority",
        details,
    )


def _fairness(rec: Any) -> dict[str, Any]:
    f = rec.fairness or {}
    cats = f.get("categories") or []
    details = ["Protected traits (gender, religion, nationality, ...) are never sent to the AI."]
    if f.get("redactions"):
        details.append(
            f"{f['redactions']} sensitive detail(s) removed from notes before the AI saw them"
            + (f" ({', '.join(cats)})." if cats else ".")
        )
    for v in f.get("violations") or []:
        details.append(f"Violation: {v}")
    ok = f.get("passed", True)
    return _step(
        "fairness",
        "Fairness check",
        "rule",
        "pass" if ok else "fail",
        "Passed" if ok else "Failed",
        details,
    )


# --------------------------------------------------------------- acquisition


def _acquisition(rec: Any) -> tuple[list[dict[str, Any]], str, list[str]]:
    rules: list[dict[str, Any]] = rec.rule_results or []
    dec: dict[str, Any] = rec.decisions or {}
    sig: dict[str, Any] = rec.signals or {}
    action = rec.action
    steps: list[dict[str, Any]] = []
    because: list[str] = []

    consent = _rules(rules, "consent.", "routing.")
    blocked = [r for r in consent if not r["passed"] and r["severity"] == "block"]
    steps.append(
        _step(
            "consent",
            "Consent and permission",
            "rule",
            _rule_status(consent),
            "Blocked: may not be contacted" if blocked else "Allowed to profile and contact",
            [r["reason"] for r in consent],
        )
    )
    if blocked:
        because.append("a consent rule blocks contact")

    dq = _rules(rules, "data_quality.")
    missing = [m.get("field", "") for m in rec.missing_info or []]
    stopped_dq = action == Action.REQUEST_INFO
    steps.append(
        _step(
            "data_quality",
            "Data completeness",
            "rule",
            "skipped" if not dq else _rule_status(dq),
            "Not reached"
            if not dq
            else f"Missing or invalid: {', '.join(_human(m) for m in missing)}"
            if stopped_dq
            else "All mandatory fields present and valid",
            [r["reason"] for r in dq],
        )
    )
    if stopped_dq:
        because.append(f"mandatory data is missing ({', '.join(_human(m) for m in missing)})")

    uw = _rules(rules, "underwriting.")
    knock = [r for r in uw if not r["passed"] and r["severity"] == "block"]
    refer = [r for r in uw if not r["passed"] and r["severity"] == "refer"]
    if not uw:
        uw_out, uw_status = "Not reached: an earlier check stopped the case", "skipped"
    elif knock:
        uw_out, uw_status = "Knock-out rule hit: underwriter must decide", "fail"
        because.append("a knock-out underwriting rule was hit")
    elif refer:
        uw_out, uw_status = "Referral rule hit: underwriter must review", "fail"
        because.append("an underwriting referral rule was hit")
    else:
        uw_out, uw_status = "Clear: no referral rules hit", "pass"
    uw_details = [r["reason"] for r in uw]
    if dec.get("risk"):
        uw_details.append(
            _ai_line("AI risk summary", dec["risk"]) + " (adds colour, never changes the outcome)"
        )
    steps.append(_step("underwriting", "Underwriting rules", "rule", uw_status, uw_out, uw_details))

    app = _rules(rules, "application.", "suitability.")
    if app:
        steps.append(
            _step(
                "application",
                "Application and suitability",
                "rule",
                _rule_status(app),
                "Open items for the approver"
                if _rule_status(app) != "pass"
                else "Complete and suitable",
                [r["reason"] for r in app],
            )
        )

    ls = dec.get("lead_score")
    if ls:
        steps.append(
            _step(
                "interest",
                "Buying interest",
                "ai",
                "info",
                _ai_line("Rated", ls),
                _ai_reasons(ls, sig),
            )
        )
    else:
        steps.append(
            _step("interest", "Buying interest", "ai", "skipped", "Not rated: AI not used", [])
        )

    pf = dec.get("product_fit")
    products = rec.products or []
    if products:
        top = products[0]
        steps.append(
            _step(
                "product",
                "Product match",
                "ai",
                "info",
                f"Best match: {top.get('name') or top.get('code')} ({top.get('fit')} fit)",
                [
                    f"Ranked only among {len(products)} product(s) the eligibility rules allow.",
                    top.get("rationale", ""),
                    (pf or {}).get("explanation", ""),
                ],
            )
        )
        extra = _also_suggest(rec)
        if extra:
            steps.append(
                _step(
                    "cross_sell",
                    "Other products that suit",
                    "ai",
                    "info",
                    "Also suits: " + ", ".join(str(x.get("name") or x["code"]) for x in extra),
                    [
                        f"{x.get('name') or x['code']}: {x.get('rationale', '')}"
                        + (" Needs an underwriter." if x.get("needs_underwriter") else "")
                        for x in extra
                    ]
                    + ["Picked only from other lines' products the eligibility rules allow."],
                )
            )
    elif uw and not knock:
        steps.append(
            _step(
                "product",
                "Product match",
                "rule",
                "fail",
                "No eligible catalogue product",
                ["Manual underwriting needed."],
            )
        )

    band = (ls or {}).get("band")
    if action == Action.DO_NOT_CONTACT:
        rule = "Any blocking consent rule means do not contact. The AI was not used."
    elif action == Action.REQUEST_INFO:
        rule = "Mandatory data missing or invalid means ask for it before any scoring. AI not used."
    elif action == Action.REFER_TO_UNDERWRITER and knock:
        rule = "A knock-out rule means refer to an underwriter. The system never declines."
    elif action == Action.REFER_TO_UNDERWRITER:
        rule = "Any underwriting referral means refer to an underwriter, whatever the interest."
    elif action == Action.NURTURE:
        rule = "Underwriting clear and interest rated cold means nurture, not active contact."
        because.append("underwriting is clear but buying interest is cold")
    else:
        rule = f"Underwriting clear and interest rated {band} (not cold) means contact and quote."
        because.append(f"underwriting is clear and buying interest is {band}")
    prio = (
        f"Priority {rec.priority}: set from the interest band (hot=high, warm=medium, cold=low)"
        if band
        else f"Priority {rec.priority}: fixed for this outcome"
    )
    if action == Action.REFER_TO_UNDERWRITER and band == "cold":
        prio += ", raised to medium for referrals"
    steps.append(
        _step("decision", "How the action was chosen", "policy", "info", _act(action), [rule, prio])
    )
    return steps, ", ".join(because), _checks_common(rec, rules)


def _tidy(text: str) -> str:
    """'Smoker aged 50 or over.; High-risk occupation.' -> 'Smoker aged 50 or over · High-risk
    occupation'."""
    parts = [p.strip().rstrip(".").strip() for p in text.split(";")]
    return " · ".join(p for p in parts if p)


def _item(kind: str, title: str, detail: str = "") -> dict[str, str]:
    return {"kind": kind, "title": title, "detail": detail}


def _split_reason(reason: str) -> tuple[str, str]:
    """'Prefix: rest' -> (prefix, rest) when the prefix is a short label."""
    head, sep, rest = reason.partition(":")
    if sep and 0 < len(head) <= 40:
        detail = _tidy(rest)
        return head.strip(), detail[:1].upper() + detail[1:]
    return _tidy(reason), ""


def _checks_common(rec: Any, rules: list[dict[str, Any]]) -> list[dict[str, str]]:
    """What the approver should confirm before approving, as short title + detail."""
    items: list[dict[str, str]] = []
    for r in rec.review_reasons or []:
        text = str(r)
        if text.startswith("LLM flagged:"):
            items.append(_item("flag", "AI flagged a concern", text.split(":", 1)[1].strip()))
        else:
            title, detail = _split_reason(text)
            items.append(_item("rule", title, detail))
    seen = " ".join(i["title"] + " " + i["detail"] for i in items)
    for r in rules:
        if not r["passed"] and r["severity"] == "warn" and _tidy(r["reason"]) not in seen:
            missing = (r.get("data") or {}).get("missing")
            if r["id"] == "application.documents" and missing:
                docs = ", ".join(_human(m) for m in missing)
                items.append(
                    _item("rule", "Documents still to collect", docs[:1].upper() + docs[1:])
                )
                continue
            title, detail = _split_reason(r["reason"])
            items.append(_item("rule", title, detail))
    if rec.confidence in ("low", "medium"):
        items.append(
            _item(
                "confidence",
                f"AI is only {rec.confidence}-confident",
                "Check the key facts in 'Facts used' before you approve.",
            )
        )
    if rec.action == Action.REFER_TO_UNDERWRITER:
        items.append(
            _item(
                "decision",
                "The cover call is yours",
                "The system never accepts or declines: you decide on the cover.",
            )
        )
    extra = _also_suggest(rec)
    if extra and rec.action in (Action.CONTACT_AND_QUOTE, Action.REFER_TO_UNDERWRITER):
        names = ", ".join(str(x.get("name") or x["code"]) for x in extra)
        uw = [str(x.get("name") or x["code"]) for x in extra if x.get("needs_underwriter")]
        items.append(
            _item(
                "cross_sell",
                "Other products are only a talking point",
                f"{names}. Raise them only if relevant; each needs its own quote"
                + (f", and {', '.join(uw)} needs an underwriter." if uw else "."),
            )
        )
    if rec.action == Action.DO_NOT_CONTACT:
        items.append(
            _item("decision", "This logs a do-not-contact", "Nobody reaches out to this person.")
        )
    if rec.action == Action.REQUEST_INFO:
        fields = ", ".join(_human(m.get("field", "")) for m in rec.missing_info or [])
        items.append(
            _item("decision", "The gaps are real", f"Confirm these are missing or wrong: {fields}.")
        )
    if rec.channel == "intermediary":
        items.append(
            _item(
                "channel",
                "Goes via the broker / employer",
                "Not straight to the customer: they own the relationship.",
            )
        )
    return items


# The business concern each step protects, shown next to it.
ASPECT = {
    "consent": "Compliance",
    "data_quality": "Data quality",
    "underwriting": "Risk appetite",
    "application": "Suitability & KYC",
    "interest": "Sales pipeline",
    "product": "Product fit",
    "cross_sell": "Cross-sell",
    "decision": "Business policy",
    "routing": "Governance",
    "fairness": "Fair treatment",
}


def _first_fail(rules: list[dict[str, Any]], *prefixes: str) -> str:
    for r in _rules(rules, *prefixes):
        if not r["passed"] and r["severity"] in ("block", "refer"):
            return plain(r["reason"]).rstrip(".")
    return ""


def _num(x: Any) -> str:
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


def headline(rec: Any, products: list[dict[str, Any]]) -> str:
    """One plain, punchy line a busy approver can act on."""
    rules: list[dict[str, Any]] = rec.rule_results or []
    dec: dict[str, Any] = rec.decisions or {}
    a = rec.action
    top = (products or [{}])[0]
    product = top.get("name") or top.get("code")
    if a == Action.DO_NOT_CONTACT:
        why = _first_fail(rules, "consent.", "routing.") or "no permission to contact"
        return f"Hands off: {why.lower()}. We log it and move on, no outreach."
    if a == Action.REQUEST_INFO:
        fields = ", ".join(_human(m.get("field", "")) for m in rec.missing_info or [])
        missing = fields or "key details"
        return f"Can't judge this one blind. Missing {missing}: ask first, score later."
    if a == Action.REFER_TO_UNDERWRITER:
        why = _first_fail(rules, "underwriting.") or "the risk needs a specialist"
        if any(
            not r["passed"] and r["severity"] == "block" for r in _rules(rules, "underwriting.")
        ):
            return f"Hard stop: {why.lower()}. Only an underwriter can make this call."
        return f"Worth a look, but {why[0].lower() + why[1:]}. Underwriter's eyes first."
    if a == Action.NURTURE:
        return "Not shopping yet. Keep it warm with light-touch nurture, no hard sell."
    if a == Action.CONTACT_AND_QUOTE:
        band = (dec.get("lead_score") or {}).get("band")
        lead = {"hot": "Hot lead", "warm": "Warm lead"}.get(band or "", "Good lead")
        risk = (dec.get("risk") or {}).get("band")
        clean = "clean risk" if risk in (None, "low") else f"{risk} risk"
        when = "call today" if band == "hot" else "call this week"
        return f"{lead}, {clean}: {when}" + (f" and lead with {product}." if product else ".")
    return f"Next step: {_act(a)}."


def _cited_facts(rec: Any) -> list[dict[str, Any]]:
    """Every fact an AI judgement leaned on, with its value and the AI's own words."""
    sig: dict[str, Any] = rec.signals or {}
    out: list[dict[str, Any]] = []
    names = {
        "lead_score": "Buying interest",
        "risk": "Risk",
        "product_fit": "Product fit",
    }
    groups = [
        (label, (rec.decisions or {}).get(key, {}).get("reasons", []) or [])
        for key, label in names.items()
    ]
    groups += [
        (f"Also suits: {x.get('name') or x['code']}", x.get("reasons") or [])
        for x in _also_suggest(rec)
    ]
    for label, reasons in groups:
        for r in reasons:
            s = r.get("signal", "")
            out.append(
                {
                    "signal": s,
                    "value": sig.get(s),
                    "explanation": r.get("explanation", ""),
                    "judgement": label,
                }
            )
    return out


def _also_suggest(rec: Any) -> list[dict[str, Any]]:
    """Other-line products the AI suggested (stored on the product_fit decision)."""
    fit = (rec.decisions or {}).get("product_fit") or {}
    return [x for x in fit.get("also_suggest") or [] if isinstance(x, dict) and x.get("code")]


def build(
    rec: Any, events: list[Any], products: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    steps, because, checks = _acquisition(rec)
    steps += [_routing(rec), _fairness(rec)]
    for s in steps:
        s["aspect"] = ASPECT.get(s["key"], "")
    rule_steps = [s for s in steps if s["basis"] == "rule"]
    summary = f"Recommends: {_act(rec.action)}" + (f", because {because}." if because else ".")
    return {
        "headline": headline(rec, products if products is not None else rec.products or []),
        "summary": summary[0].upper() + summary[1:],
        "cited_facts": _cited_facts(rec),
        "steps": steps,
        "criteria_met": [s["title"] for s in rule_steps if s["status"] == "pass"],
        "criteria_not_met": [s["title"] for s in rule_steps if s["status"] in ("fail", "warn")],
        "approver_items": checks,
        "approver_checks": [
            f"{c['title']}: {c['detail']}" if c["detail"] else c["title"] for c in checks
        ],
        "ai_used": any(s["basis"] == "ai" and s["status"] != "skipped" for s in steps),
        "rulebook_version": rec.rulebook_version,
    }
