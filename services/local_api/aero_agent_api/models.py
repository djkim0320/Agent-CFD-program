from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ConnectionMode(StrEnum):
    codex_oauth = "codex_oauth"
    openai_api = "openai_api"


class JobStatus(StrEnum):
    uploaded = "uploaded"
    preflighting = "preflighting"
    waiting_approval = "waiting_approval"
    running = "running"
    retrying = "retrying"
    postprocessing = "postprocessing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class AnalysisRequest(BaseModel):
    unit: str
    geometry_kind: Literal["general_3d", "aircraft_vsp"]
    solver_preference: Literal["auto", "vspaero", "su2", "openfoam"] = "auto"
    fidelity: Literal["fast", "balanced", "high"] = "balanced"
    flow: dict[str, Any] = Field(default_factory=dict)
    frame: dict[str, Any] | None = None
    reference_values: dict[str, Any] | None = None
    notes: str | None = None


class ConnectionCreate(BaseModel):
    mode: ConnectionMode
    label: str | None = None
    data_policy: str = "summary_first"
    credentials_hint: dict[str, Any] | None = None


class ConnectionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    mode: ConnectionMode
    label: str
    status: Literal["unknown", "ready", "missing", "error"] = "unknown"
    data_policy: str = "summary_first"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_validated_at: datetime | None = None


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    connection_id: str
    status: JobStatus
    selected_solver: Literal["auto", "vspaero", "su2", "openfoam"] = "auto"
    rationale: str | None = None
    progress: int = 0
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    request: AnalysisRequest
    source_file_name: str
    source_file_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None
    cancelled_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None


class JobEvent(BaseModel):
    id: int | None = None
    job_id: str
    seq: int = 0
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PreflightPlan(BaseModel):
    job_id: str
    selected_solver: str
    rationale: str
    runtime_estimate_minutes: int
    memory_estimate_gb: float
    warnings: list[str] = Field(default_factory=list)
    repair_summary: list[str] = Field(default_factory=list)
    approve_required: bool = True


class ArtifactPayload(BaseModel):
    job_id: str
    kind: str
    path: str
    size_bytes: int


def utcnow() -> datetime:
    return datetime.now(UTC)


def make_job_folder(base_dir: Path, job_id: str) -> Path:
    return base_dir / "jobs" / job_id
