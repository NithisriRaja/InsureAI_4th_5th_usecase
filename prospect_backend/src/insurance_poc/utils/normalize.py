from __future__ import annotations

import hashlib
import re
from datetime import date


def norm_email(email: str | None) -> str | None:
    if not email:
        return None
    email = email.strip().casefold()
    return email or None


def norm_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return digits or None


def lead_dedupe_hash(
    *,
    product_line: str | None,
    email: str | None,
    phone: str | None,
    first_name: str | None,
    last_name: str | None,
    dob: date | None,
) -> str:
    """Same person asking for the same line counts as a duplicate lead.

    Identity = normalised email + phone; falls back to name + dob when neither is present.
    """
    e, p = norm_email(email), norm_phone(phone)
    if e or p:
        key = f"{product_line}|{e or ''}|{p or ''}"
    else:
        key = (
            f"{product_line}|{(first_name or '').strip().casefold()}|"
            f"{(last_name or '').strip().casefold()}|{dob or ''}"
        )
    return hashlib.sha256(key.encode()).hexdigest()


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def mask_phone(phone: str | None) -> str | None:
    digits = norm_phone(phone)
    if not digits:
        return None
    return f"***{digits[-3:]}"
