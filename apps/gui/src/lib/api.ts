import type {
  AIAssistMode,
  ConnectionMode,
  ConnectionStatusResponse,
  CreateJobRequest,
  ExecutionMode,
  GeometryTriageFinding,
  InstallStatusResponse,
  JobEventRecord,
  JobEventType,
  JobSummaryResponse,
  PreflightResponse,
  SolverKind,
  SubagentFindings,
} from "../generated/contracts";
import type { AnalysisFormState } from "./types";

const API_BASE = "/api/v1";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function toExecutionMode(value: unknown): ExecutionMode {
  return value === "scaffold" ? "scaffold" : "real";
}

function toAIAssistMode(value: unknown): AIAssistMode {
  return value === "local_fallback" || value === "disabled" ? value : "remote";
}

function toSolverKind(value: unknown): SolverKind {
  return value === "vspaero" || value === "su2" || value === "openfoam" ? value : "su2";
}

function normalizeGeometryTriage(value: unknown): GeometryTriageFinding {
  const record = isRecord(value) ? value : {};
  return {
    geometry_kind: record.geometry_kind === "aircraft_vsp" ? "aircraft_vsp" : "general_3d",
    risks: toStringArray(record.risks),
    missing_inputs: toStringArray(record.missing_inputs),
    repairability: record.repairability === "blocked" ? "blocked" : "repairable",
    notes: toStringArray(record.notes),
  };
}

function normalizeSolverPlanner(value: unknown) {
  const record = isRecord(value) ? value : {};
  return {
    recommended_solver: toSolverKind(record.recommended_solver),
    rationale: typeof record.rationale === "string" ? record.rationale : "",
    execution_mode: toExecutionMode(record.execution_mode),
    warnings: toStringArray(record.warnings),
    deferred_scope: toStringArray(record.deferred_scope),
  };
}

function normalizeAuthAndPolicy(value: unknown) {
  const record = isRecord(value) ? value : {};
  return {
    allowed: typeof record.allowed === "boolean" ? record.allowed : true,
    ai_warnings: toStringArray(record.ai_warnings),
    policy_warnings: toStringArray(record.policy_warnings),
    export_scope: "summary_only" as const,
    notes: toStringArray(record.notes),
  };
}

function normalizeSubagentFindings(value: unknown): SubagentFindings {
  const record = isRecord(value) ? value : {};
  return {
    geometry_triage: normalizeGeometryTriage(record.geometry_triage),
    solver_planner: normalizeSolverPlanner(record.solver_planner),
    auth_and_policy_reviewer: normalizeAuthAndPolicy(record.auth_and_policy_reviewer),
  };
}

function normalizeConnectionStatus(raw: unknown, connectionId: ConnectionMode): ConnectionStatusResponse {
  const record = isRecord(raw) ? raw : {};
  return {
    connection_id:
      typeof record.connection_id === "string"
        ? record.connection_id
        : typeof record.id === "string"
          ? record.id
          : connectionId,
    mode:
      record.mode === "codex_oauth" || record.mode === "openai_api" ? record.mode : connectionId,
    connected: typeof record.connected === "boolean" ? record.connected : true,
    provider_ready: typeof record.provider_ready === "boolean" ? record.provider_ready : true,
    backend: typeof record.backend === "string" ? record.backend : "local",
    warnings: toStringArray(record.warnings),
  };
}

function normalizeInstallStatus(raw: unknown): InstallStatusResponse {
  const record = isRecord(raw) ? raw : {};
  return {
    docker_ok: typeof record.docker_ok === "boolean" ? record.docker_ok : false,
    gmsh_ok: typeof record.gmsh_ok === "boolean" ? record.gmsh_ok : false,
    su2_image_ok: typeof record.su2_image_ok === "boolean" ? record.su2_image_ok : false,
    workspace_ok: typeof record.workspace_ok === "boolean" ? record.workspace_ok : false,
    install_warnings: toStringArray(record.install_warnings),
  };
}

