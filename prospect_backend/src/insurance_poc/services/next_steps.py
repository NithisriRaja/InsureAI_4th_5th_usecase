"""What the team does next on a new-customer case, as a short ordered to-do list.

Who acts, by which route and how soon is decided here by rules, from the customer's own facts
(callback request, days since they enquired, quotes asked for, owner, consent, missing
documents), so it can never route around a broker or contact someone without consent. What to
say comes from the AI's grounded ``talking_points`` on the product decision. Nothing here
contacts anyone; it tells staff what to do once the recommendation is approved.
"""

from __future__ import annotations

from typing import Any

from insurance_poc.enums import Action, ChannelOwner, RecStatus
from insurance_poc.services.approachability import plain

TEAM = {
    "sales": "Sales & marketing",
    "adviser": "Adviser",
    "underwriting": "Underwriter",
}
PRIORITY_HINT = {
    "high": "High priority: contact first.",
    "medium": "Contact after the high-priority customers.",
    "low": "Low priority: contact when the busier cases are done.",
}


def _step(
    title: str,
    detail: str,
    owner: str,
    kind: str,
    done: bool = False,
    items: list[str] | None = None,
    quote: str | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "detail": detail,
        "owner": owner,
        "kind": kind,
        "done": done,
        "items": items or [],
        "quote": quote,  # a line to say, shown with a copy button
    }


def _words(keys: list[str]) -> str:
    return ", ".join(k.replace("declared.", "").replace("_", " ") for k in keys)


def _sentences(parts: Any) -> list[str]:
    """'A.; B' fragments -> ['A.', 'B.'] (unique, tidy full stops)."""
    out: list[str] = []
    for part in parts:
        for bit in str(part).split(";"):
            bit = plain(bit).strip().rstrip(".").strip()
            if bit and f"{bit}." not in out:
                out.append(f"{bit[0].upper()}{bit[1:]}.")
    return out


def _named(name: str, text: Any) -> str:
    """'Name: text', without repeating the name when the text already starts with it."""
    text = str(text or "").strip()
    if not text:
        return name
    return text if text.lower().startswith(name.lower()) else f"{name}: {text}"


def _days(n: Any) -> str:
    return "today" if n == 0 else "yesterday" if n == 1 else f"{n} days ago"


def timing(sig: dict[str, Any], priority: str) -> str:
    """How soon to reach out, from the engagement facts (falls back to the priority)."""
    days = sig.get("days_since_inquiry")
    quotes = sig.get("quote_requests_30d") or 0
    pages = sig.get("pages_viewed") or 0
    if sig.get("requested_callback"):
        when = f" {_days(days)}" if isinstance(days, int) else ""
        return f"They asked for a call back{when}: call today, while they expect it."
    if isinstance(days, int) and days <= 3 and quotes:
        return (
            f"Enquired {_days(days)} and asked for {quotes} quote(s) this month: "
            "reach out within 24 hours."
        )
    if isinstance(days, int) and days <= 7:
        return f"Enquired {_days(days)}: reach out this week, while it is fresh."
    if isinstance(days, int) and days > 30:
        return (
            f"Last enquired {days} days ago, so interest may have cooled: "
            "open with a short check-in, not a hard sell."
        )
    if pages >= 5:
        return f"Looked at {pages} pages on our site: they are researching, so follow up soon."
    return PRIORITY_HINT.get(priority, "")


def _contact(rec: Any, lead: dict[str, Any], team: str) -> dict[str, Any]:
    first = (lead.get("first_name") or lead.get("name") or "the customer").split(" ")[0]
    sig: dict[str, Any] = rec.signals or {}
    pitch = ((rec.decisions or {}).get("product_fit") or {}).get("pitch")
    when = timing(sig, rec.priority)
    if sig.get("existing_customer"):
        when += f" {first} already has a policy with us: mention it."
    owner = rec.channel_owner
    if owner in (ChannelOwner.BROKER, ChannelOwner.EMPLOYER):
        who = lead.get("intermediary") or f"the {owner}"
        return _step(
            f"Ask {who} to contact {first}",
            f"{when} The {owner} owns this customer, so we never contact them directly.",
            "Broker desk",
            "contact",
            quote=pitch,
        )
    if owner == ChannelOwner.ADVISER:
        return _step(
            f"Book a needs meeting with {first}",
            f"{when} A licensed adviser leads the conversation (regulated product).",
            "Adviser",
            "contact",
            quote=pitch,
        )
    ways = [
        w
        for w, ok in (
            ("email", lead.get("consent_email") and lead.get("email")),
            ("SMS", lead.get("consent_sms") and lead.get("phone")),
        )
        if ok
    ]
    how = " or ".join(ways) if ways else "a channel they have consented to"
    return _step(f"Contact {first} by {how}", when, team, "contact", quote=pitch)


