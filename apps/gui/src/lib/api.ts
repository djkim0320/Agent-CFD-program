import type {
  AIAssistMode,
  ConnectionMode,
  ConnectionStatusResponse,
  CreateJobRequest,
  ExecutionMode,
  GeometryTriageFinding,
  InstallStatusResponse,
  IssueRecord,
  JobEventRecord,
  JobEventType,
  JobSummaryResponse,
  NormalizationSummary,
  PreflightResponse,
  SolverKind,
  SubagentFindings,
} from "../generated/contracts";
import type { AnalysisFormState } from "./types";

const API_BASE = "/api/v1";

const JOB_EVENT_TYPES = new Set<JobEventType>([
  "job.status",
  "preflight.started",
  "preflight.completed",
  "approval.required",
  "subagent.started",
  "subagent.completed",
  "tool.started",
  "tool.progress",
  "tool.completed",
  "solver.stdout",
  "solver.metrics",
  "artifact.ready",
  "report.ready",
  "job.completed",
  "job.failed",
  "job.cancelled",
]);

export class ApiRequestError extends Error {
  readonly path: string;
  readonly status: number;
  readonly details: string;

  constructor(path: string, status: number, details: string) {
    super(details ? `API request failed (${status}) for ${path}: ${details}` : `API request failed (${status}) for ${path}`);
    this.name = "ApiRequestError";
    this.path = path;
    this.status = status;
    this.details = details;
  }
}

export class ApiDecodeError extends Error {
  readonly path: string;
  readonly raw: unknown;

  constructor(path: string, message: string, raw: unknown) {
    super(`API decode failed for ${path}: ${message}`);
    this.name = "ApiDecodeError";
    this.path = path;
    this.raw = raw;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function requireRecord(value: unknown, path: string, context: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new ApiDecodeError(path, `${context} must be an object`, value);
  }
  return value;
}

function requireString(value: unknown, path: string, field: string): string {
  if (typeof value !== "string") {
    throw new ApiDecodeError(path, `${field} must be a string`, value);
  }
  return value;
}

function requireBoolean(value: unknown, path: string, field: string): boolean {
  if (typeof value !== "boolean") {
    throw new ApiDecodeError(path, `${field} must be a boolean`, value);
  }
  return value;
}

function requireNumber(value: unknown, path: string, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiDecodeError(path, `${field} must be a finite number`, value);
  }
  return value;
}

function requireStringArray(value: unknown, path: string, field: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new ApiDecodeError(path, `${field} must be an array of strings`, value);
  }
  return value;
}

function requireEnum<T extends string>(value: unknown, path: string, field: string, allowed: readonly T[]): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) {
    throw new ApiDecodeError(path, `${field} must be one of: ${allowed.join(", ")}`, value);
  }
  return value as T;
}

function requireOptionalString(value: unknown, path: string, field: string): string | null {
  if (value === null || typeof value === "undefined") {
    return null;
  }
  if (typeof value !== "string") {
    throw new ApiDecodeError(path, `${field} must be a string or null`, value);
  }
  return value;
}

function requireOptionalNumber(value: unknown, path: string, field: string): number | null {
  if (value === null || typeof value === "undefined") {
    return null;
  }
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiDecodeError(path, `${field} must be a finite number or null`, value);
  }
  return value;
}

function requireOptionalInteger(value: unknown, path: string, field: string): number | null {
  if (value === null || typeof value === "undefined") {
    return null;
  }
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new ApiDecodeError(path, `${field} must be an integer or null`, value);
  }
  return value;
}

function parseJson(text: string, path: string): unknown {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new ApiDecodeError(path, error instanceof Error ? error.message : "Invalid JSON payload", text);
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (error) {
    throw new ApiRequestError(path, 0, error instanceof Error ? error.message : "Network request failed");
  }

  const bodyText = await response.text();
  if (!response.ok) {
    throw new ApiRequestError(path, response.status, bodyText || response.statusText);
  }
  if (!bodyText.trim()) {
    return undefined as T;
  }
  return parseJson(bodyText, path) as T;
}

