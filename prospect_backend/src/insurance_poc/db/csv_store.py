"""CSV storage: the files in ``data_dir`` are the only data the app keeps on disk.

Layout of ``data_dir``:
    leads.csv, products.csv, customers.csv   people-friendly inputs (see ``csv_data``)
    system/<table>.csv                        everything the app records (runs, AI decisions,
                                              approvals, audit, LLM calls, users, sessions...)
    results/ai_results.csv                    one row per lead with its latest AI verdict

At start-up the CSVs are loaded into a throwaway SQLite working copy in the OS temp folder
(it keeps the run queue's atomic claims and the approvals' version checks safe under
concurrency). Every write marks the store dirty; a background task writes the CSVs back
within ``csv_flush_interval_s``, and once more on shutdown. Each file is written to a temp
file and swapped in, so a crash never leaves a half-written CSV; unchanged files are not
rewritten. The working copy is deleted on shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import csv
import io
import json
import os
import shutil
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, Date, Float, Integer, Table, event, insert, select

from insurance_poc import csv_data
from insurance_poc.db.base import Base, UTCDateTime
from insurance_poc.db.session import Database
from insurance_poc.utils.logging import get_logger

log = get_logger(__name__)

INPUT_TABLES = ("products", "customers", "leads")  # written in the friendly format
SYSTEM_DIR = "system"
RESULTS_FILE = Path("results") / "ai_results.csv"
_WRITES = ("INSERT", "UPDATE", "DELETE", "REPLACE")
_dumping: contextvars.ContextVar[bool] = contextvars.ContextVar("csv_dumping", default=False)


# ----------------------------------------------------------- raw tables ---


def _tables() -> list[Table]:
    from insurance_poc.db import models  # noqa: F401  (register tables)

    return [t for t in Base.metadata.sorted_tables if t.name not in INPUT_TABLES]


def _encode(col: Any, value: Any) -> str:
    if value is None:
        return ""
    t = col.type
    if isinstance(t, JSON):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(t, Boolean):
        return "true" if value else "false"
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _decode(col: Any, text: str) -> Any:
    t = col.type
    if text == "":
        if col.nullable:
            return None
        if isinstance(t, JSON) and col.default is not None:
            return col.default.arg(None)  # dict() / list(), wrapped by SQLAlchemy
        return ""
    if isinstance(t, JSON):
        return json.loads(text)
    if isinstance(t, Boolean):
        return text.lower() == "true"
    if isinstance(t, Integer):
        return int(text)
    if isinstance(t, Float):
        return float(text)
    if isinstance(t, UTCDateTime):
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    if isinstance(t, Date):
        return date.fromisoformat(text)
    return text


def _csv_text(columns: list[str], rows: list[dict[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _write_if_changed(path: Path, text: str) -> bool:
    """Atomic replace; skipped when the content is unchanged. Raises PermissionError when the
    file is locked (e.g. open in Excel) so the caller can retry."""
    data = text.encode(csv_data.ENCODING)
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


# ------------------------------------------------------------- load/dump ---


async def load_all(db: Database, folder: Path) -> dict[str, int]:
    """Fill an empty database from ``folder``. Raises ``csv_data.CsvError`` on bad input."""
    await db.create_all()
    async with db.session() as s:
        counts = await csv_data.load(s, folder)
    for table in _tables():
        path = folder / SYSTEM_DIR / f"{table.name}.csv"
        if not path.exists():
            continue
        with path.open(encoding=csv_data.ENCODING, newline="") as f:
            rows = list(csv.DictReader(f))
        cols = {c.name: c for c in table.columns}
        values = [
            {k: _decode(cols[k], v or "") for k, v in row.items() if k in cols} for row in rows
        ]
        if values:
            async with db.session() as s:
                await s.execute(insert(table), values)
        counts[table.name] = len(values)
    return counts


async def dump_all(db: Database, folder: Path) -> list[str]:
    """Write every table back to ``folder``; returns the files that changed."""
    from insurance_poc.db.models import Customer, Lead, Product

    token = _dumping.set(True)
    try:
        files: dict[Path, str] = {}
        async with db.session() as s:
            products = (await s.execute(select(Product).order_by(Product.code))).scalars().all()
            customers = (await s.execute(select(Customer).order_by(Customer.id))).scalars().all()
            leads = (
                (await s.execute(select(Lead).order_by(Lead.created_at, Lead.id))).scalars().all()
            )
            files[folder / "products.csv"] = _csv_text(
                csv_data.PRODUCT_COLUMNS, [csv_data.product_row(p) for p in products]
            )
            files[folder / "customers.csv"] = _csv_text(
                csv_data.CUSTOMER_COLUMNS, [csv_data.customer_row(c) for c in customers]
            )
            files[folder / "leads.csv"] = _csv_text(
                csv_data.lead_columns(leads), [csv_data.lead_row(lead) for lead in leads]
            )
            for table in _tables():
                cols = list(table.columns)
                pk = list(table.primary_key.columns)
                result = await s.execute(select(table).order_by(*pk))
                rows = [
                    {c.name: _encode(c, r._mapping[c]) for c in cols} for r in result.fetchall()
                ]
                files[folder / SYSTEM_DIR / f"{table.name}.csv"] = _csv_text(
                    [c.name for c in cols], rows
                )
            files[folder / RESULTS_FILE] = await _results_text(s, leads)
        # File I/O off the event loop so API requests and workers keep running.
        return await asyncio.to_thread(
            lambda: [str(p) for p, text in files.items() if _write_if_changed(p, text)]
        )
    finally:
        _dumping.reset(token)


async def _results_text(s: Any, leads: Any) -> str:
    from insurance_poc.db.models import Recommendation

    recs = (
        (
            await s.execute(
                select(Recommendation)
                .where(Recommendation.subject_type == "lead")
                .order_by(Recommendation.created_at)
            )
        )
        .scalars()
        .all()
    )
    latest = {r.subject_id: r for r in recs}
    rows = [csv_data.result_row(lead, latest.get(lead.id)) for lead in leads]
    return _csv_text(csv_data.RESULT_COLUMNS, rows)


# ------------------------------------------------------------------ sync ---


class CsvStore:
    """Working copy + background write-back for one app instance."""

    def __init__(self, folder: Path, interval_s: float = 1.0) -> None:
        self.folder = folder
        self.interval_s = interval_s
        self._tmp = Path(tempfile.mkdtemp(prefix="insurance-poc-"))
        self.db = Database(f"sqlite+aiosqlite:///{(self._tmp / 'working-copy.db').as_posix()}")
        self._dirty = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._warned_locked: set[str] = set()

    def _on_execute(self, _conn: Any, cur: Any, statement: str, *_a: Any) -> None:
        if _dumping.get() or not statement.lstrip()[:7].upper().startswith(_WRITES):
            return
        if getattr(cur, "rowcount", -1) == 0:  # matched nothing (-1 = unknown: save)
            return
        self._dirty.set()

    async def open(self) -> dict[str, int]:
        counts = await load_all(self.db, self.folder)
        event.listen(self.db.engine.sync_engine, "after_cursor_execute", self._on_execute)
        self._task = asyncio.create_task(self._loop(), name="csv-writeback")
        log.info("csv.loaded", folder=str(self.folder), **counts)
        return counts

    async def flush(self) -> None:
        try:
            changed = await dump_all(self.db, self.folder)
            self._warned_locked.clear()
            if changed:
                log.info("csv.saved", files=len(changed))
        except PermissionError as e:
            self._dirty.set()  # retry on the next tick
            name = Path(getattr(e, "filename", "") or "").name
            if name not in self._warned_locked:
                self._warned_locked.add(name)
                log.warning("csv.locked", file=name, hint="close it in Excel; saving retries")

    async def _loop(self) -> None:
        while True:
            await self._dirty.wait()
            await asyncio.sleep(self.interval_s)  # batch bursts of writes
            self._dirty.clear()
            try:
                await self.flush()
            except Exception:  # noqa: BLE001 - one bad save must not stop all later saves
                log.exception("csv.save_failed")
                self._dirty.set()
                await asyncio.sleep(max(self.interval_s, 5.0))  # don't spin on a hard error

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        try:
            await self.flush()
        except Exception:  # noqa: BLE001
            log.exception("csv.final_save_failed", folder=str(self.folder))
            raise
        finally:
            await self.db.dispose()
            shutil.rmtree(self._tmp, ignore_errors=True)
            log.info("csv.closed", folder=str(self.folder))


def reset_state(folder: Path, *, keep_users: bool = False) -> list[str]:
    """Forget everything the app recorded (runs, AI decisions, approvals, audit, results) and
    set every lead back to "new". The input data (leads, products, customers) is kept."""
    from insurance_poc.db.models import IDENTITY_TABLES

    removed: list[str] = []
    system = folder / SYSTEM_DIR
    for path in sorted(system.glob("*.csv")) if system.exists() else []:
        if keep_users and path.stem in IDENTITY_TABLES:
            continue
        path.unlink()
        removed.append(str(path))
    results = folder / RESULTS_FILE
    if results.exists():
        results.unlink()
        removed.append(str(results))
    leads = folder / "leads.csv"
    if leads.exists():
        with leads.open(encoding=csv_data.ENCODING, newline="") as f:
            reader = csv.DictReader(f)
            columns, rows = list(reader.fieldnames or []), list(reader)
        if "status" in columns:
            for row in rows:
                row["status"] = "new"
            _write_if_changed(leads, _csv_text(columns, rows))
    return removed
