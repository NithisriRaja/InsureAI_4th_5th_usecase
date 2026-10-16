"""Integration interfaces. The mocks read the working copy loaded from the CSV files; real
adapters (CRM, product catalogue) can implement the same protocols without touching nodes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from insurance_poc.db.models import Customer, Lead, Product


class CRM(Protocol):
    async def get_lead(self, lead_id: str) -> Lead | None: ...
    async def get_customer(self, customer_id: str) -> Customer | None: ...


class Catalogue(Protocol):
    async def get_product(self, code: str) -> Product | None: ...
    async def list_products(self, line: str | None = None) -> Sequence[Product]: ...
