export type ConnectionMode = "codex_oauth" | "openai_api";

export type SolverKind = "auto" | "vspaero" | "su2" | "openfoam";

export type JobStatus =
  | "uploaded"
  | "preflighting"
  | "waiting_approval"
  | "running"
  | "retrying"
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
  | "job.failed";

export interface ConnectionStatus {
  connected: boolean;
  mode: ConnectionMode;
  providerReady: boolean;
  backend: string;
  warnings: string[];
}

export interface AnalysisRequest {
  geometryFile: File | null;
  unit: string;
  frame: {
    forwardAxis: "x" | "y" | "z";
    upAxis: "x" | "y" | "z";
    symmetryPlane: string;
    momentCenter: string;
  };
  referenceValues: {
    area: string;
    length: string;
    span: string;
  };
  flow: {
    velocity: string;
    mach: string;
    aoa: string;
    sideslip: string;
    altitude: string;
    density: string;
    viscosity: string;
  };
  fidelity: "fast" | "balanced" | "high";
  solverPreference: SolverKind;
  notes: string;
}

export interface AnalysisJob {
  id: string;
  status: JobStatus;
  selectedSolver: SolverKind;
  rationale: string;
  progress: number;
  warnings: string[];
  artifacts: Array<{ name: string; path: string }>;
  metrics: Record<string, string | number>;
  error?: string;
}

export interface PreflightPlan {
  selectedSolver: SolverKind;
  candidateSolvers: SolverKind[];
  runtimeEstimate: string;
  memoryEstimate: string;
  confidence: number;
  warnings: string[];
  rationale: string;
}

export interface JobEvent {
  id: string;
  type: JobEventType;
  message: string;
  timestamp: string;
  progress?: number;
}
