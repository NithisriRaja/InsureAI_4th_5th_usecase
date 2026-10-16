"""SQLAlchemy models. Enum-valued columns store the StrEnum value (see ``insurance_poc.enums``).

Money is stored as integer minor units (cents). Dates are calendar dates; timestamps are UTC.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from insurance_poc.db.base import Base
from insurance_poc.utils.clock import utcnow


def _json_dict() -> Mapped[dict[str, Any]]:
    return mapped_column(JSON, default=dict, nullable=False)


def _json_list() -> Mapped[list[Any]]:
    return mapped_column(JSON, default=list, nullable=False)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------- domain ---


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    external_ref: Mapped[str | None] = mapped_column(String(64), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    dob: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    city: Mapped[str | None] = mapped_column(String(100))
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_email: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_updated_at: Mapped[datetime | None] = mapped_column()
    # Protected attributes: stored for record only, never sent to LLM or used by rules.
    protected: Mapped[dict[str, Any]] = _json_dict()


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    external_ref: Mapped[str | None] = mapped_column(String(64), unique=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), unique=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    dob: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    city: Mapped[str | None] = mapped_column(String(100))
    product_line: Mapped[str | None] = mapped_column(String(20))
    sum_insured_requested: Mapped[int | None] = mapped_column(Integer)
    # Line-specific declared facts, e.g. vehicle_year, smoker, prior_claims_3y.
    declared: Mapped[dict[str, Any]] = _json_dict()
    notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), default="web")
    # Relationship owner: adviser | broker | direct | employer (None = resolved from source/line).
    channel_owner: Mapped[str | None] = mapped_column(String(20))
    intermediary: Mapped[str | None] = mapped_column(String(120))  # owning broker / adviser
    documents_provided: Mapped[list[Any]] = _json_list()
    # Purpose consent: may this record be used for profiling / scoring at all.
    consent_profiling: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_email: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    protected: Mapped[dict[str, Any]] = _json_dict()
    existing_customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)


class Product(Base):
    __tablename__ = "products"

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    line: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    min_age: Mapped[int] = mapped_column(Integer)
    max_age: Mapped[int] = mapped_column(Integer)
    min_sum_insured: Mapped[int] = mapped_column(Integer)
    max_sum_insured: Mapped[int] = mapped_column(Integer)
    base_premium: Mapped[int] = mapped_column(Integer)  # annual, minor units
    tier: Mapped[str] = mapped_column(String(20), default="standard")  # basic|standard|premium
    rules: Mapped[dict[str, Any]] = _json_dict()  # e.g. {"max_vehicle_age": 15}
    payment_frequency: Mapped[str] = mapped_column(String(10), default="annual")
    channels: Mapped[list[Any]] = _json_list()  # relationship owners allowed to sell it
    regulated: Mapped[bool] = mapped_column(Boolean, default=False)  # suggestions = advice
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# ------------------------------------------------------------- execution ---


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    params: Mapped[dict[str, Any]] = _json_dict()
    skipped: Mapped[list[Any]] = _json_list()  # [{subject_id, reason}] filtered before queueing
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        # At most one active run per subject (race guard for duplicate triggers / scans).
        Index(
            "uq_runs_active_subject",
            "subject_type",
            "subject_id",
            unique=True,
            sqlite_where=text("status IN ('queued','running')"),
        ),
        Index("ix_runs_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"), index=True)
    use_case: Mapped[str] = mapped_column(String(20))
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[str] = mapped_column(String(40))
    cycle_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    claimed_by: Mapped[str | None] = mapped_column(String(60))
    heartbeat_at: Mapped[datetime | None] = mapped_column()
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any]] = _json_dict()
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()


# ------------------------------------------------------------------ HITL ---


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        # At most one open recommendation per subject + cycle.
        Index(
            "uq_recs_open_subject_cycle",
            "subject_type",
            "subject_id",
            "cycle_key",
            unique=True,
            sqlite_where=text("status = 'pending_approval'"),
        ),
        Index("ix_recs_status_queue", "status", "queue"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    use_case: Mapped[str] = mapped_column(String(20))
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[str] = mapped_column(String(40))
    cycle_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="pending_approval")
    version: Mapped[int] = mapped_column(Integer, default=1)
    queue: Mapped[str] = mapped_column(String(20))
    priority: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(40))
    channel_owner: Mapped[str | None] = mapped_column(String(20))
    # Application prep: completeness, missing documents, evidence, needs review.
    checklist: Mapped[dict[str, Any]] = _json_dict()
    rulebook_version: Mapped[str | None] = mapped_column(String(30))
    band: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[str | None] = mapped_column(String(10))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reasons: Mapped[list[Any]] = _json_list()
    signals: Mapped[dict[str, Any]] = _json_dict()
    decisions: Mapped[dict[str, Any]] = _json_dict()  # LLM decisions by node
    rule_results: Mapped[list[Any]] = _json_list()
    missing_info: Mapped[list[Any]] = _json_list()
    products: Mapped[list[Any]] = _json_list()  # ranked eligible products
    channel: Mapped[str | None] = mapped_column(String(20))
    explanation: Mapped[str | None] = mapped_column(Text)
    fairness: Mapped[dict[str, Any]] = _json_dict()
    expires_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column()
    decided_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), unique=True)
    decision: Mapped[str] = mapped_column(String(30))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(100))
    actor_role: Mapped[str] = mapped_column(String(20))
    session_id: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str | None] = mapped_column(Text)
    edits: Mapped[dict[str, Any]] = _json_dict()
    original_snapshot: Mapped[dict[str, Any]] = _json_dict()
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


# ---------------------------------------------------------------- audit ---


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(40), index=True)
    node: Mapped[str | None] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    attempt: Mapped[int] = mapped_column(Integer)
    request: Mapped[dict[str, Any]] = _json_dict()
    response_raw: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))  # ok | error | invalid
    error: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditEvent(Base):
    """Append-only. Never updated or deleted by application code."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    run_id: Mapped[str | None] = mapped_column(String(40), index=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(40), index=True)
    subject_type: Mapped[str | None] = mapped_column(String(20))
    subject_id: Mapped[str | None] = mapped_column(String(40), index=True)
    node: Mapped[str | None] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(100), default="system")
    payload: Mapped[dict[str, Any]] = _json_dict()


# ------------------------------------------------------------- identity ---


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(100), unique=True)  # casefolded name
    role: Mapped[str] = mapped_column(String(20))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()


IDENTITY_TABLES = ("users", "sessions")
