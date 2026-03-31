from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class ConnectionMode(StrEnum):
    CODEX_OAUTH = "codex_oauth"
    OPENAI_API = "openai_api"


class SolverKind(StrEnum):
    AUTO = "auto"
    VSPAERO = "vspaero"
    SU2 = "su2"
    OPENFOAM = "openfoam"


class GeometryKind(StrEnum):
    GENERAL_3D = "general_3d"
    AIRCRAFT_VSP = "aircraft_vsp"


class JobStatus(StrEnum):
    UPLOADED = "uploaded"
    PREFLIGHTING = "preflighting"
    WAITING_APPROVAL = "waiting_approval"
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SnapshotStatus(StrEnum):
    UPLOADED = "uploaded"
    PREFLIGHTING = "preflighting"
    READY = "ready"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class ExecutionMode(StrEnum):
    REAL = "real"
    SCAFFOLD = "scaffold"


class AIAssistMode(StrEnum):
    REMOTE = "remote"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    FAILED = "failed"


class EventType(StrEnum):
    JOB_STATUS = "job.status"
    PREFLIGHT_STARTED = "preflight.started"
    PREFLIGHT_COMPLETED = "preflight.completed"
    APPROVAL_REQUIRED = "approval.required"
    SUBAGENT_STARTED = "subagent.started"
    SUBAGENT_COMPLETED = "subagent.completed"
    TOOL_STARTED = "tool.started"
    TOOL_PROGRESS = "tool.progress"
    TOOL_COMPLETED = "tool.completed"
    SOLVER_STDOUT = "solver.stdout"
    SOLVER_METRICS = "solver.metrics"
    ARTIFACT_READY = "artifact.ready"
    REPORT_READY = "report.ready"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"


class ProviderBackend(StrEnum):
    OPENAI = "openai"
    CODEX_SDK = "codex_sdk"
    CODEX_APP_SERVER = "codex_app_server"
    CODEX_NONINTERACTIVE = "codex_noninteractive"
    CODEX_MCP = "codex_mcp"
    MOCK = "mock"


class ToolName(StrEnum):
    GEOMETRY_INSPECT = "geometry.inspect"
    GEOMETRY_REPAIR_CHECK = "geometry.repair_check"
    GEOMETRY_PREVIEW_BUILD = "geometry.preview_build"
    SOLVER_SELECT = "solver.select"
    CASE_PREPARE = "case.prepare"
    MESH_GENERATE = "mesh.generate"
    SOLVER_RUN = "solver.run"
    SOLVER_STATUS = "solver.status"
    RESULTS_EXTRACT = "results.extract"
    REPORT_BUILD = "report.build"
    ARTIFACT_PACKAGE = "artifact.package"
    INSTALL_CHECK = "install.check"
    INSTALL_REPAIR = "install.repair"
    AUTH_STATUS = "auth.status"


class ArtifactKind(StrEnum):
    REPORT_HTML = "report_html"
    VIEWER_BUNDLE = "viewer_bundle"
    CASE_ARCHIVE = "case_archive"
    LOGS = "logs"
    SUMMARY = "summary"
    PREVIEW = "preview"
    SOLVER_LOG = "solver_log"
    MESH_LOG = "mesh_log"
    RESIDUAL_HISTORY = "residual_history"
    COEFFICIENTS = "coefficients"
    CASE_BUNDLE = "case_bundle"
    MESH_MANIFEST = "mesh_manifest"
    NORMALIZATION_MANIFEST = "normalization_manifest"
    SOLVER_RUN_MANIFEST = "solver_run_manifest"


class FlowCondition(BaseModel):
    velocity: float | None = None
    mach: float | None = None
    aoa: float = 0.0
    sideslip: float = 0.0
    altitude: float | None = None
    density: float | None = None
    viscosity: float | None = None


class FrameSpec(BaseModel):
    forward_axis: Literal["x", "y", "z"] = "x"
    up_axis: Literal["x", "y", "z"] = "z"
    symmetry_plane: Literal["xy", "yz", "xz"] | None = None
    moment_center: tuple[float, float, float] | None = None


class ReferenceValues(BaseModel):
    area: float
    length: float | None = None
    span: float | None = None


class AnalysisRequest(BaseModel):
    geometry_file: str
    unit: Literal["m", "mm", "cm", "in", "ft"]
    frame: FrameSpec | None = None
    reference_values: ReferenceValues | None = None
    flow: FlowCondition
    fidelity: Literal["fast", "balanced", "high"] = "balanced"
    solver_preference: SolverKind = SolverKind.AUTO
    notes: str | None = None
    geometry_kind_hint: GeometryKind | None = None


class GeometryStats(BaseModel):
    file_size_bytes: int
    bbox: tuple[float, float, float, float, float, float] | None = None
    face_count: int | None = None
    edge_count: int | None = None
    component_count: int | None = None
    watertight: bool | None = None
    estimated_scale: float | None = None


class GeometryManifest(BaseModel):
    geometry_file: str
    geometry_kind: GeometryKind
    unit: str
    format: str | None = None
    stats: GeometryStats
    source_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    preview_path: str | None = None
    repaired_path: str | None = None


