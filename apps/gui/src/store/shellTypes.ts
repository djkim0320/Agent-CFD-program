import type {
  AnalysisFormState,
  AIAssistMode,
  ConnectionMode,
  ConnectionStatusResponse,
  DiagnosticIssue,
  InstallStatusResponse,
  JobArtifact,
  JobEventRecord,
  JobStatus,
  JobSummaryResponse,
  PreflightResponse,
  StreamHealth,
} from "../lib/types";

export type RoutePane = "workspace" | "reports" | "settings";
export type InspectorTab = "snapshot" | "run" | "artifacts" | "environment" | "diagnostics";
export type ComposerScope = "draft" | "job";

export interface PendingState {
  boot: boolean;
  preflight: boolean;
  approve: boolean;
  refresh: boolean;
  cancel: boolean;
  composer: boolean;
}

export interface ComposerNote {
  id: string;
  scope: ComposerScope;
  text: string;
  createdAt: string;
}

export interface SessionRecord {
  job: JobSummaryResponse;
  updatedAt: string | null;
}

export interface ShellState {
  routePane: RoutePane;
  connectionMode: ConnectionMode;
  connectionStatus: ConnectionStatusResponse | null;
  installStatus: InstallStatusResponse | null;
  draft: AnalysisFormState;
  draftPreflight: PreflightResponse | null;
  jobsById: Record<string, SessionRecord>;
  jobOrder: string[];
  eventsByJobId: Record<string, JobEventRecord[]>;
  notesByScope: Record<string, ComposerNote[]>;
  diagnosticIssues: DiagnosticIssue[];
  streamHealthByJobId: Record<string, StreamHealth>;
  selectedJobId: string | null;
  selectedInspectorTab: InspectorTab;
  selectedArtifactKind: string | null;
  composerText: string;
  pending: PendingState;
  dismissedDiagnosticIds: string[];
}

export type ShellAction =
  | { type: "set-route-pane"; pane: RoutePane }
  | { type: "set-connection-mode"; mode: ConnectionMode }
  | { type: "set-connection-status"; status: ConnectionStatusResponse | null }
  | { type: "set-install-status"; status: InstallStatusResponse | null }
  | { type: "set-draft"; draft: AnalysisFormState }
  | { type: "reset-draft"; draft: AnalysisFormState }
  | { type: "set-draft-field"; field: keyof AnalysisFormState; value: string | File | null }
  | { type: "set-draft-section"; section: "frame" | "referenceValues" | "flow"; value: Record<string, string> }
  | { type: "set-preflight"; preflight: PreflightResponse | null }
  | { type: "ingest-jobs"; jobs: JobSummaryResponse[]; receivedAt: string }
  | { type: "upsert-job"; job: JobSummaryResponse; updatedAt: string | null }
  | { type: "select-job"; jobId: string | null }
  | { type: "merge-job-status"; jobId: string; status?: JobStatus; progress?: number; error?: string | null; updatedAt?: string | null }
  | { type: "merge-job-metrics"; jobId: string; metrics: Record<string, string | number>; updatedAt?: string | null }
  | { type: "append-job-artifact"; jobId: string; artifact: JobArtifact; updatedAt?: string | null }
  | { type: "append-event"; jobId: string; event: JobEventRecord }
  | { type: "set-events"; jobId: string; events: JobEventRecord[] }
  | { type: "append-note"; scope: ComposerScope; text: string; createdAt: string }
  | { type: "append-diagnostic-issue"; issue: DiagnosticIssue }
  | { type: "clear-diagnostics"; scope?: ComposerScope | "global"; subjectId?: string | null }
  | { type: "set-stream-health"; jobId: string; state: StreamHealth["state"]; patch?: Partial<StreamHealth> }
  | { type: "set-selected-inspector-tab"; tab: InspectorTab }
  | { type: "set-selected-artifact-kind"; kind: string | null }
  | { type: "set-composer-text"; text: string }
  | { type: "set-pending"; key: keyof PendingState; pending: boolean }
  | { type: "dismiss-diagnostic-issue"; issueId: string };

export function createInitialDraft(): AnalysisFormState {
  return {
    geometryFile: null,
    unit: "m",
    frame: { forwardAxis: "x", upAxis: "z", symmetryPlane: "", momentCenter: "0, 0, 0" },
    referenceValues: { area: "1.0", length: "1.0", span: "1.0" },
    flow: {
      velocity: "60",
      mach: "0.18",
      aoa: "4",
      sideslip: "0",
      altitude: "0",
      density: "1.225",
      viscosity: "1.81e-5",
    },
    fidelity: "balanced",
    solverPreference: "auto",
    notes: "Steady external aerodynamics for a local desktop workflow.",
  };
}

export function createInitialShellState(): ShellState {
  return {
    routePane: "workspace",
    connectionMode: "openai_api",
    connectionStatus: null,
    installStatus: null,
    draft: createInitialDraft(),
    draftPreflight: null,
    jobsById: {},
    jobOrder: [],
    eventsByJobId: {},
    notesByScope: {},
    diagnosticIssues: [],
    streamHealthByJobId: {},
    selectedJobId: null,
    selectedInspectorTab: "snapshot",
    selectedArtifactKind: null,
    composerText: "",
    pending: {
      boot: false,
      preflight: false,
      approve: false,
      refresh: false,
      cancel: false,
      composer: false,
    },
    dismissedDiagnosticIds: [],
  };
}

export function currentScopeKey(selectedJobId: string | null): ComposerScope | string {
  return selectedJobId ?? "draft";
}
