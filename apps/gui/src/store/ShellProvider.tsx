import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";
import { createInitialShellState, shellReducer } from "./shellReducer";
import { useComposerActions } from "./useComposerActions";
import { useDiagnostics } from "./useDiagnostics";
import { useRouteSync } from "./useRouteSync";
import { getPrimaryDiagnosticIssue } from "./selectors";
import { useSelectedJobStream } from "./useSelectedJobStream";
import { useSessionQueries } from "./useSessionQueries";
import { useSessionMutations } from "./useSessionMutations";
import { useShellBoot } from "./useShellBoot";
import type { RoutePane, ShellAction, ShellState, InspectorTab } from "./shellTypes";
import type { AnalysisFormState } from "../lib/types";

interface ShellContextValue {
  state: ShellState;
  actions: {
    setRoutePane: (pane: RoutePane) => void;
    setConnectionMode: (mode: ShellState["connectionMode"]) => void;
    setDraftField: (field: keyof AnalysisFormState, value: string | File | null) => void;
    setDraftSection: (section: "frame" | "referenceValues" | "flow", value: Record<string, string>) => void;
    newAnalysis: () => void;
    runPreflight: () => Promise<void>;
    approveCurrentDraft: () => Promise<void>;
    selectJob: (jobId: string | null) => void;
    refreshSelectedJob: () => Promise<void>;
    cancelSelectedJob: () => Promise<void>;
    setInspectorTab: (tab: InspectorTab) => void;
    setSelectedArtifactKind: (kind: string | null) => void;
    setComposerText: (text: string) => void;
    submitComposer: () => Promise<void>;
    clearNotice: () => void;
  };
}

const ShellContext = createContext<ShellContextValue | null>(null);

function parseRouteFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const pane = params.get("pane");
  const jobId = params.get("job");
  const inspector = params.get("inspector");
  return {
    pane: pane === "reports" || pane === "settings" ? pane : "workspace",
    jobId,
    inspector:
      inspector === "run" || inspector === "artifacts" || inspector === "environment" || inspector === "diagnostics"
        ? inspector
        : "snapshot",
  } as const;
}

export function ShellProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(shellReducer, undefined, () => {
    const initial = createInitialShellState();
    if (typeof window === "undefined") {
      return initial;
    }
    const route = parseRouteFromLocation();
    return {
      ...initial,
      routePane: route.pane,
      selectedJobId: route.jobId,
      selectedInspectorTab: route.inspector,
    };
  });

  const { reportIssue, setStreamHealth, clearDiagnostics } = useDiagnostics(dispatch);
  const { refreshJobList, refreshJobById } = useSessionQueries({ dispatch, reportIssue });

  useShellBoot({
    connectionMode: state.connectionMode,
    dispatch,
    refreshJobList,
    reportIssue,
  });

  useRouteSync({
    routePane: state.routePane,
    selectedJobId: state.selectedJobId,
    selectedInspectorTab: state.selectedInspectorTab,
    dispatch,
  });

  useSelectedJobStream({
    selectedJobId: state.selectedJobId,
    dispatch,
    refreshJobById,
    refreshJobList,
    reportIssue,
    setStreamHealth,
  });

  const sessionMutations = useSessionMutations({
    state,
    dispatch,
    refreshJobList,
    refreshJobById,
    reportIssue,
    clearDiagnostics,
  });

  const submitComposer = useComposerActions({
    state,
    dispatch,
    runPreflight: sessionMutations.runPreflight,
    approveCurrentDraft: sessionMutations.approveCurrentDraft,
    refreshSelectedJob: sessionMutations.refreshSelectedJob,
    reportIssue,
  });

  const actions = useMemo<ShellContextValue["actions"]>(
    () => ({
      setRoutePane: (pane) => dispatch({ type: "set-route-pane", pane }),
      setConnectionMode: (mode) => dispatch({ type: "set-connection-mode", mode }),
      setDraftField: (field, value) => dispatch({ type: "set-draft-field", field, value }),
      setDraftSection: (section, value) => dispatch({ type: "set-draft-section", section, value }),
      newAnalysis: sessionMutations.newAnalysis,
      runPreflight: sessionMutations.runPreflight,
      approveCurrentDraft: sessionMutations.approveCurrentDraft,
      selectJob: sessionMutations.selectJob,
      refreshSelectedJob: sessionMutations.refreshSelectedJob,
      cancelSelectedJob: sessionMutations.cancelSelectedJob,
      setInspectorTab: (tab) => dispatch({ type: "set-selected-inspector-tab", tab }),
      setSelectedArtifactKind: (kind) => dispatch({ type: "set-selected-artifact-kind", kind }),
      setComposerText: (text) => dispatch({ type: "set-composer-text", text }),
      submitComposer,
      clearNotice: () => {
        const primaryIssue = getPrimaryDiagnosticIssue(state);
        if (primaryIssue) {
          dispatch({ type: "dismiss-diagnostic-issue", issueId: primaryIssue.id });
        }
      },
    }),
    [dispatch, sessionMutations.approveCurrentDraft, sessionMutations.cancelSelectedJob, sessionMutations.newAnalysis, sessionMutations.refreshSelectedJob, sessionMutations.runPreflight, sessionMutations.selectJob, state, submitComposer],
  );

  return <ShellContext.Provider value={{ state, actions }}>{children}</ShellContext.Provider>;
}

export function useShell() {
  const context = useContext(ShellContext);
  if (!context) {
    throw new Error("useShell must be used inside ShellProvider");
  }
  return context;
}
