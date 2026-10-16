"""Relationship-owner resolution and approval routing (who owns the customer, who approves).

- Leads get a channel owner from (explicit value, product line, source), in that order.
  Adviser-led lines always land with an adviser; employee benefits with a broker or employer.
- Queues come from the approval matrix, then shift to the adviser queue for adviser-owned
  relationships and regulated (life / savings) products.
"""

from __future__ import annotations

from insurance_poc import rulebook
from insurance_poc.enums import Action, ChannelOwner, Queue, Role

QUEUE_ROLES: dict[str, set[Role]] = {
    Queue.SALES: {Role.SALES, Role.ADMIN},
    Queue.ADVISER: {Role.ADVISER, Role.ADMIN},
    Queue.UNDERWRITING: {Role.UNDERWRITER, Role.ADMIN},
}


def resolve_lead_owner(line: str | None, source: str | None, explicit: str | None) -> str:
    line_owners = tuple(rulebook.LINES[line]["owners"]) if line in rulebook.LINES else ()
    if explicit in {o.value for o in ChannelOwner} and (not line_owners or explicit in line_owners):
        return str(explicit)
    src = rulebook.SOURCES.get(source or "", rulebook.SOURCES[rulebook.DEFAULT_SOURCE])
    owner = src["owner"]
    if line_owners and owner not in line_owners:
        return str(line_owners[0])
    return str(owner)


def route_queue(action: str, channel_owner: str | None, *, regulated_product: bool) -> Queue:
    entry = rulebook.APPROVAL_MATRIX.get(action)
    if entry is None:
        raise KeyError(f"action {action!r} is not in the approval matrix")
    queue = Queue(entry["queue"])
    # Sales work on adviser-owned relationships or regulated products goes to an adviser.
    if queue == Queue.SALES and (channel_owner == ChannelOwner.ADVISER or regulated_product):
        return Queue.ADVISER
    return queue


def approver_roles(queue: str) -> set[Role]:
    return QUEUE_ROLES.get(queue, {Role.ADMIN})


def owns_via_intermediary(channel_owner: str | None) -> bool:
    """Broker / employer owns the relationship: contact goes to them, not the customer."""
    return (
        channel_owner in (ChannelOwner.BROKER, ChannelOwner.EMPLOYER)
        and not rulebook.BROKER_DIRECT_CONTACT_ALLOWED
    )


def is_acquisition_action(action: str) -> bool:
    return action in (
        Action.CONTACT_AND_QUOTE,
        Action.NURTURE,
        Action.REQUEST_INFO,
        Action.DO_NOT_CONTACT,
        Action.REFER_TO_UNDERWRITER,
    )