function decodeGeometryTriageFinding(raw: unknown, path: string): GeometryTriageFinding {
  const record = requireRecord(raw, path, "geometry_triage");
  return {
    geometry_kind: requireEnum(record.geometry_kind, path, "geometry_kind", ["general_3d", "aircraft_vsp"] as const),
    risks: requireStringArray(record.risks, path, "risks"),
    missing_inputs: requireStringArray(record.missing_inputs, path, "missing_inputs"),
    repairability: requireEnum(record.repairability, path, "repairability", ["repairable", "blocked"] as const),
    notes: requireStringArray(record.notes, path, "notes"),
  };
}

function decodeSolverPlannerFinding(raw: unknown, path: string) {
  const record = requireRecord(raw, path, "solver_planner");
  return {
    recommended_solver: requireEnum(record.recommended_solver, path, "recommended_solver", ["auto", "vspaero", "su2", "openfoam"] as const),
    rationale: requireString(record.rationale, path, "rationale"),
    execution_mode: requireEnum(record.execution_mode, path, "execution_mode", ["real", "scaffold"] as const),
    warnings: requireStringArray(record.warnings, path, "warnings"),
    deferred_scope: requireStringArray(record.deferred_scope, path, "deferred_scope"),
  };
}

function decodeAuthAndPolicyFinding(raw: unknown, path: string) {
  const record = requireRecord(raw, path, "auth_and_policy_reviewer");
  return {
    allowed: requireBoolean(record.allowed, path, "allowed"),
    ai_warnings: requireStringArray(record.ai_warnings, path, "ai_warnings"),
    policy_warnings: requireStringArray(record.policy_warnings, path, "policy_warnings"),
    export_scope: requireEnum(record.export_scope, path, "export_scope", ["summary_only"] as const),
    notes: requireStringArray(record.notes, path, "notes"),
  };
}

function decodeSubagentFindings(raw: unknown, path: string): SubagentFindings {
  const record = requireRecord(raw, path, "subagent_findings");
  return {
    geometry_triage: decodeGeometryTriageFinding(record.geometry_triage, `${path}.geometry_triage`),
    solver_planner: decodeSolverPlannerFinding(record.solver_planner, `${path}.solver_planner`),
    auth_and_policy_reviewer: decodeAuthAndPolicyFinding(record.auth_and_policy_reviewer, `${path}.auth_and_policy_reviewer`),
  };
}

function decodeIssueRecord(raw: unknown, path: string): IssueRecord {
  const record = requireRecord(raw, path, "issue");
  return {
    code: requireString(record.code, path, "code"),
    message: requireString(record.message, path, "message"),
    guidance: requireOptionalString(record.guidance, path, "guidance"),
  };
}

function decodeStringNullableRecord(raw: unknown, path: string, field: string): Record<string, string | null> {
  const record = requireRecord(raw, path, field);
  const decoded: Record<string, string | null> = {};
  for (const [key, value] of Object.entries(record)) {
    if (value === null || typeof value === "undefined") {
      decoded[key] = null;
      continue;
    }
    if (typeof value !== "string") {
      throw new ApiDecodeError(path, `${field}.${key} must be a string or null`, value);
    }
    decoded[key] = value;
  }
  return decoded;
}

function decodeOptionalNumberArray(raw: unknown, path: string, field: string): number[] | null {
  if (raw === null || typeof raw === "undefined") {
    return null;
  }
  if (!Array.isArray(raw)) {
    throw new ApiDecodeError(path, `${field} must be an array of numbers or null`, raw);
  }
  return raw.map((item, index) => requireNumber(item, `${path}.${field}[${index}]`, field));
}

