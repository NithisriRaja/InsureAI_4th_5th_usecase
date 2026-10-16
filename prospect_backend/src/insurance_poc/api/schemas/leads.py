from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, TypeAdapter, field_validator

from insurance_poc.api.schemas.common import RecBrief, RunBrief
from insurance_poc.csv_data import DECLARED, PROTECTED

# Python type each declared fact must have so it can be saved to (and re-read from) the CSV.
# Money is minor units here, as in the database.
_DECLARED_TYPES: dict[str, TypeAdapter[Any]] = {
    kind: TypeAdapter(t)
    for kind, t in {
        "int": int,
        "money": int,
        "float": float,
        "bool": StrictBool,
        "str": str,
        "list": list[str],
    }.items()
}
# A cell starting with one of these runs as a formula when the CSV is opened in Excel.
_FORMULA_START = ("=", "+", "@", "\t", "\r")


def _no_formula(v: str | None) -> str | None:
    if v is not None and v.lstrip().startswith(_FORMULA_START):
        raise ValueError("must not start with =, +, @ (spreadsheet formula)")
    return v


class LeadIn(BaseModel):
    """Lenient on purpose: missing/invalid business data is the data-quality gate's job
    (it produces a request_info recommendation), not a 422. Values that cannot be stored in
    the CSV files (wrong type, unknown fact, spreadsheet formula) are rejected."""

    model_config = ConfigDict(extra="forbid")

    external_ref: str | None = Field(default=None, max_length=64)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    dob: date | None = None
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=100)
    product_line: str | None = Field(default=None, max_length=20)
    sum_insured: int | None = Field(
        default=None, ge=0, le=10**12, description="Major currency units."
    )
    declared: dict[str, Any] = Field(
        default_factory=dict,
        description="Declared facts by CSV column name; money in minor units (cents).",
    )
    notes: str | None = Field(default=None, max_length=2000)
    source: str = Field(default="web", max_length=30)
    channel_owner: str | None = Field(
        default=None,
        max_length=20,
        description="adviser|broker|direct|employer; default from source/line",
    )
    intermediary: str | None = Field(default=None, max_length=120)
    documents_provided: list[str] = Field(default_factory=list)
    consent_profiling: bool = True
    consent_marketing: bool = False
    consent_email: bool = False
    consent_sms: bool = False
    protected: dict[str, Any] = Field(
        default_factory=dict, description="Stored for record only; never used in decisions."
    )

    _text_fields = field_validator(
        "external_ref", "first_name", "last_name", "city", "notes", "source", "intermediary"
    )(_no_formula)

    @field_validator("declared")
    @classmethod
    def _check_declared(cls, v: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(v) - set(DECLARED))
        if unknown:
            raise ValueError(f"unknown facts {unknown}; allowed: {sorted(DECLARED)}")
        out: dict[str, Any] = {}
        for key, value in v.items():
            if value is None:
                continue
            try:
                out[key] = _DECLARED_TYPES[DECLARED[key]].validate_python(value)
            except ValueError as e:
                raise ValueError(f"{key}: expected {DECLARED[key]}") from e
            if DECLARED[key] == "str":
                _no_formula(out[key])
            elif DECLARED[key] == "list":
                for item in out[key]:
                    _no_formula(item)
        return out

    @field_validator("protected")
    @classmethod
    def _check_protected(cls, v: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(v) - set(PROTECTED))
        if unknown:
            raise ValueError(f"unknown keys {unknown}; allowed: {list(PROTECTED)}")
        return {k: _no_formula(str(x)) for k, x in v.items() if x is not None}

    def to_model_fields(self) -> dict[str, Any]:
        data = self.model_dump(exclude={"sum_insured"})
        data["sum_insured_requested"] = (
            self.sum_insured * 100 if self.sum_insured is not None else None
        )
        return data


class LeadBulkIn(BaseModel):
    leads: list[LeadIn] = Field(min_length=1, max_length=200)


class LeadIngestResult(BaseModel):
    lead_id: str
    created: bool
    run: RunBrief | None


class LeadBulkResult(BaseModel):
    batch_id: str
    results: list[LeadIngestResult]


class LeadOut(BaseModel):
    id: str
    external_ref: str | None
    name: str
    product_line: str | None
    sum_insured: int | None
    source: str
    channel_owner: str
    intermediary: str | None
    status: str
    existing_customer: bool
    consent_marketing: bool
    created_at: datetime
    latest_recommendation: RecBrief | None
    latest_run: RunBrief | None


class LeadDetail(LeadOut):
    """What a reviewer sees before running a lead. Protected attributes are never exposed."""

    first_name: str | None
    last_name: str | None
    dob: date | None
    email: str | None
    phone: str | None
    city: str | None
    # Line-specific facts as stored: money values are minor units (cents).
    declared: dict[str, Any]
    notes: str | None
    documents_provided: list[str]
    consent_profiling: bool
    consent_email: bool
    consent_sms: bool