function normalizePreflightResponse(raw: unknown): PreflightResponse {
  const record = isRecord(raw) ? raw : {};
  const selectedSolver = toSolverKind(record.selected_solver ?? record.selectedSolver);
  const runtimeBlockers = toStringArray(record.runtime_blockers ?? record.runtimeBlockers ?? record.blockers);
  const installWarnings = toStringArray(record.install_warnings ?? record.installWarnings ?? record.warnings);
  const aiWarnings = toStringArray(record.ai_warnings ?? record.aiWarnings);
  const policyWarnings = toStringArray(record.policy_warnings ?? record.policyWarnings);
  const subagentFindings = normalizeSubagentFindings(
    record.subagent_findings ?? record.subagentFindings ?? record.findings,
  );

  const runtimeEstimateMinutes = toNumber(
    record.runtime_estimate_minutes ??
      record.runtimeEstimateMinutes ??
      record.runtime_estimate ??
      record.runtimeEstimate,
  );
  const memoryEstimateGb = toNumber(
    record.memory_estimate_gb ?? record.memoryEstimateGb ?? record.memory_estimate ?? record.memoryEstimate,
  );

  return {
    preflight_id:
      typeof record.preflight_id === "string"
        ? record.preflight_id
        : typeof record.id === "string"
          ? record.id
          : "preflight_unknown",
    selected_solver: selectedSolver,
    execution_mode: toExecutionMode(record.execution_mode ?? record.executionMode),
    ai_assist_mode: toAIAssistMode(record.ai_assist_mode ?? record.aiAssistMode),
    runtime_blockers: runtimeBlockers,
    install_warnings: installWarnings,
    ai_warnings: aiWarnings,
    policy_warnings: policyWarnings,
    subagent_findings: subagentFindings,
    request_digest:
      typeof record.request_digest === "string"
        ? record.request_digest
        : typeof record.requestDigest === "string"
          ? record.requestDigest
          : "",
    source_hash:
      typeof record.source_hash === "string"
        ? record.source_hash
        : typeof record.sourceHash === "string"
          ? record.sourceHash
          : "",
    normalized_manifest_hash:
      typeof record.normalized_manifest_hash === "string"
        ? record.normalized_manifest_hash
        : typeof record.normalizedManifestHash === "string"
          ? record.normalizedManifestHash
          : "",
    normalized_geometry_hash:
      typeof record.normalized_geometry_hash === "string"
        ? record.normalized_geometry_hash
        : typeof record.normalizedGeometryHash === "string"
          ? record.normalizedGeometryHash
          : "",
    normalization_summary:
      isRecord(record.normalization_summary)
        ? (record.normalization_summary as Record<string, unknown>)
        : isRecord(record.normalizationSummary)
          ? (record.normalizationSummary as Record<string, unknown>)
          : {},
    physics_grade: "stable_trend_grade",
    mesh_strategy: "box_farfield",
    runtime_estimate_minutes: runtimeEstimateMinutes,
    memory_estimate_gb: memoryEstimateGb,
    confidence: toNumber(record.confidence ?? record.confidence_score, 0),
    rationale: typeof record.rationale === "string" ? record.rationale : "",
  };
}

function normalizeJobArtifact(value: unknown): JobSummaryResponse["artifacts"][number] {
  const record = isRecord(value) ? value : {};
  return {
    kind: typeof record.kind === "string" ? record.kind : "artifact",
    name: typeof record.name === "string" ? record.name : typeof record.path === "string" ? record.path : "artifact",
    path: typeof record.path === "string" ? record.path : "",
    size_bytes:
      typeof record.size_bytes === "number"
        ? record.size_bytes
        : typeof record.sizeBytes === "number"
          ? record.sizeBytes
          : null,
    download_url:
      typeof record.download_url === "string"
        ? record.download_url
        : typeof record.downloadUrl === "string"
          ? record.downloadUrl
          : null,
  };
}