function decodeNormalizationSummary(raw: unknown, path: string): NormalizationSummary {
  const record = requireRecord(raw, path, "normalization_summary");
  return {
    source_format: requireOptionalString(record.source_format, path, "source_format"),
    declared_unit: requireString(record.declared_unit, path, "declared_unit"),
    canonical_unit: requireString(record.canonical_unit, path, "canonical_unit"),
    scale_factor_to_meter: requireNumber(record.scale_factor_to_meter, path, "scale_factor_to_meter"),
    axis_mapping: decodeStringNullableRecord(record.axis_mapping, path, "axis_mapping"),
    source_bbox: decodeOptionalNumberArray(record.source_bbox, path, "source_bbox"),
    normalized_bbox: decodeOptionalNumberArray(record.normalized_bbox, path, "normalized_bbox"),
    face_count: requireOptionalNumber(record.face_count, path, "face_count"),
    component_count: requireOptionalNumber(record.component_count, path, "component_count"),
    watertight:
      record.watertight === null || typeof record.watertight === "undefined"
        ? null
        : requireBoolean(record.watertight, path, "watertight"),
    repair_actions: requireStringArray(record.repair_actions, path, "repair_actions"),
    caveats: requireStringArray(record.caveats, path, "caveats"),
  };
}

function decodeConnectionStatus(raw: unknown, connectionId: ConnectionMode, path: string): ConnectionStatusResponse {
  const record = requireRecord(raw, path, "connection status");
  const connection_id = requireString(record.connection_id, path, "connection_id");
  const mode = requireEnum(record.mode, path, "mode", ["codex_oauth", "openai_api"] as const);
  if (connection_id !== connectionId || mode !== connectionId) {
    throw new ApiDecodeError(path, `connection status must match requested connection mode (${connectionId})`, raw);
  }
  return {
    connection_id,
    mode,
    connected: requireBoolean(record.connected, path, "connected"),
    provider_ready: requireBoolean(record.provider_ready, path, "provider_ready"),
    backend: requireString(record.backend, path, "backend"),
    warnings: requireStringArray(record.warnings, path, "warnings"),
  };
}

function decodeInstallStatus(raw: unknown, path: string): InstallStatusResponse {
  const record = requireRecord(raw, path, "install status");
  return {
    docker_ok: requireBoolean(record.docker_ok, path, "docker_ok"),
    gmsh_ok: requireBoolean(record.gmsh_ok, path, "gmsh_ok"),
    su2_image_ok: requireBoolean(record.su2_image_ok, path, "su2_image_ok"),
    workspace_ok: requireBoolean(record.workspace_ok, path, "workspace_ok"),
    install_warnings: requireStringArray(record.install_warnings, path, "install_warnings"),
  };
}