class RepairCheckResult(BaseModel):
    repairable: bool
    repair_actions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    preview_mesh_path: str | None = None


class SolverCandidate(BaseModel):
    solver: SolverKind
    score: float
    rationale: str
    runtime_estimate_minutes: int
    memory_estimate_gb: float


class SolverSelection(BaseModel):
    selected_solver: SolverKind
    rationale: str
    candidates: list[SolverCandidate] = Field(default_factory=list)
    user_override: SolverKind | None = None
    runtime_estimate_minutes: int
    memory_estimate_gb: float
    fit_score: float = 0.0


class GeometryTriageFinding(BaseModel):
    geometry_kind: GeometryKind = GeometryKind.GENERAL_3D
    risks: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    repairability: Literal["repairable", "blocked"] = "repairable"
    notes: list[str] = Field(default_factory=list)


class SolverPlannerFinding(BaseModel):
    recommended_solver: SolverKind = SolverKind.AUTO
    rationale: str = ""
    execution_mode: ExecutionMode = ExecutionMode.SCAFFOLD
    warnings: list[str] = Field(default_factory=list)
    deferred_scope: list[str] = Field(default_factory=list)


class AuthPolicyFinding(BaseModel):
    allowed: bool = True
    ai_warnings: list[str] = Field(default_factory=list)
    policy_warnings: list[str] = Field(default_factory=list)
    export_scope: str = "summary_only"
    notes: list[str] = Field(default_factory=list)


class SubagentFindings(BaseModel):
    geometry_triage: GeometryTriageFinding
    solver_planner: SolverPlannerFinding
    auth_and_policy_reviewer: AuthPolicyFinding


class IssueRecord(BaseModel):
    code: str
    message: str
    guidance: str | None = None


class NormalizationSummary(BaseModel):
    source_format: str | None = None
    declared_unit: str
    canonical_unit: str = "m"
    scale_factor_to_meter: float
    axis_mapping: dict[str, str | None] = Field(default_factory=dict)
    source_bbox: tuple[float, float, float, float, float, float] | None = None
    normalized_bbox: tuple[float, float, float, float, float, float] | None = None
    face_count: int | None = None
    component_count: int | None = None
    watertight: bool | None = None
    repair_actions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class PreflightPlan(BaseModel):
    request: AnalysisRequest
    geometry_manifest: GeometryManifest
    repair: RepairCheckResult
    solver_selection: SolverSelection
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    approval_required: bool = True
    estimated_runtime_minutes: int = 0
    estimated_memory_gb: float = 0.0


class InstallStatus(BaseModel):
    docker_ok: bool
    gmsh_ok: bool
    su2_image_ok: bool
    workspace_ok: bool
    install_warnings: list[str] = Field(default_factory=list)
    runtime_blockers: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ProviderCapabilities(BaseModel):
    backend: ProviderBackend
    supports_streaming: bool = False
    supports_subagents: bool = False
    supports_noninteractive: bool = False
    supports_mcp: bool = False
    notes: list[str] = Field(default_factory=list)


class ProviderStatus(BaseModel):
    connected: bool
    mode: ConnectionMode
    backend: ProviderBackend
    provider_ready: bool = False
    warnings: list[str] = Field(default_factory=list)
    data_policy: str = "summary-first"
    details: dict[str, Any] = Field(default_factory=dict)


class ConnectionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    mode: ConnectionMode
    label: str
    status: Literal["unknown", "ready", "missing", "error"] = "unknown"
    data_policy: str = "summary_first"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    last_validated_at: datetime | None = None


class ConnectionStatusResponse(BaseModel):
    connection_id: str
    connected: bool
    provider_ready: bool
    mode: ConnectionMode
    backend: ProviderBackend
    warnings: list[str] = Field(default_factory=list)


class ConnectionProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    mode: ConnectionMode
    label: str
    backend: ProviderBackend = ProviderBackend.MOCK
    status: ProviderStatus | None = None
    created_at: datetime = Field(default_factory=utc_now)
    last_validated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactRecord(BaseModel):
    kind: ArtifactKind
    path: str
    sha256: str | None = None
    size_bytes: int | None = None
    created_at: datetime = Field(default_factory=utc_now)


class MetricRecord(BaseModel):
    name: str
    value: float
    unit: str | None = None
    description: str | None = None


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    connection_id: str
    preflight_snapshot_id: str
    status: JobStatus
    selected_solver: SolverKind = SolverKind.AUTO
    execution_mode: ExecutionMode = ExecutionMode.SCAFFOLD
    ai_assist_mode: AIAssistMode = AIAssistMode.DISABLED
    rationale: str | None = None
    progress: int = 0
    warnings: list[str] = Field(default_factory=list)
    runtime_blockers: list[str] = Field(default_factory=list)
    install_warnings: list[str] = Field(default_factory=list)
    ai_warnings: list[str] = Field(default_factory=list)
    policy_warnings: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    metrics: list[MetricRecord] = Field(default_factory=list)
    error: str | None = None
    request: AnalysisRequest
    source_file_name: str
    source_file_path: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None


