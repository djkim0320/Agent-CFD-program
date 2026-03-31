import { useCallback, type Dispatch } from "react";
import { approveJob, cancelJob, createJobFromPreflight, loadJobEvents, submitPreflight } from "../lib/api";
import { canApprovePreflight } from "./selectors";
import { createInitialDraft } from "./shellReducer";
import type { DiagnosticIssueInput } from "./diagnostics";
import type { JobSummaryResponse } from "../lib/types";
import type { ShellAction, ShellState } from "./shellTypes";

interface UseSessionMutationsArgs {
  state: ShellState;
  dispatch: Dispatch<ShellAction>;
  refreshJobList: (debounced?: boolean) => Promise<void>;
  refreshJobById: (jobId: string) => Promise<JobSummaryResponse | null>;
  reportIssue: (input: DiagnosticIssueInput) => void;
  clearDiagnostics?: (filter?: { scope?: "draft" | "job" | "global"; subjectId?: string | null }) => void;
}

export function useSessionMutations({
  state,
  dispatch,
  refreshJobList,
  refreshJobById,
  reportIssue,
  clearDiagnostics,
}: UseSessionMutationsArgs) {
  const runPreflight = useCallback(async () => {
    if (!state.draft.geometryFile) {
      reportIssue({
        scope: "preflight",
        subjectId: "draft",
        code: "GEOMETRY_REQUIRED",
        title: "Geometry file required",
        detail: "Choose a geometry file before generating a preflight snapshot.",
        severity: "warning",
        nextAction: "Select a geometry file and try again.",
      });
      return;
    }

    dispatch({ type: "set-pending", key: "preflight", pending: true });

    try {
      const preflight = await submitPreflight(state.draft, state.connectionMode);
      dispatch({ type: "set-preflight", preflight });
      dispatch({
        type: "append-note",
        scope: "draft",
        text: `Preflight generated for ${preflight.selected_solver} (${preflight.execution_mode}).`,
        createdAt: new Date().toISOString(),
      });
      dispatch({ type: "set-selected-inspector-tab", tab: "snapshot" });
    } catch (error) {
      reportIssue({
        scope: "preflight",
        subjectId: "draft",
        code: error instanceof Error ? error.name : "PREFLIGHT_FAILED",
        title: "Preflight blocked",
        detail: error instanceof Error ? error.message : "The preflight request failed.",
        severity: "error",
        raw: error,
      });
    } finally {
      dispatch({ type: "set-pending", key: "preflight", pending: false });
    }
  }, [dispatch, reportIssue, state.connectionMode, state.draft]);

  const approveCurrentDraft = useCallback(async () => {
    if (!state.draftPreflight) {
      reportIssue({
        scope: "preflight",
        subjectId: "draft",
        code: "PREFLIGHT_REQUIRED",
        title: "Preflight snapshot required",
        detail: "Generate a preflight snapshot before creating a persistent job.",
        severity: "warning",
        nextAction: "Generate a preflight snapshot first.",
      });
      return;
    }
    if (!canApprovePreflight(state.draftPreflight)) {
      reportIssue({
        scope: "preflight",
        subjectId: "draft",
        code: "PREFLIGHT_BLOCKED",
        title: "Snapshot blocked",
        detail: "This snapshot cannot be approved for real execution.",
        severity: "warning",
        nextAction: "Review the blockers and regenerate the snapshot if needed.",
      });
      return;
    }

    dispatch({ type: "set-pending", key: "approve", pending: true });

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
      reportIssue({
        scope: "runtime",
        subjectId: state.selectedJobId ?? "draft",
        code: error instanceof Error ? error.name : "APPROVE_FAILED",
        title: "Approval failed",
        detail: error instanceof Error ? error.message : "The job could not be created or approved.",
        severity: "error",
        raw: error,
      });
    } finally {
      dispatch({ type: "set-pending", key: "approve", pending: false });
    }
  }, [dispatch, refreshJobList, reportIssue, state.draftPreflight]);

  const refreshSelectedJob = useCallback(async () => {
    if (!state.selectedJobId) {
      return;
    }

    dispatch({ type: "set-pending", key: "refresh", pending: true });
    try {
      const refreshed = await refreshJobById(state.selectedJobId);
      if (!refreshed) {
        return;
      }
      const history = await loadJobEvents(state.selectedJobId);
      dispatch({ type: "set-events", jobId: state.selectedJobId, events: history });
      await refreshJobList();
    } catch (error) {
      reportIssue({
        scope: "runtime",
        subjectId: state.selectedJobId,
        code: error instanceof Error ? error.name : "JOB_REFRESH_FAILED",
        title: "Session refresh failed",
        detail: error instanceof Error ? error.message : "The selected session could not be refreshed.",
        severity: "error",
        raw: error,
      });
    } finally {
      dispatch({ type: "set-pending", key: "refresh", pending: false });
    }
  }, [dispatch, refreshJobById, refreshJobList, reportIssue, state.selectedJobId]);

  const cancelSelectedJob = useCallback(async () => {
    if (!state.selectedJobId) {
      return;
    }

    dispatch({ type: "set-pending", key: "cancel", pending: true });
    try {
      const job = await cancelJob(state.selectedJobId);
      dispatch({ type: "upsert-job", job, updatedAt: new Date().toISOString() });
      await refreshJobList();
    } catch (error) {
      reportIssue({
        scope: "runtime",
        subjectId: state.selectedJobId,
        code: error instanceof Error ? error.name : "JOB_CANCEL_FAILED",
        title: "Cancellation failed",
        detail: error instanceof Error ? error.message : "The selected session could not be cancelled.",
        severity: "error",
        raw: error,
      });
    } finally {
      dispatch({ type: "set-pending", key: "cancel", pending: false });
    }
  }, [dispatch, refreshJobList, reportIssue, state.selectedJobId]);

  const newAnalysis = useCallback(() => {
    dispatch({ type: "reset-draft", draft: createInitialDraft() });
    dispatch({ type: "select-job", jobId: null });
    dispatch({ type: "set-composer-text", text: "" });
    clearDiagnostics?.({ scope: "draft" });
    dispatch({ type: "set-route-pane", pane: "workspace" });
  }, [clearDiagnostics, dispatch]);

  const selectJob = useCallback(
    (jobId: string | null) => {
      dispatch({ type: "select-job", jobId });
      dispatch({ type: "set-route-pane", pane: "workspace" });
    },
    [dispatch],
  );

  return {
    runPreflight,
    approveCurrentDraft,
    refreshSelectedJob,
    cancelSelectedJob,
    newAnalysis,
    selectJob,
  };
}