function normalizeJobSummary(raw: unknown): JobSummaryResponse {
  const record = isRecord(raw) ? raw : {};
  const runtimeBlockers = toStringArray(record.runtime_blockers ?? record.runtimeBlockers);
  const installWarnings = toStringArray(record.install_warnings ?? record.installWarnings ?? record.warnings);
  const aiWarnings = toStringArray(record.ai_warnings ?? record.aiWarnings);
  const policyWarnings = toStringArray(record.policy_warnings ?? record.policyWarnings);
  const residualHistory = Array.isArray(record.residual_history)
    ? record.residual_history
        .map((point) => {
          if (!isRecord(point)) {
            return null;
          }
          return {
            iteration: toNumber(point.iteration, 0),
            residual: toNumber(point.residual, 0),
          };
        })
        .filter((point): point is JobSummaryResponse["residual_history"][number] => point !== null)
    : [];

  return {
    id: typeof record.id === "string" ? record.id : "job_unknown",
    status:
      record.status === "waiting_approval" ||
      record.status === "queued" ||
      record.status === "running" ||
      record.status === "postprocessing" ||
      record.status === "completed" ||
      record.status === "failed" ||
      record.status === "cancelled"
        ? record.status
        : "uploaded",
    selected_solver: toSolverKind(record.selected_solver ?? record.selectedSolver),
    execution_mode: toExecutionMode(record.execution_mode ?? record.executionMode),
    ai_assist_mode: toAIAssistMode(record.ai_assist_mode ?? record.aiAssistMode),
    source_file_name:
      typeof record.source_file_name === "string"
        ? record.source_file_name
        : typeof record.sourceFileName === "string"
          ? record.sourceFileName
          : "unknown geometry",
    created_at:
      typeof record.created_at === "string"
        ? record.created_at
        : typeof record.createdAt === "string"
          ? record.createdAt
          : new Date().toISOString(),
    updated_at:
      typeof record.updated_at === "string"
        ? record.updated_at
        : typeof record.updatedAt === "string"
          ? record.updatedAt
          : new Date().toISOString(),
    preflight_snapshot_id:
      typeof record.preflight_snapshot_id === "string"
        ? record.preflight_snapshot_id
        : typeof record.preflightSnapshotId === "string"
          ? record.preflightSnapshotId
          : "",
    rationale: typeof record.rationale === "string" ? record.rationale : "",
    progress: toNumber(record.progress, 0),
    runtime_blockers: runtimeBlockers,
    install_warnings: installWarnings,
    ai_warnings: aiWarnings,
    policy_warnings: policyWarnings,
    artifacts: Array.isArray(record.artifacts) ? record.artifacts.map(normalizeJobArtifact) : [],
    metrics: isRecord(record.metrics) ? (record.metrics as Record<string, string | number>) : {},
    residual_history: residualHistory,
    error:
      typeof record.error === "string"
        ? record.error
        : record.error === null || typeof record.error === "undefined"
          ? null
          : String(record.error),
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

type ApiJobEventRecord = JobEventRecord;

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    let detail = "";
    try {
      detail = await response.text();
    } catch {
      detail = "";
    }
    throw new Error(
      detail ? `API request failed: ${response.status} ${detail}` : `API request failed: ${response.status}`,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
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
  return normalizeInstallStatus(await requestJson<unknown>("/install/status"));
}

export async function loadConnectionStatus(connectionId: ConnectionMode): Promise<ConnectionStatusResponse> {
  try {
    return normalizeConnectionStatus(await requestJson<unknown>(`/connections/${connectionId}/status`), connectionId);
  } catch (error) {
    if (connectionId === "openai_api" || connectionId === "codex_oauth") {
      return normalizeConnectionStatus(
        await requestJson<unknown>(`/connections/status?mode=${connectionId}`),
        connectionId,
      );
    }
    throw error;
  }
}

export async function submitPreflight(
  request: AnalysisFormState,
  connectionMode: ConnectionMode,
): Promise<PreflightResponse> {
  return normalizePreflightResponse(
    await requestJson<unknown>("/jobs/preflight", {
      method: "POST",
      body: buildPreflightFormData(request, connectionMode),
    }),
  );
}

export async function createJobFromPreflight(preflightId: string): Promise<JobSummaryResponse> {
  const payload: CreateJobRequest = { preflight_id: preflightId };
  return normalizeJobSummary(
    await requestJson<unknown>("/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload),
    }),
  );
}

export async function approveJob(jobId: string): Promise<JobSummaryResponse> {
  return normalizeJobSummary(
    await requestJson<unknown>(`/jobs/${jobId}/approve`, {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    }),
  );
}

export async function cancelJob(jobId: string): Promise<JobSummaryResponse> {
  return normalizeJobSummary(
    await requestJson<unknown>(`/jobs/${jobId}/cancel`, {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    }),
  );
}

export async function getJob(jobId: string): Promise<JobSummaryResponse> {
  return normalizeJobSummary(await requestJson<unknown>(`/jobs/${jobId}`));
}

export async function listJobs(): Promise<JobSummaryResponse[]> {
  const response = await requestJson<unknown>("/jobs");
  return Array.isArray(response) ? response.map(normalizeJobSummary) : [];
}

export async function loadJobEvents(jobId: string): Promise<JobEventRecord[]> {
  const response = await requestJson<unknown>(`/jobs/${jobId}/history`);
  if (!Array.isArray(response)) {
    return [];
  }
  return response.map((record) => {
    const event = isRecord(record) ? record : {};
    return {
      id: typeof event.id === "string" ? event.id : String(event.seq ?? Math.random()),
      job_id: typeof event.job_id === "string" ? event.job_id : jobId,
      seq: toNumber(event.seq, 0),
      event_type:
        event.event_type === "job.status" ||
        event.event_type === "preflight.started" ||
        event.event_type === "preflight.completed" ||
        event.event_type === "approval.required" ||
        event.event_type === "subagent.started" ||
        event.event_type === "subagent.completed" ||
        event.event_type === "tool.started" ||
        event.event_type === "tool.progress" ||
        event.event_type === "tool.completed" ||
        event.event_type === "solver.stdout" ||
        event.event_type === "solver.metrics" ||
        event.event_type === "artifact.ready" ||
        event.event_type === "report.ready" ||
        event.event_type === "job.completed" ||
        event.event_type === "job.failed" ||
        event.event_type === "job.cancelled"
          ? event.event_type
          : "job.status",
      payload: isRecord(event.payload) ? event.payload : {},
      created_at:
        typeof event.created_at === "string" ? event.created_at : new Date().toISOString(),
    };
  });
}

export function subscribeJobEvents(jobId: string, onEvent: (event: JobEventRecord) => void): () => void {
  const source = new EventSource(`${API_BASE}/jobs/${jobId}/events`);
  const handleMessage = (message: MessageEvent<string>) => {
    try {
      const parsed = JSON.parse(message.data) as unknown;
      const event = loadEventRecord(parsed, jobId);
      onEvent(event);
    } catch {
      // Ignore malformed heartbeat data.
    }
  };

  const eventTypes = [
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

  for (const eventType of eventTypes) {
    source.addEventListener(eventType, handleMessage as EventListener);
  }

  source.addEventListener("heartbeat", () => {
    // Keep the stream warm without affecting UI state.
  });

  source.onerror = () => {
    source.close();
  };

  return () => {
    for (const eventType of eventTypes) {
      source.removeEventListener(eventType, handleMessage as EventListener);
    }
    source.close();
  };
}

export type { JobEventType };

function loadEventRecord(raw: unknown, jobId: string): JobEventRecord {
  const record = isRecord(raw) ? raw : {};
  return {
    id: typeof record.id === "string" ? record.id : String(record.seq ?? Math.random()),
    job_id: typeof record.job_id === "string" ? record.job_id : jobId,
    seq: toNumber(record.seq, 0),
    event_type:
      record.event_type === "job.status" ||
      record.event_type === "preflight.started" ||
      record.event_type === "preflight.completed" ||
      record.event_type === "approval.required" ||
      record.event_type === "subagent.started" ||
      record.event_type === "subagent.completed" ||
      record.event_type === "tool.started" ||
      record.event_type === "tool.progress" ||
      record.event_type === "tool.completed" ||
      record.event_type === "solver.stdout" ||
      record.event_type === "solver.metrics" ||
      record.event_type === "artifact.ready" ||
      record.event_type === "report.ready" ||
      record.event_type === "job.completed" ||
      record.event_type === "job.failed" ||
      record.event_type === "job.cancelled"
        ? record.event_type
        : "job.status",
    payload: isRecord(record.payload) ? record.payload : {},
    created_at: typeof record.created_at === "string" ? record.created_at : new Date().toISOString(),
  };
}