function decodePreflightResponse(raw: unknown, path: string): PreflightResponse {
  const record = requireRecord(raw, path, "preflight response");
  const normalizationSummary =
    record.normalization_summary === null || typeof record.normalization_summary === "undefined"
      ? null
      : decodeNormalizationSummary(record.normalization_summary, `${path}.normalization_summary`);
  const subagentFindings =
    record.subagent_findings === null || typeof record.subagent_findings === "undefined"
      ? null
      : decodeSubagentFindings(record.subagent_findings, `${path}.subagent_findings`);
  const runtimeBlockerDetails = Array.isArray(record.runtime_blocker_details)
    ? record.runtime_blocker_details.map((item, index) => decodeIssueRecord(item, `${path}.runtime_blocker_details[${index}]`))
    : (() => {
        throw new ApiDecodeError(path, "runtime_blocker_details must be an array", record.runtime_blocker_details);
      })();
  return {
    preflight_id: requireString(record.preflight_id, path, "preflight_id"),
    selected_solver: requireEnum(record.selected_solver, path, "selected_solver", ["auto", "vspaero", "su2", "openfoam"] as const),
    execution_mode: requireEnum(record.execution_mode, path, "execution_mode", ["real", "scaffold"] as const),
    ai_assist_mode: requireEnum(record.ai_assist_mode, path, "ai_assist_mode", ["remote", "unavailable", "disabled", "failed"] as const),
    ai_review_status:
      record.ai_review_status === null || typeof record.ai_review_status === "undefined"
        ? null
        : requireEnum(record.ai_review_status, path, "ai_review_status", ["remote", "unavailable", "disabled", "failed"] as const),
    ai_review_reason: requireOptionalString(record.ai_review_reason, path, "ai_review_reason"),
    runtime_blockers: requireStringArray(record.runtime_blockers, path, "runtime_blockers"),
    runtime_blocker_details: runtimeBlockerDetails,
    install_warnings: requireStringArray(record.install_warnings, path, "install_warnings"),
    ai_warnings: requireStringArray(record.ai_warnings, path, "ai_warnings"),
    policy_warnings: requireStringArray(record.policy_warnings, path, "policy_warnings"),
    subagent_findings: subagentFindings,
    request_digest: requireString(record.request_digest, path, "request_digest"),
    source_hash: requireString(record.source_hash, path, "source_hash"),
    normalized_manifest_hash: requireString(record.normalized_manifest_hash, path, "normalized_manifest_hash"),
    normalized_geometry_hash: requireOptionalString(record.normalized_geometry_hash, path, "normalized_geometry_hash"),
    normalization_summary: normalizationSummary,
    physics_grade: requireEnum(record.physics_grade, path, "physics_grade", ["stable_trend_grade"] as const),
    mesh_strategy: requireEnum(record.mesh_strategy, path, "mesh_strategy", ["box_farfield"] as const),
    runtime_estimate_minutes: requireNumber(record.runtime_estimate_minutes, path, "runtime_estimate_minutes"),
    memory_estimate_gb: requireNumber(record.memory_estimate_gb, path, "memory_estimate_gb"),
    confidence: requireNumber(record.confidence, path, "confidence"),
    rationale: requireString(record.rationale, path, "rationale"),
  };
}

function decodeJobArtifact(raw: unknown, path: string): JobSummaryResponse["artifacts"][number] {
  const record = requireRecord(raw, path, "artifact");
  return {
    kind: requireString(record.kind, path, "kind"),
    path: requireString(record.path, path, "path"),
    sha256: requireOptionalString(record.sha256, path, "sha256"),
    size_bytes: requireOptionalNumber(record.size_bytes, path, "size_bytes"),
    created_at: requireOptionalString(record.created_at, path, "created_at"),
  };
}

function decodeResidualHistory(raw: unknown, path: string): JobSummaryResponse["residual_history"] {
  if (!Array.isArray(raw)) {
    throw new ApiDecodeError(path, "residual_history must be an array", raw);
  }
  return raw.map((point, index) => {
    const record = requireRecord(point, `${path}[${index}]`, "residual_history point");
    return {
      iteration: requireNumber(record.iteration, `${path}[${index}]`, "iteration"),
      residual: requireNumber(record.residual, `${path}[${index}]`, "residual"),
    };
  });
}

function decodeMetrics(raw: unknown, path: string): Record<string, string | number> {
  const record = requireRecord(raw, path, "metrics");
  const metrics: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(record)) {
    if (typeof value === "string" || typeof value === "number") {
      metrics[key] = value;
      continue;
    }
    throw new ApiDecodeError(path, `metrics.${key} must be a string or number`, value);
  }
  return metrics;
}

