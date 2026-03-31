import type { JobSummaryResponse } from "../lib/types";
import type { SessionRecord, ShellAction, ShellState } from "./shellTypes";
import { createIdleStreamHealth, updateStreamHealth } from "./diagnostics";

export function createInitialDraft(): ShellState["draft"] {
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
    fidelity: "balanced" as const,
    solverPreference: "auto" as const,
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

function sortJobOrder(records: Record<string, SessionRecord>): string[] {
  return Object.values(records)
    .sort((left, right) => {
      const leftStamp = left.updatedAt ?? left.job.updated_at ?? left.job.created_at;
      const rightStamp = right.updatedAt ?? right.job.updated_at ?? right.job.created_at;
      return rightStamp.localeCompare(leftStamp);
    })
    .map((item) => item.job.id);
}

function upsertJobRecord(
  state: ShellState,
  job: JobSummaryResponse,
  updatedAt: string | null,
): Pick<ShellState, "jobsById" | "jobOrder"> {
  const nextJobsById: Record<string, SessionRecord> = {
    ...state.jobsById,
    [job.id]: {
      job,
      updatedAt: updatedAt ?? job.updated_at ?? state.jobsById[job.id]?.updatedAt ?? null,
    },
  };
  return {
    jobsById: nextJobsById,
    jobOrder: sortJobOrder(nextJobsById),
  };
}

export function shellReducer(state: ShellState, action: ShellAction): ShellState {
  switch (action.type) {
    case "set-route-pane":
      return { ...state, routePane: action.pane };
    case "set-connection-mode":
      return { ...state, connectionMode: action.mode };
    case "set-connection-status":
      return { ...state, connectionStatus: action.status };
    case "set-install-status":
      return { ...state, installStatus: action.status };
    case "set-draft":
      return { ...state, draft: action.draft };
    case "reset-draft":
      return {
        ...state,
        draft: action.draft,
        draftPreflight: null,
        selectedArtifactKind: null,
        selectedInspectorTab: "snapshot",
      };
    case "set-draft-field":
      return { ...state, draft: { ...state.draft, [action.field]: action.value } };
    case "set-draft-section":
      return {
        ...state,
        draft: {
          ...state.draft,
          [action.section]: {
            ...state.draft[action.section],
            ...action.value,
          },
        },
      };
    case "set-preflight":
      return {
        ...state,
        draftPreflight: action.preflight,
        selectedInspectorTab: action.preflight ? "snapshot" : state.selectedInspectorTab,
      };
    case "ingest-jobs": {
      let nextState = state;
      for (const job of action.jobs) {
        nextState = {
          ...nextState,
          ...upsertJobRecord(nextState, job, action.receivedAt),
        };
      }
      return nextState;
    }
    case "upsert-job":
      return {
        ...state,
        ...upsertJobRecord(state, action.job, action.updatedAt),
      };
    case "select-job":
      return {
        ...state,
        selectedJobId: action.jobId,
        selectedArtifactKind: null,
        selectedInspectorTab: action.jobId ? "run" : "snapshot",
      };
    case "merge-job-status": {
      const record = state.jobsById[action.jobId];
      if (!record) {
        return state;
      }
      const nextJob = {
        ...record.job,
        status: action.status ?? record.job.status,
        progress: action.progress ?? record.job.progress,
        error: typeof action.error === "undefined" ? record.job.error : action.error,
        updated_at: action.updatedAt ?? record.job.updated_at,
      };
      return {
        ...state,
        ...upsertJobRecord(state, nextJob, action.updatedAt ?? null),
      };
    }
    case "merge-job-metrics": {
      const record = state.jobsById[action.jobId];
      if (!record) {
        return state;
      }
      const nextJob = {
        ...record.job,
        metrics: {
          ...record.job.metrics,
          ...action.metrics,
        },
        updated_at: action.updatedAt ?? record.job.updated_at,
      };
      return {
        ...state,
        ...upsertJobRecord(state, nextJob, action.updatedAt ?? null),
      };
    }
    case "append-job-artifact": {
      const record = state.jobsById[action.jobId];
      if (!record) {
        return state;
      }
      const alreadyPresent = record.job.artifacts.some(
        (artifact) => artifact.kind === action.artifact.kind && artifact.path === action.artifact.path,
      );
      if (alreadyPresent) {
        return state;
      }
      const nextJob = {
        ...record.job,
        artifacts: [...record.job.artifacts, action.artifact],
        updated_at: action.updatedAt ?? record.job.updated_at,
      };
      return {
        ...state,
        ...upsertJobRecord(state, nextJob, action.updatedAt ?? null),
      };
    }
    case "append-event": {
      const current = state.eventsByJobId[action.jobId] ?? [];
      if (current.some((event) => event.id === action.event.id || event.seq === action.event.seq)) {
        return state;
      }
      return {
        ...state,
        eventsByJobId: {
          ...state.eventsByJobId,
          [action.jobId]: [...current, action.event].sort((left, right) => left.seq - right.seq),
        },
      };
    }
    case "set-events":
      return {
        ...state,
        eventsByJobId: {
          ...state.eventsByJobId,
          [action.jobId]: [...action.events].sort((left, right) => left.seq - right.seq),
        },
      };
    case "append-note": {
      const scope = action.scope === "job" ? state.selectedJobId ?? "draft" : "draft";
      const current = state.notesByScope[scope] ?? [];
      return {
        ...state,
        notesByScope: {
          ...state.notesByScope,
          [scope]: [
            ...current,
            {
              id: `${scope}-${action.createdAt}-${current.length + 1}`,
              scope: action.scope,
              text: action.text,
              createdAt: action.createdAt,
            },
          ],
        },
      };
    }
    case "append-diagnostic-issue":
      return {
        ...state,
        dismissedDiagnosticIds: state.dismissedDiagnosticIds.filter((issueId) => issueId !== action.issue.id),
        diagnosticIssues: state.diagnosticIssues.some((issue) => issue.id === action.issue.id)
          ? state.diagnosticIssues
          : [...state.diagnosticIssues, action.issue],
      };
    case "clear-diagnostics":
      return {
        ...state,
        diagnosticIssues: state.diagnosticIssues.filter((issue) => {
          if (action.subjectId && issue.subjectId !== action.subjectId) {
            return true;
          }
          if (action.scope === "draft") {
            return issue.subjectId !== "draft";
          }
          if (action.scope === "job") {
            return issue.subjectId !== state.selectedJobId;
          }
          if (action.scope === "global") {
            return issue.subjectId !== null;
          }
          if (!action.scope && !action.subjectId) {
            return false;
          }
          return false;
        }),
      };
    case "set-stream-health":
      return {
        ...state,
        streamHealthByJobId: {
          ...state.streamHealthByJobId,
          [action.jobId]: updateStreamHealth(state.streamHealthByJobId[action.jobId] ?? createIdleStreamHealth(), action.state, action.patch),
        },
      };
    case "set-selected-inspector-tab":
      return { ...state, selectedInspectorTab: action.tab };
    case "set-selected-artifact-kind":
      return {
        ...state,
        selectedArtifactKind: action.kind,
        selectedInspectorTab: action.kind ? "artifacts" : state.selectedInspectorTab,
      };
    case "set-composer-text":
      return { ...state, composerText: action.text };
    case "set-pending":
      return {
        ...state,
        pending: {
          ...state.pending,
          [action.key]: action.pending,
        },
      };
    case "dismiss-diagnostic-issue":
      return {
        ...state,
        dismissedDiagnosticIds: state.dismissedDiagnosticIds.includes(action.issueId)
          ? state.dismissedDiagnosticIds
          : [...state.dismissedDiagnosticIds, action.issueId],
      };
    default:
      return state;
  }
}
