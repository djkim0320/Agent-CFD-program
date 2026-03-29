import type {
  AnalysisJob,
  AnalysisRequest,
  ConnectionMode,
  ConnectionStatus,
  JobEvent,
  JobStatus,
  PreflightPlan,
} from "./types";
import { createMockConnection, createMockJob, createMockPlan } from "./mock";

const API_BASE = "/api/v1";

type ApiJobRecord = {
  id: string;
  status: JobStatus;
  selected_solver: AnalysisJob["selectedSolver"];
  rationale: string | null;
  progress: number;
  warnings: string[];
  artifacts: Array<{ kind?: string; path: string }>;
  metrics: Record<string, string | number>;
  error?: string | null;
};

type ApiJobEventRecord = {
  id?: number;
  seq: number;
  event_type: JobEvent["type"] | string;
  payload: Record<string, unknown>;
  created_at: string;
};

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function deriveGeometryKind(request: AnalysisRequest): "general_3d" | "aircraft_vsp" {
  const name = request.geometryFile?.name.toLowerCase() ?? "";
  return name.endsWith(".vsp3") ? "aircraft_vsp" : "general_3d";
}

function buildFormData(request: AnalysisRequest, connectionMode: ConnectionMode): FormData {
  if (!request.geometryFile) {
    throw new Error("A geometry file is required.");
  }
  const formData = new FormData();
  formData.set("connection_mode", connectionMode);
  formData.set("unit", request.unit);
  formData.set("geometry_kind", deriveGeometryKind(request));
  formData.set("solver_preference", request.solverPreference);
  formData.set("fidelity", request.fidelity);
  formData.set("aoa", request.flow.aoa);
  formData.set("sideslip", request.flow.sideslip);
  if (request.flow.velocity) {
    formData.set("velocity", request.flow.velocity);
  }
  if (request.flow.mach) {
    formData.set("mach", request.flow.mach);
  }
  formData.set("geometry_file", request.geometryFile);
  return formData;
}

function mapJob(record: ApiJobRecord): AnalysisJob {
  return {
    id: record.id,
    status: record.status,
    selectedSolver: record.selected_solver,
    rationale: record.rationale ?? "",
    progress: record.progress,
    warnings: record.warnings ?? [],
    artifacts: (record.artifacts ?? []).map((artifact) => ({
      name: artifact.kind ?? "artifact",
      path: artifact.path,
    })),
    metrics: record.metrics ?? {},
    error: record.error ?? undefined,
  };
}

function mapEvent(record: ApiJobEventRecord): JobEvent {
  const payload = record.payload ?? {};
  const message =
    typeof payload.message === "string"
      ? payload.message
      : typeof payload.status === "string"
        ? `Status changed to ${payload.status}`
        : String(record.event_type);
  const progress =
    typeof payload.progress === "number"
      ? payload.progress
      : typeof payload.progress === "string"
        ? Number(payload.progress)
        : undefined;
  return {
    id: String(record.id ?? record.seq),
    type: (record.event_type as JobEvent["type"]) ?? "job.status",
    message,
    timestamp: record.created_at,
    progress,
  };
}

export async function loadConnectionStatus(mode: ConnectionMode): Promise<ConnectionStatus> {
  try {
    return await requestJson<ConnectionStatus>(`/connections/status?mode=${mode}`);
  } catch {
    return createMockConnection(mode);
  }
}

export async function submitPreflight(
  request: AnalysisRequest,
  connectionMode: ConnectionMode,
): Promise<PreflightPlan> {
  try {
    return await requestJson<PreflightPlan>("/jobs/preflight", {
      method: "POST",
      body: buildFormData(request, connectionMode),
    });
  } catch {
    return createMockPlan(request);
  }
}

export async function createJob(
  request: AnalysisRequest,
  connectionMode: ConnectionMode,
): Promise<AnalysisJob> {
  try {
    const response = await requestJson<ApiJobRecord>("/jobs", {
      method: "POST",
      body: buildFormData(request, connectionMode),
    });
    return mapJob(response);
  } catch {
    return createMockJob(request, createMockPlan(request)).job;
  }
}

export async function approveJob(jobId: string): Promise<AnalysisJob> {
  const response = await requestJson<ApiJobRecord>(`/jobs/${jobId}/approve`, { method: "POST" });
  return mapJob(response);
}

export async function getJob(jobId: string): Promise<AnalysisJob> {
  const response = await requestJson<ApiJobRecord>(`/jobs/${jobId}`);
  return mapJob(response);
}

export async function listJobs(): Promise<AnalysisJob[]> {
  try {
    const response = await requestJson<ApiJobRecord[]>("/jobs");
    return response.map(mapJob);
  } catch {
    return [];
  }
}

export async function loadJobEvents(jobId: string): Promise<JobEvent[]> {
  try {
    const response = await requestJson<ApiJobEventRecord[]>(`/jobs/${jobId}/history`);
    return response.map(mapEvent);
  } catch {
    return [];
  }
}

export function subscribeJobEvents(jobId: string, onEvent: (event: JobEvent) => void): () => void {
  const source = new EventSource(`${API_BASE}/jobs/${jobId}/events`);
  const handleMessage = (message: MessageEvent<string>) => {
    try {
      const parsed = JSON.parse(message.data) as ApiJobEventRecord;
      onEvent(mapEvent(parsed));
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
