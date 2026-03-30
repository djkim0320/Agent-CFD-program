export type ConnectionMode = "codex_oauth" | "openai_api";

export type SolverKind = "auto" | "vspaero" | "su2" | "openfoam";

export type GeometryKind = "general_3d" | "aircraft_vsp";

export type ExecutionMode = "real" | "scaffold";

export type AIAssistMode = "remote" | "local_fallback" | "disabled";

export type JobStatus =
  | "uploaded"
  | "preflighting"
  | "waiting_approval"
  | "queued"
  | "running"
  | "postprocessing"
  | "completed"
  | "failed"
  | "cancelled";

export type JobEventType =
  | "job.status"
  | "preflight.started"
  | "preflight.completed"
  | "approval.required"
  | "subagent.started"
  | "subagent.completed"
  | "tool.started"
  | "tool.progress"
  | "tool.completed"
  | "solver.stdout"
  | "solver.metrics"
  | "artifact.ready"
  | "report.ready"
  | "job.completed"
  | "job.failed"
  | "job.cancelled";

export interface InstallStatusResponse {
  docker_ok: boolean;
  gmsh_ok: boolean;
  su2_image_ok: boolean;
  workspace_ok: boolean;
  install_warnings: string[];
}

export interface ConnectionStatusResponse {
  connection_id: string;
  mode: ConnectionMode;
  connected: boolean;
  provider_ready: boolean;
  backend: string;
  warnings: string[];
}

export interface GeometryTriageFinding {
  geometry_kind: GeometryKind;
  risks: string[];
  missing_inputs: string[];
  repairability: "repairable" | "blocked";
  notes: string[];
}

export interface SolverPlannerFinding {
  recommended_solver: SolverKind;
  rationale: string;
  execution_mode: ExecutionMode;
  warnings: string[];
  deferred_scope: string[];
}

export interface AuthAndPolicyFinding {
  allowed: boolean;
  ai_warnings: string[];
  policy_warnings: string[];
  export_scope: "summary_only";
  notes: string[];
}

export interface SubagentFindings {
  geometry_triage: GeometryTriageFinding;
  solver_planner: SolverPlannerFinding;
  auth_and_policy_reviewer: AuthAndPolicyFinding;
}

export interface PreflightResponse {
  preflight_id: string;
  selected_solver: SolverKind;
  execution_mode: ExecutionMode;
  ai_assist_mode: AIAssistMode;
  runtime_blockers: string[];
  install_warnings: string[];
  ai_warnings: string[];
  policy_warnings: string[];
  subagent_findings: SubagentFindings;
  request_digest: string;
  source_hash: string;
  normalized_manifest_hash: string;
  normalized_geometry_hash: string;
  normalization_summary: Record<string, unknown>;
  physics_grade: "stable_trend_grade";
  mesh_strategy: "box_farfield";
  runtime_estimate_minutes: number;
  memory_estimate_gb: number;
  confidence: number;
  rationale: string;
}

export interface CreateJobRequest {
  preflight_id: string;
}

export interface JobArtifact {
  kind: string;
  name: string;
  path: string;
  size_bytes?: number | null;
  download_url?: string | null;
}

export interface ResidualHistoryPoint {
  iteration: number;
  residual: number;
}

export interface JobSummaryResponse {
  id: string;
  status: JobStatus;
  selected_solver: SolverKind;
  execution_mode: ExecutionMode;
  ai_assist_mode: AIAssistMode;
  source_file_name: string;
  created_at: string;
  updated_at: string;
  preflight_snapshot_id: string;
  rationale: string;
  progress: number;
  runtime_blockers: string[];
  install_warnings: string[];
  ai_warnings: string[];
  policy_warnings: string[];
  artifacts: JobArtifact[];
  metrics: Record<string, string | number>;
  residual_history: ResidualHistoryPoint[];
  error?: string | null;
}

export interface JobEventRecord {
  id: string;
  job_id: string;
  seq: number;
  event_type: JobEventType;
  payload: Record<string, unknown>;
  created_at: string;
}