function decodeJobSummary(raw: unknown, path: string): JobSummaryResponse {
  const record = requireRecord(raw, path, "job summary");
  return {
    id: requireString(record.id, path, "id"),
    status: requireEnum(record.status, path, "status", [
      "uploaded",
      "preflighting",
      "waiting_approval",
      "queued",
      "running",
      "postprocessing",
      "completed",
      "failed",
      "cancelled",
    ] as const),
    selected_solver: requireEnum(record.selected_solver, path, "selected_solver", ["auto", "vspaero", "su2", "openfoam"] as const),
    execution_mode: requireEnum(record.execution_mode, path, "execution_mode", ["real", "scaffold"] as const),
    ai_assist_mode: requireEnum(record.ai_assist_mode, path, "ai_assist_mode", ["remote", "unavailable", "disabled", "failed"] as const),
    ai_review_status:
      record.ai_review_status === null || typeof record.ai_review_status === "undefined"
        ? null
        : requireEnum(record.ai_review_status, path, "ai_review_status", ["remote", "unavailable", "disabled", "failed"] as const),
    ai_review_reason: requireOptionalString(record.ai_review_reason, path, "ai_review_reason"),
    source_file_name: requireString(record.source_file_name, path, "source_file_name"),
    created_at: requireString(record.created_at, path, "created_at"),
    updated_at: requireString(record.updated_at, path, "updated_at"),
    preflight_snapshot_id: requireString(record.preflight_snapshot_id, path, "preflight_snapshot_id"),
    rationale: requireOptionalString(record.rationale, path, "rationale"),
    progress: requireNumber(record.progress, path, "progress"),
    runtime_blockers: requireStringArray(record.runtime_blockers, path, "runtime_blockers"),
    runtime_blocker_details: Array.isArray(record.runtime_blocker_details)
      ? record.runtime_blocker_details.map((detail, index) => decodeIssueRecord(detail, `${path}.runtime_blocker_details[${index}]`))
      : (() => {
          throw new ApiDecodeError(path, "runtime_blocker_details must be an array", record.runtime_blocker_details);
        })(),
    install_warnings: requireStringArray(record.install_warnings, path, "install_warnings"),
    ai_warnings: requireStringArray(record.ai_warnings, path, "ai_warnings"),
    policy_warnings: requireStringArray(record.policy_warnings, path, "policy_warnings"),
    artifacts: Array.isArray(record.artifacts)
      ? record.artifacts.map((artifact, index) => decodeJobArtifact(artifact, `${path}.artifacts[${index}]`))
      : (() => {
          throw new ApiDecodeError(path, "artifacts must be an array", record.artifacts);
        })(),
    metrics: decodeMetrics(record.metrics, `${path}.metrics`),
    residual_history: decodeResidualHistory(record.residual_history, `${path}.residual_history`),
    error: requireOptionalString(record.error, path, "error"),
  };
}

function decodeJobEventType(value: unknown, path: string): JobEventType {
  if (typeof value !== "string" || !JOB_EVENT_TYPES.has(value as JobEventType)) {
    throw new ApiDecodeError(path, `event_type must be one of: ${Array.from(JOB_EVENT_TYPES).join(", ")}`, value);
  }
  return value as unknown as JobEventType;
}

function decodeJobEventRecord(raw: unknown, jobId: string, path: string): JobEventRecord {
  const record = requireRecord(raw, path, "job event");
  const eventJobId = requireString(record.job_id, path, "job_id");
  if (eventJobId !== jobId) {
    throw new ApiDecodeError(path, `job_id must match requested job (${jobId})`, raw);
  }
  return {
    id: record.id === null || typeof record.id === "undefined" ? null : requireOptionalInteger(record.id, path, "id"),
    job_id: eventJobId,
    seq: requireNumber(record.seq, path, "seq"),
    event_type: decodeJobEventType(record.event_type, path),
    payload: requireRecord(record.payload, path, "payload"),
    created_at: requireString(record.created_at, path, "created_at"),
  };
}

export function decodeJobStatusEventPayload(raw: unknown, path: string) {
  const record = requireRecord(raw, path, "job.status payload");
  return {
    status: requireEnum(record.status, path, "status", [
      "uploaded",
      "preflighting",
      "waiting_approval",
      "queued",
      "running",
      "postprocessing",
      "completed",
      "failed",
      "cancelled",
    ] as const),
    progress: typeof record.progress === "undefined" ? null : requireNumber(record.progress, path, "progress"),
    phase: requireOptionalString(record.phase, path, "phase"),
    message: requireOptionalString(record.message, path, "message"),
  };
}

