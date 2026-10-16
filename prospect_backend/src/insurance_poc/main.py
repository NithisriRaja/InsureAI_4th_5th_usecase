"""FastAPI entry point: ``uv run uvicorn insurance_poc.main:app --reload``."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from insurance_poc.api import errors
from insurance_poc.api.routes import (
    approvals,
    health,
    leads,
    recommendations,
    runs,
    sessions,
)
from insurance_poc.config import get_settings
from insurance_poc.csv_data import CsvError
from insurance_poc.db.csv_store import CsvStore
from insurance_poc.db.session import Database, set_db
from insurance_poc.services.llm.client import LLMClient
from insurance_poc.services.runner import Runner
from insurance_poc.utils.logging import configure_logging, get_logger

log = get_logger(__name__)


def create_app(
    *,
    db: Database | None = None,
    llm_factory: Callable[[], LLMClient] | None = None,
    start_runner: bool = True,
) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        store: CsvStore | None = None
        if db is None:  # the app's own storage: the CSV files (tests pass a database)
            store = CsvStore(settings.data_dir, settings.csv_flush_interval_s)
            try:
                await store.open()
            except CsvError as e:
                for problem in e.problems:
                    log.error("csv.invalid", problem=problem)
                await store.close()
                raise SystemExit(f"Fix the CSV files in {settings.data_dir} and restart.") from e
            database = store.db
        else:
            database = db
        set_db(database)
        await database.create_all()
        app.state.db = database
        app.state.csv_store = store
        app.state.runner = None
        if start_runner:
            runner = Runner(database, settings=settings, llm_factory=llm_factory)
            await runner.start()
            app.state.runner = runner
        log.info(
            "app.started",
            provider=settings.llm_provider,
            storage=str(settings.data_dir) if store else database.url,
        )
        try:
            yield
        finally:
            if app.state.runner:
                await app.state.runner.stop()
            if store is not None:
                await store.close()  # final write-back, then drop the working copy

    app = FastAPI(
        title="Insurance AI Agents POC",
        version="0.1.0",
        description="New-customer agent: hard rules, bounded LLM decisions, product matching "
        "and human approval. Data: CSV files.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    errors.install(app)
    for r in (
        health.router,
        sessions.router,
        leads.router,
        runs.router,
        recommendations.router,
        approvals.router,
    ):
        app.include_router(r)
    return app


app = create_app()
