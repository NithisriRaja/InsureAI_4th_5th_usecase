"""Async engine + session factory.

SQLite concurrency strategy:
- WAL journal so readers never block the single writer.
- busy_timeout so a writer waits instead of failing with "database is locked".
- Every transaction starts with BEGIN IMMEDIATE: the write lock is taken up front, which
  avoids the deferred read->write upgrade deadlock (SQLITE_BUSY without waiting).
- Callers keep transactions short and never await network I/O inside one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from insurance_poc.db.base import Base


def _ensure_sqlite_dir(url: str) -> None:
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


def create_engine(url: str) -> AsyncEngine:
    _ensure_sqlite_dir(url)
    engine = create_async_engine(url, connect_args={"timeout": 30})

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _on_connect(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            dbapi_conn.isolation_level = None  # we emit BEGIN ourselves
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            # Busy waiting is not fair: under a burst of short writers (workers, LLM audit,
            # heartbeats, API) one waiter can lose for seconds. Match the 30s connect timeout.
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        @event.listens_for(engine.sync_engine, "begin")
        def _on_begin(conn):  # type: ignore[no-untyped-def]
            conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = create_engine(url)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """One unit of work: commits on success, rolls back on error."""
        async with self.sessionmaker() as s:
            try:
                yield s
                await s.commit()
            except BaseException:
                await s.rollback()
                raise

    async def create_all(self) -> None:
        from insurance_poc.db import models  # noqa: F401  (register tables)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()


_db: Database | None = None


def get_db() -> Database:
    """The open working copy (set at app start-up by the CSV store, or by tests)."""
    if _db is None:
        raise RuntimeError("No database is open: start the app (CSV store) or set_db() first.")
    return _db


def set_db(db: Database | None) -> None:
    """Swap the process-wide database (tests)."""
    global _db
    _db = db