export function decodeSolverMetricsEventPayload(raw: unknown, path: string) {
  const record = requireRecord(raw, path, "solver.metrics payload");
  return {
    metrics: decodeMetrics(record.metrics, `${path}.metrics`),
    residual_history_points:
      typeof record.residual_history_points === "undefined"
        ? null
        : requireNumber(record.residual_history_points, path, "residual_history_points"),
  };
}

export function decodeArtifactReadyEventPayload(raw: unknown, path: string) {
  const record = requireRecord(raw, path, "artifact.ready payload");
  return {
    artifact: decodeJobArtifact(record.artifact, `${path}.artifact`),
  };
}

export function decodeReportReadyEventPayload(raw: unknown, path: string) {
  const record = requireRecord(raw, path, "report.ready payload");
  return {
    report_path: requireOptionalString(record.report_path, path, "report_path"),
    summary_path: requireOptionalString(record.summary_path, path, "summary_path"),
  };
}

function appendOptionalField(formData: FormData, key: string, value: string | null | undefined) {
  if (typeof value !== "string") {
    return;
  }
  if (value.trim() === "") {
    return;
  }
  formData.set(key, value);
}

function deriveGeometryKind(request: AnalysisFormState): "general_3d" | "aircraft_vsp" {
  const name = request.geometryFile?.name.toLowerCase() ?? "";
  return name.endsWith(".vsp3") ? "aircraft_vsp" : "general_3d";
}

function buildPreflightFormData(request: AnalysisFormState, connectionMode: ConnectionMode): FormData {
  if (!request.geometryFile) {
    throw new Error("A geometry file is required for preflight.");
  }

  const formData = new FormData();
  formData.set("connection_mode", connectionMode);
  formData.set("geometry_kind", deriveGeometryKind(request));
  formData.set("unit", request.unit);
  formData.set("frame_forward_axis", request.frame.forwardAxis);
  formData.set("frame_up_axis", request.frame.upAxis);
  appendOptionalField(formData, "frame_symmetry_plane", request.frame.symmetryPlane);
  appendOptionalField(formData, "frame_moment_center", request.frame.momentCenter);
  formData.set("reference_area", request.referenceValues.area);
  appendOptionalField(formData, "reference_length", request.referenceValues.length);
  appendOptionalField(formData, "reference_span", request.referenceValues.span);
  appendOptionalField(formData, "flow_velocity", request.flow.velocity);
  appendOptionalField(formData, "flow_mach", request.flow.mach);
  formData.set("flow_aoa", request.flow.aoa);
  formData.set("flow_sideslip", request.flow.sideslip);
  appendOptionalField(formData, "flow_altitude", request.flow.altitude);
  appendOptionalField(formData, "flow_density", request.flow.density);
  appendOptionalField(formData, "flow_viscosity", request.flow.viscosity);
  formData.set("fidelity", request.fidelity);
  formData.set("solver_preference", request.solverPreference);
  appendOptionalField(formData, "notes", request.notes);
  formData.set("geometry_file", request.geometryFile);
  return formData;
}

export async function loadInstallStatus(): Promise<InstallStatusResponse> {
  return decodeInstallStatus(await requestJson<unknown>("/install/status"), "/install/status");
}

export async function loadConnectionStatus(connectionId: ConnectionMode): Promise<ConnectionStatusResponse> {
  return decodeConnectionStatus(await requestJson<unknown>(`/connections/${connectionId}/status`), connectionId, `/connections/${connectionId}/status`);
}