def for_lead(rec: Any, lead: dict[str, Any]) -> list[dict[str, Any]]:
    team = TEAM.get(rec.queue, rec.queue)
    action = rec.action
    steps: list[dict[str, Any]] = []
    first = (lead.get("first_name") or lead.get("name") or "the customer").split(" ")[0]

    if rec.status == RecStatus.REJECTED:
        return [_step("No action", "The recommendation was rejected by a reviewer.", team, "stop")]
    if rec.status in (RecStatus.SUPERSEDED, RecStatus.EXPIRED):
        return [_step("Re-run the AI", f"This recommendation is {rec.status}.", team, "rerun")]
    approved = rec.status in (RecStatus.APPROVED, RecStatus.APPROVED_WITH_EDITS)
    steps.append(
        _step(
            "Approve the AI suggestion",
            "Nothing happens with the customer until a reviewer approves it.",
            team,
            "approve",
            done=approved,
        )
    )

    sig: dict[str, Any] = rec.signals or {}
    checklist: dict[str, Any] = rec.checklist or {}
    products = [p for p in rec.products or [] if isinstance(p, dict)]
    fit = (rec.decisions or {}).get("product_fit") or {}
    extra = [x for x in fit.get("also_suggest") or [] if isinstance(x, dict)]

    if action == Action.DO_NOT_CONTACT:
        why = next(
            (plain(r["reason"]) for r in rec.rule_results or [] if not r.get("passed")),
            "Consent or data-use rules do not allow contact.",
        )
        return [
            *steps,
            _step(f"Do not contact {first}", why, team, "stop"),
            _step(
                "Remove from campaigns",
                "Keep them off marketing lists until their consent or the data source changes.",
                team,
                "stop",
            ),
        ]
    if action == Action.REQUEST_INFO:
        fields = [m.get("field", "") for m in rec.missing_info or []]
        return [
            *steps,
            _step(
                f"Ask {first} for the missing details",
                f"Missing or invalid: {_words(fields)}." if fields else "Some details are missing.",
                team,
                "collect",
            ),
            _step(
                "Run the AI again",
                f"Once {first}'s details are in, run the check again to get a product match.",
                team,
                "rerun",
            ),
        ]
    if action == Action.REFER_TO_UNDERWRITER:
        reasons = _sentences(str(r).split(":", 1)[-1] for r in rec.review_reasons or [])
        steps += [
            _step(
                "Underwriter reviews the case",
                " ".join(reasons) or "Underwriting rules need a human decision.",
                "Underwriter",
                "review",
            ),
            _step(
                f"Hold: no quote for {first} yet",
                f"Sales waits for the underwriter. {timing(sig, rec.priority)}".strip(),
                team,
                "wait",
            ),
        ]
        return steps
    if action == Action.NURTURE:
        days = sig.get("days_since_inquiry")
        pages = sig.get("pages_viewed")
        seen = []
        if isinstance(days, int):
            seen.append(f"last enquired {_days(days)}")
        if isinstance(pages, int):
            seen.append(f"looked at {pages} page(s)")
        if not sig.get("quote_requests_30d"):
            seen.append("has not asked for a quote")
        return [
            *steps,
            _step(
                "No sales call now",
                f"{first} {', '.join(seen) or 'shows little interest'}. Keep them warm with "
                "general information only, and only where they have marketing consent.",
                team,
                "nurture",
            ),
            _step(
                "Run the AI again when they engage",
                f"For example when {first} asks for a quote or a call back.",
                team,
                "rerun",
            ),
        ]

    # contact_and_quote
    steps.append(_contact(rec, lead, team))
    points = [str(t.get("explanation", "")) for t in fit.get("talking_points") or [] if t]
    if points:
        steps.append(
            _step(
                "In the conversation",
                f"Plan for the call with {first}, based on what we know about them:",
                team,
                "talk",
                items=points,
            )
        )
    if products:
        top = products[0]
        name = top.get("name") or top.get("code")
        steps.append(
            _step(
                f"Quote {name}",
                str(top.get("rationale") or "Best fit for this customer."),
                team,
                "quote",
            )
        )
    if extra:
        uw = [str(x.get("name") or x["code"]) for x in extra if x.get("needs_underwriter")]
        steps.append(
            _step(
                "Mention " + " and ".join(str(x.get("name") or x["code"]) for x in extra),
                "Only if it fits the conversation; each is quoted separately"
                + (f", and {', '.join(uw)} needs a risk check first." if uw else "."),
                team,
                "cross_sell",
                items=[_named(str(x.get("name") or x["code"]), x.get("rationale")) for x in extra],
            )
        )
    docs = checklist.get("documents_missing") or []
    if docs:
        steps.append(
            _step(
                f"Collect {len(docs)} document(s) from {first}",
                _words(docs).capitalize() + ".",
                team,
                "collect",
            )
        )
    evidence = [
        e.get("item") if isinstance(e, dict) else str(e)
        for e in checklist.get("evidence_required") or []
    ]
    if evidence:
        steps.append(
            _step(
                "Arrange medical evidence",
                _words([e for e in evidence if e]).capitalize() + ".",
                "Adviser",
                "collect",
            )
        )
    return steps
