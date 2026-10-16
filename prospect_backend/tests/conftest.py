from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import pytest

from insurance_poc.config import get_settings
from insurance_poc.db.session import Database, set_db

AS_OF = date(2026, 10, 13)
DEMO_CSV = Path(__file__).parent / "fixtures" / "demo_csv"


@pytest.fixture(autouse=True)
def _settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic settings for every test; never read the developer's .env."""
    monkeypatch.setenv("AS_OF_DATE", AS_OF.isoformat())
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    for key in ("DOMO_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "insurance_poc.config.Settings.model_config",
        {**get_settings().model_config, "env_file": None},
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def db(tmp_path) -> AsyncIterator[Database]:
    """Fresh file-backed SQLite per test (WAL + real locking semantics, unlike :memory:)."""
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await database.create_all()
    set_db(database)
    yield database
    set_db(None)
    await database.dispose()


@pytest.fixture
async def seeded_db(db: Database) -> Database:
    """The fixed demo data (tests/fixtures/demo_csv), loaded through the real CSV loader."""
    from insurance_poc import csv_data

    async with db.session() as s:
        await csv_data.load(s, DEMO_CSV)
    return db