export async function submitPreflight(request: AnalysisFormState, connectionMode: ConnectionMode): Promise<PreflightResponse> {
  return decodePreflightResponse(
    await requestJson<unknown>("/jobs/preflight", {
      method: "POST",
      body: buildPreflightFormData(request, connectionMode),
    }),
    "/jobs/preflight",
  );
}

export async function createJobFromPreflight(preflightId: string): Promise<JobSummaryResponse> {
  const payload: CreateJobRequest = { preflight_id: preflightId };
  return decodeJobSummary(
    await requestJson<unknown>("/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    }),
    "/jobs",
  );
}

export async function approveJob(jobId: string): Promise<JobSummaryResponse> {
  return decodeJobSummary(
    await requestJson<unknown>(`/jobs/${jobId}/approve`, {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    }),
    `/jobs/${jobId}/approve`,
  );
}

export async function cancelJob(jobId: string): Promise<JobSummaryResponse> {
  return decodeJobSummary(
    await requestJson<unknown>(`/jobs/${jobId}/cancel`, {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    }),
    `/jobs/${jobId}/cancel`,
  );
}

export async function getJob(jobId: string): Promise<JobSummaryResponse> {
  return decodeJobSummary(await requestJson<unknown>(`/jobs/${jobId}`), `/jobs/${jobId}`);
}

export async function listJobs(): Promise<JobSummaryResponse[]> {
  const response = await requestJson<unknown>("/jobs");
  if (!Array.isArray(response)) {
    throw new ApiDecodeError("/jobs", "jobs response must be an array", response);
  }
  return response.map((job, index) => decodeJobSummary(job, `/jobs[${index}]`));
}

export async function loadJobEvents(jobId: string): Promise<JobEventRecord[]> {
  const response = await requestJson<unknown>(`/jobs/${jobId}/history`);
  if (!Array.isArray(response)) {
    throw new ApiDecodeError(`/jobs/${jobId}/history`, "history response must be an array", response);
  }
  return response.map((record, index) => decodeJobEventRecord(record, jobId, `/jobs/${jobId}/history[${index}]`));
}

export function subscribeJobEvents(
  jobId: string,
  onEvent: (event: JobEventRecord) => void,
  onError?: (error: Error) => void,
): () => void {
  const source = new EventSource(`${API_BASE}/jobs/${jobId}/events`);

  const eventTypes: JobEventType[] = [
    "job.status",
    "preflight.started",
    "preflight.completed",
    "approval.required",
    "subagent.started",
    "subagent.completed",
    "tool.started",
    "tool.progress",
    "tool.completed",
    "solver.stdout",
    "solver.metrics",
    "artifact.ready",
    "report.ready",
    "job.completed",
    "job.failed",
    "job.cancelled",
  ];

  const handleMessage = (eventType: JobEventType) => (message: MessageEvent<string>) => {
    try {
      const parsed = parseJson(message.data, `/jobs/${jobId}/events/${eventType}`);
      const record = decodeJobEventRecord(parsed, jobId, `/jobs/${jobId}/events/${eventType}`);
      onEvent(record);
    } catch (error) {
      onError?.(error instanceof Error ? error : new ApiDecodeError(`/jobs/${jobId}/events/${eventType}`, "Unable to decode event payload", message.data));
      source.close();
    }
  };

  const handlers = new Map<JobEventType, EventListener>();
  for (const eventType of eventTypes) {
    const handler = handleMessage(eventType) as EventListener;
    handlers.set(eventType, handler);
    source.addEventListener(eventType, handler);
  }

  source.addEventListener("heartbeat", () => undefined);

  source.onerror = () => {
    onError?.(new ApiRequestError(`/jobs/${jobId}/events`, 0, "The live event stream disconnected."));
    source.close();
  };

  return () => {
    for (const eventType of eventTypes) {
      const handler = handlers.get(eventType);
      if (handler) {
        source.removeEventListener(eventType, handler);
      }
    }
    source.close();
  };
}

export type { JobEventType };
