import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";
import {
  approveJob,
  cancelJob,
  createJobFromPreflight,
  getJob,
  listJobs,
  loadConnectionStatus,
  loadInstallStatus,
  loadJobEvents,
  submitPreflight,
  subscribeJobEvents,
  type JobEventType,
} from "../lib/api";
import type { AnalysisFormState } from "../lib/types";
import { createInitialDraft, createInitialShellState, shellReducer } from "./shellReducer";
import { canApprovePreflight, getSelectedJob } from "./selectors";
import type { InspectorTab, RoutePane, ShellState } from "./shellTypes";

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

const REFRESH_JOB_EVENTS: Set<JobEventType> = new Set([
  "job.status",
  "solver.metrics",
  "artifact.ready",
  "report.ready",
  "job.completed",
  "job.failed",
  "job.cancelled",
]);

const REFRESH_LIST_EVENTS: Set<JobEventType> = new Set([
  "job.status",
  "job.completed",
  "job.failed",
  "job.cancelled",
]);

function parseRouteFromLocation() {
  const params = new URLSearchParams(window.location.search);
  const pane = params.get("pane");
  const jobId = params.get("job");
  const inspector = params.get("inspector");
  return {
    pane: pane === "reports" || pane === "settings" ? pane : "workspace",
    jobId,
    inspector:
      inspector === "run" || inspector === "artifacts" || inspector === "environment"
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
  const listRefreshTimerRef = useRef<number | null>(null);
  const selectedJob = useMemo(() => getSelectedJob(state), [state]);

  const setNotice = useCallback((message: string | null) => {
    dispatch({ type: "set-notice", notice: message });
  }, []);

  useEffect(() => {
    return () => {
      if (listRefreshTimerRef.current !== null) {
        window.clearTimeout(listRefreshTimerRef.current);
      }
    };
  }, []);

  const refreshJobList = useCallback(async (debounced = false) => {
    const execute = async () => {
      const jobs = await listJobs();
      startTransition(() => {
        dispatch({ type: "ingest-jobs", jobs, receivedAt: new Date().toISOString() });
      });
    };

    if (!debounced) {
      await execute();
      return;
    }
    if (listRefreshTimerRef.current !== null) {
      window.clearTimeout(listRefreshTimerRef.current);
    }
    listRefreshTimerRef.current = window.setTimeout(() => {
      void execute();
    }, 1200);
  }, []);

  const refreshJobById = useCallback(async (jobId: string) => {
    const job = await getJob(jobId);
    startTransition(() => {
      dispatch({ type: "upsert-job", job, updatedAt: new Date().toISOString() });
    });
    return job;
  }, []);

  useEffect(() => {
    let cancelled = false;
    void loadInstallStatus()
      .then((status) => {
        if (!cancelled) {
          dispatch({ type: "set-install-status", status });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setNotice(error instanceof Error ? error.message : "Install status is unavailable.");
        }
      });
    void refreshJobList();
    return () => {
      cancelled = true;
    };
  }, [refreshJobList, setNotice]);

  useEffect(() => {
    let cancelled = false;
    void loadConnectionStatus(state.connectionMode)
      .then((status) => {
        if (!cancelled) {
          dispatch({ type: "set-connection-status", status });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setNotice(error instanceof Error ? error.message : "Connection status is unavailable.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [setNotice, state.connectionMode]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    params.set("pane", state.routePane);
    if (state.selectedJobId) {
      params.set("job", state.selectedJobId);
    } else {
      params.delete("job");
    }
    params.set("inspector", state.selectedInspectorTab);
    const query = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
  }, [state.routePane, state.selectedInspectorTab, state.selectedJobId]);

  useEffect(() => {
    const onPopState = () => {
      const route = parseRouteFromLocation();
      dispatch({ type: "set-route-pane", pane: route.pane });
      dispatch({ type: "select-job", jobId: route.jobId });
      dispatch({ type: "set-selected-inspector-tab", tab: route.inspector });
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const jobId = state.selectedJobId;
    if (!jobId) {
      return;
    }

    let cancelled = false;
    void loadJobEvents(jobId)
      .then((events) => {
        if (!cancelled) {
          dispatch({ type: "set-events", jobId, events });
        }
      })
      .catch(() => undefined);

    void refreshJobById(jobId).catch(() => undefined);
    const unsubscribe = subscribeJobEvents(jobId, (event) => {
      dispatch({ type: "append-event", jobId, event });
      if (REFRESH_JOB_EVENTS.has(event.event_type)) {
        void refreshJobById(jobId).catch(() => undefined);
      }
      if (REFRESH_LIST_EVENTS.has(event.event_type)) {
        void refreshJobList(true).catch(() => undefined);
      }
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [refreshJobById, refreshJobList, state.selectedJobId]);

  const actions = useMemo<ShellContextValue["actions"]>(() => {
    const runPreflight = async () => {
      if (!state.draft.geometryFile) {
        setNotice("Pick a geometry file before generating a preflight snapshot.");
        return;
      }
      dispatch({ type: "set-busy", busy: true });
      dispatch({ type: "set-notice", notice: null });
      try {
        const preflight = await submitPreflight(state.draft, state.connectionMode);
        dispatch({ type: "set-preflight", preflight });
        dispatch({
          type: "append-note",
          scope: "draft",
          text: `Preflight generated with ${preflight.selected_solver} (${preflight.execution_mode}).`,
          createdAt: new Date().toISOString(),
        });
        dispatch({ type: "set-selected-inspector-tab", tab: "snapshot" });
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "Preflight request failed.");
      } finally {
        dispatch({ type: "set-busy", busy: false });
      }
    };

    const approveCurrentDraft = async () => {
      if (!state.draftPreflight) {
        setNotice("Generate a preflight snapshot first.");
        return;
      }
      if (!canApprovePreflight(state.draftPreflight)) {
        setNotice("This snapshot is not approved for real execution.");
        return;
      }
      dispatch({ type: "set-busy", busy: true });
      dispatch({ type: "set-notice", notice: null });
      try {
        const draftJob = await createJobFromPreflight(state.draftPreflight.preflight_id);
        dispatch({ type: "upsert-job", job: draftJob, updatedAt: new Date().toISOString() });
        dispatch({ type: "select-job", jobId: draftJob.id });
        const approved = await approveJob(draftJob.id);
        dispatch({ type: "upsert-job", job: approved, updatedAt: new Date().toISOString() });
        const history = await loadJobEvents(draftJob.id);
        dispatch({ type: "set-events", jobId: draftJob.id, events: history });
        await refreshJobList();
        dispatch({
          type: "append-note",
          scope: "job",
          text: "Snapshot approved and queued for execution.",
          createdAt: new Date().toISOString(),
        });
        dispatch({ type: "set-selected-inspector-tab", tab: "run" });
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "Failed to create or approve the job.");
      } finally {
        dispatch({ type: "set-busy", busy: false });
      }
    };

    const refreshSelectedJob = async () => {
      if (!state.selectedJobId) {
        return;
      }
      dispatch({ type: "set-busy", busy: true });
      try {
        const job = await refreshJobById(state.selectedJobId);
        const events = await loadJobEvents(job.id);
        dispatch({ type: "set-events", jobId: job.id, events });
        await refreshJobList();
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "Unable to refresh the selected job.");
      } finally {
        dispatch({ type: "set-busy", busy: false });
      }
    };

    const cancelSelectedJob = async () => {
      if (!state.selectedJobId) {
        return;
      }
      dispatch({ type: "set-busy", busy: true });
      try {
        const job = await cancelJob(state.selectedJobId);
        dispatch({ type: "upsert-job", job, updatedAt: new Date().toISOString() });
        await refreshJobList();
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "Unable to cancel the selected job.");
      } finally {
        dispatch({ type: "set-busy", busy: false });
      }
    };

    const submitComposer = async () => {
      const text = state.composerText.trim();
      if (!text) {
        return;
      }
      const normalized = text.toLowerCase();
      dispatch({
        type: "append-note",
        scope: selectedJob ? "job" : "draft",
        text,
        createdAt: new Date().toISOString(),
      });
      dispatch({ type: "set-composer-text", text: "" });
      if (normalized.includes("preflight")) {
        await runPreflight();
        return;
      }
      if (normalized.includes("approve") || normalized.includes("run")) {
        await approveCurrentDraft();
        return;
      }
      if (normalized.includes("log")) {
        dispatch({ type: "set-selected-inspector-tab", tab: "artifacts" });
        dispatch({ type: "set-selected-artifact-kind", kind: "solver_log" });
        return;
      }
      if (normalized.includes("settings") || normalized.includes("runtime")) {
        dispatch({ type: "set-route-pane", pane: "settings" });
        dispatch({ type: "set-selected-inspector-tab", tab: "environment" });
      }
    };

    return {
      setRoutePane: (pane) => dispatch({ type: "set-route-pane", pane }),
      setConnectionMode: (mode) => dispatch({ type: "set-connection-mode", mode }),
      setDraftField: (field, value) => dispatch({ type: "set-draft-field", field, value }),
      setDraftSection: (section, value) => dispatch({ type: "set-draft-section", section, value }),
      newAnalysis: () => {
        dispatch({ type: "reset-draft", draft: createInitialDraft() });
        dispatch({ type: "set-composer-text", text: "" });
        dispatch({ type: "set-notice", notice: null });
        dispatch({ type: "set-route-pane", pane: "workspace" });
      },
      runPreflight,
      approveCurrentDraft,
      selectJob: (jobId) => {
        dispatch({ type: "select-job", jobId });
        dispatch({ type: "set-route-pane", pane: "workspace" });
      },
      refreshSelectedJob,
      cancelSelectedJob,
      setInspectorTab: (tab) => dispatch({ type: "set-selected-inspector-tab", tab }),
      setSelectedArtifactKind: (kind) => dispatch({ type: "set-selected-artifact-kind", kind }),
      setComposerText: (text) => dispatch({ type: "set-composer-text", text }),
      submitComposer,
      clearNotice: () => dispatch({ type: "set-notice", notice: null }),
    };
  }, [refreshJobById, refreshJobList, selectedJob, setNotice, state.composerText, state.connectionMode, state.draft, state.draftPreflight, state.selectedJobId]);

  return <ShellContext.Provider value={{ state, actions }}>{children}</ShellContext.Provider>;
}

export function useShell() {
  const context = useContext(ShellContext);
  if (!context) {
    throw new Error("useShell must be used inside ShellProvider");
  }
  return context;
}
