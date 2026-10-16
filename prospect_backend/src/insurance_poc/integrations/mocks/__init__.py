"""Mock integrations over the working copy. Each call uses its own short read session."""

from __future__ import annotations

from collections.abc import Sequence

from insurance_poc.db.models import Customer, Lead, Product
from insurance_poc.db.repositories import catalogue as catalogue_repo
from insurance_poc.db.repositories import leads as leads_repo
from insurance_poc.db.session import Database


class MockCRM:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_lead(self, lead_id: str) -> Lead | None:
        async with self.db.session() as s:
            return await leads_repo.get(s, lead_id)

    async def get_customer(self, customer_id: str) -> Customer | None:
        async with self.db.session() as s:
            return await catalogue_repo.get_customer(s, customer_id)


class MockCatalogue:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_product(self, code: str) -> Product | None:
        async with self.db.session() as s:
            return await catalogue_repo.get_product(s, code)

    async def list_products(self, line: str | None = None) -> Sequence[Product]:
        async with self.db.session() as s:
            return await catalogue_repo.list_products(s, line=line)
