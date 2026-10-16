"""Products and existing customers (read-only for the agent)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.db.models import Customer, Product


async def get_customer(s: AsyncSession, customer_id: str) -> Customer | None:
    return await s.get(Customer, customer_id)


async def get_product(s: AsyncSession, code: str) -> Product | None:
    return await s.get(Product, code)


async def list_products(s: AsyncSession, *, line: str | None = None) -> Sequence[Product]:
    q = select(Product).where(Product.active.is_(True))
    if line:
        q = q.where(Product.line == line)
    return (await s.execute(q.order_by(Product.code))).scalars().all()
