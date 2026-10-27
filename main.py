"""FastAPI app for new customers (use case 4). From this folder: ``python -m uvicorn main:app --reload``.

    /prospect/...   new customers   prospect_backend/  (package insurance_poc)

API docs: /prospect/docs.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "prospect_backend" / "src"))  # works without `pip install -e`

from insurance_poc.main import app as prospect_app  # noqa: E402

APPS = {"/prospect": prospect_app}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # A mounted app's own start-up / shut-down (CSV load, agent runner) is not run by
    # Starlette, so run each one here.
    async with AsyncExitStack() as stack:
        for sub in APPS.values():
            await stack.enter_async_context(sub.router.lifespan_context(sub))
        yield


app = FastAPI(title="InsureAI agents", version="0.1.0", lifespan=lifespan)
for prefix, sub in APPS.items():
    app.mount(prefix, sub)


@app.get("/health", tags=["health"])
async def health() -> dict[str, object]:
    return {"status": "ok", "apps": list(APPS)}
