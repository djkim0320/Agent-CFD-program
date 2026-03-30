export * from "../generated/contracts";

export interface FrameFormState {
  forwardAxis: "x" | "y" | "z";
  upAxis: "x" | "y" | "z";
  symmetryPlane: string;
  momentCenter: string;
}

export interface ReferenceValuesFormState {
  area: string;
  length: string;
  span: string;
}

export interface FlowFormState {
  velocity: string;
  mach: string;
  aoa: string;
  sideslip: string;
  altitude: string;
  density: string;
  viscosity: string;
}

export interface AnalysisFormState {
  geometryFile: File | null;
  unit: string;
  frame: FrameFormState;
  referenceValues: ReferenceValuesFormState;
  flow: FlowFormState;
  fidelity: "fast" | "balanced" | "high";
  solverPreference: "auto" | "vspaero" | "su2" | "openfoam";
  notes: string;
}

export type DiagnosticScope = "global" | "provider" | "decode" | "stream" | "runtime" | "preflight" | "artifact";

export type DiagnosticSeverity = "info" | "warning" | "error";

export type StreamHealthState = "idle" | "connecting" | "open" | "disconnected" | "failed";

export interface StreamHealth {
  state: StreamHealthState;
  lastEventAt: string | null;
  lastError: string | null;
  eventCount: number;
}

export interface DiagnosticIssue {
  id: string;
  scope: DiagnosticScope;
  subjectId: string | null;
  code: string;
  title: string;
  detail: string;
  severity: DiagnosticSeverity;
  impact: string | null;
  nextAction: string | null;
  raw: unknown;
  createdAt: string;
}

export type UiAiReviewState = "ready" | "unavailable" | "disabled" | "failed";

export type UiRuntimeState = "ready" | "blocked";

export type UiProviderState = "ready" | "unavailable";
