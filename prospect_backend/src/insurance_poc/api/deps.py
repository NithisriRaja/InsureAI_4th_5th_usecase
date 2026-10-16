from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from insurance_poc.db.session import Database
from insurance_poc.services.runner import Runner


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_runner(request: Request) -> Runner | None:
    return getattr(request.app.state, "runner", None)


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One short unit of work per request (commit on success)."""
    async with get_database(request).session() as s:
        yield s