class JobSummaryResponse(BaseModel):
    id: str
    status: JobStatus
    selected_solver: SolverKind
    execution_mode: ExecutionMode
    ai_assist_mode: AIAssistMode
    ai_review_status: AIAssistMode | None = None
    ai_review_reason: str | None = None
    source_file_name: str
    created_at: datetime
    updated_at: datetime
    rationale: str | None = None
    progress: int = 0
    warnings: list[str] = Field(default_factory=list)
    runtime_blockers: list[str] = Field(default_factory=list)
    runtime_blocker_details: list[IssueRecord] = Field(default_factory=list)
    install_warnings: list[str] = Field(default_factory=list)
    ai_warnings: list[str] = Field(default_factory=list)
    policy_warnings: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    metrics: dict[str, float | str] = Field(default_factory=dict)
    residual_history: list[dict[str, float]] = Field(default_factory=list)
    error: str | None = None
    preflight_snapshot_id: str


class JobEventRecord(BaseModel):
    id: int | None = None
    job_id: str
    seq: int = 0
    event_type: EventType | str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class PreflightSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    connection_id: str
    status: SnapshotStatus = SnapshotStatus.READY
    source_file_name: str
    source_file_relpath: str
    normalized_manifest_relpath: str
    normalization_manifest_relpath: str | None = None
    normalized_geometry_relpath: str | None = None
    preflight_plan_relpath: str
    subagent_findings_relpath: str
    request: AnalysisRequest
    request_digest: str
    source_hash: str
    normalized_manifest_hash: str
    normalized_geometry_hash: str | None = None
    selected_solver: SolverKind
    execution_mode: ExecutionMode
    ai_assist_mode: AIAssistMode
    runtime_blockers: list[str] = Field(default_factory=list)
    install_warnings: list[str] = Field(default_factory=list)
    ai_warnings: list[str] = Field(default_factory=list)
    policy_warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime
    consumed_by_job_id: str | None = None
    consumed_at: datetime | None = None


class PreflightResponse(BaseModel):
    preflight_id: str
    selected_solver: SolverKind
    execution_mode: ExecutionMode
    ai_assist_mode: AIAssistMode
    ai_review_status: AIAssistMode | None = None
    ai_review_reason: str | None = None
    runtime_blockers: list[str] = Field(default_factory=list)
    runtime_blocker_details: list[IssueRecord] = Field(default_factory=list)
    install_warnings: list[str] = Field(default_factory=list)
    ai_warnings: list[str] = Field(default_factory=list)
    policy_warnings: list[str] = Field(default_factory=list)
    subagent_findings: SubagentFindings | None = None
    request_digest: str
    source_hash: str
    normalized_manifest_hash: str
    normalized_geometry_hash: str | None = None
    normalization_summary: NormalizationSummary | None = None
    physics_grade: Literal["stable_trend_grade"] = "stable_trend_grade"
    mesh_strategy: Literal["box_farfield"] = "box_farfield"
    runtime_estimate_minutes: int
    memory_estimate_gb: float
    confidence: float = 0.0
    rationale: str
    candidate_solvers: list[SolverKind] = Field(default_factory=list)


class ResultField(BaseModel):
    name: str
    path: str
    kind: Literal["scalar", "vector", "surface", "line"] = "scalar"


class SolverRunManifest(BaseModel):
    solver: SolverKind
    case_dir: str
    runtime_backend: Literal["docker", "native", "mock"] = "mock"
    run_id: str | None = None
    pid_or_container_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: JobStatus = JobStatus.UPLOADED
    logs_path: str | None = None
    metrics: list[MetricRecord] = Field(default_factory=list)
    fields: list[ResultField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReportManifest(BaseModel):
    title: str
    summary: str
    html_path: str
    json_path: str | None = None
    thumbnails: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ViewerManifest(BaseModel):
    bundle_dir: str
    index_path: str
    assets: list[str] = Field(default_factory=list)
    scalars: list[str] = Field(default_factory=list)
    note: str | None = None


class UsageSnapshot(BaseModel):
    provider_backend: ProviderBackend
    estimated_tokens: int = 0
    estimated_cost_usd: float = 0.0
    context_budget_bucket: str = "small"
    note: str | None = None


class AnalysisJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.UPLOADED
    selected_solver: SolverKind = SolverKind.AUTO
    rationale: str | None = None
    progress: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    metrics: list[MetricRecord] = Field(default_factory=list)
    error: str | None = None
    connection_mode: ConnectionMode = ConnectionMode.OPENAI_API
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    request: AnalysisRequest | None = None
    preflight_plan: PreflightPlan | None = None

    @model_validator(mode="after")
    def sync_updated(self) -> "AnalysisJob":
        if self.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            self.progress = max(self.progress, 1.0)
        return self


class ToolRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    job_id: str | None = None
    tool: ToolName
    version: str = "v1"
    idempotency_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    request_id: str
    ok: bool
    payload: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    side_effects: list[str] = Field(default_factory=list)
