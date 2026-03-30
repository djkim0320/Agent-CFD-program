import { useCallback, type Dispatch } from "react";
import type { DiagnosticIssueInput } from "./diagnostics";
import type { ShellAction, ShellState } from "./shellTypes";

interface UseComposerActionsArgs {
  state: ShellState;
  dispatch: Dispatch<ShellAction>;
  runPreflight: () => Promise<void>;
  approveCurrentDraft: () => Promise<void>;
  refreshSelectedJob: () => Promise<void>;
  reportIssue: (input: DiagnosticIssueInput) => void;
}

export function useComposerActions({
  state,
  dispatch,
  runPreflight,
  approveCurrentDraft,
  refreshSelectedJob,
  reportIssue,
}: UseComposerActionsArgs) {
  return useCallback(async () => {
    const text = state.composerText.trim();
    if (!text) {
      return;
    }

    const normalized = text.toLowerCase();
    dispatch({
      type: "append-note",
      scope: state.selectedJobId ? "job" : "draft",
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
    if (normalized.includes("diagnostic")) {
      dispatch({ type: "set-selected-inspector-tab", tab: "diagnostics" });
      return;
    }
    if (normalized.includes("settings") || normalized.includes("runtime")) {
      dispatch({ type: "set-route-pane", pane: "settings" });
      dispatch({ type: "set-selected-inspector-tab", tab: "environment" });
      return;
    }
    if (normalized.includes("refresh")) {
      await refreshSelectedJob();
      return;
    }

    reportIssue({
      scope: "global",
      subjectId: state.selectedJobId,
      code: "COMPOSER_COMMAND_UNRECOGNIZED",
      title: "Composer command rejected",
      detail: `The command "${text}" is not recognized by the current shell.`,
      severity: "warning",
      nextAction: 'Use a supported command such as "generate preflight", "approve and run", "show solver log", or "open diagnostics".',
      raw: { command: text },
    });
  }, [approveCurrentDraft, dispatch, refreshSelectedJob, reportIssue, runPreflight, state.composerText, state.selectedJobId]);
}
