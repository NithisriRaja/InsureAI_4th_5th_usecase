from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request

from renewal_backend.db.session import Database
from renewal_backend.db.store import DbSession
from renewal_backend.services.runner import Runner


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_runner(request: Request) -> Runner | None:
    return getattr(request.app.state, "runner", None)


async def db_session(request: Request) -> AsyncIterator[DbSession]:
    """One short unit of work per request (commit on success)."""
    async with get_database(request).session() as s:
        yield s
