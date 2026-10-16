from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LLMProvider = Literal["domo", "anthropic", "fake"]
StructuredMode = Literal["json_schema", "json_object", "prompt"]
# prospect_backend/ holds data_csv/ (relative paths resolve here, whatever the cwd); .env sits one
# level up, in the project root next to .venv and requirements.txt.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Storage: the CSV files in ``data_dir`` are the only data on disk. The app works on a
    # throwaway copy in the OS temp folder and writes every change back (db/csv_store.py).
    data_dir: Path = Path("data_csv")
    csv_flush_interval_s: float = 1.0
    as_of_date: date | None = None

    # LLM
    llm_provider: LLMProvider = "domo"
    llm_structured_mode: StructuredMode = "prompt"
    llm_temperature: float = 0.0
    llm_timeout_s: float = 60.0
    llm_max_attempts: int = 5
    llm_max_total_wait_s: float = 120.0
    llm_rpm: int = 15
    llm_max_concurrency: int = 2
    llm_max_tokens: int = 16000  # Anthropic: thinking counts against this budget
    llm_retry_base_s: float = 1.0
    llm_retry_cap_s: float = 30.0

    # Domo AI Services (POST {base}/ai/v1/text/generation, X-DOMO-Developer-Token auth)
    domo_api_key: str = ""
    domo_base_url: str = ""
    domo_model: str = "domo.openai.gpt-5.5"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    # low | medium | high | xhigh | max ; empty = model default. Classification does well at low.
    anthropic_effort: str = "low"
    # Server-side refusal fallback (Claude API only, supported models only).
    anthropic_fallbacks: bool = True

    # Runner
    runner_workers: int = 2
    runner_poll_interval_s: float = 0.5
    run_heartbeat_s: float = 5.0
    run_stale_after_s: float = 60.0
    run_max_attempts: int = 3

    # Business
    currency: str = "AED"

    # Sessions / API
    session_idle_hours: float = 12.0
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3001"]
    )

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("data_dir")
    @classmethod
    def _anchor_data_dir(cls, v: Path) -> Path:
        # Relative to the repo, not the shell's folder (a server started from another folder
        # must not create a second, empty data folder there).
        return v if v.is_absolute() else BACKEND_ROOT / v

    @field_validator("as_of_date", mode="before")
    @classmethod
    def _empty_date(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and v.strip().lower() in ("", "today", "none")):
            return None
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
