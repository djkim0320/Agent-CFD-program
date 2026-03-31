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

    dispatch({ type: "set-pending", key: "composer", pending: true });
    dispatch({ type: "set-composer-text", text: "" });

    try {
      if (!text.startsWith("/")) {
        dispatch({
          type: "append-note",
          scope: state.selectedJobId ? "job" : "draft",
          text,
          createdAt: new Date().toISOString(),
        });
        return;
      }

      const [rawCommand] = text.slice(1).trim().split(/\s+/, 1);
      const command = rawCommand?.toLowerCase() ?? "";

      if (command === "preflight") {
        await runPreflight();
        return;
      }
      if (command === "approve" || command === "run") {
        await approveCurrentDraft();
        return;
      }
      if (command === "log") {
        dispatch({ type: "set-selected-inspector-tab", tab: "artifacts" });
        dispatch({ type: "set-selected-artifact-kind", kind: "solver_log" });
        return;
      }
      if (command === "diagnostics" || command === "diagnostic") {
        dispatch({ type: "set-selected-inspector-tab", tab: "diagnostics" });
        return;
      }
      if (command === "settings" || command === "runtime") {
        dispatch({ type: "set-route-pane", pane: "settings" });
        dispatch({ type: "set-selected-inspector-tab", tab: "environment" });
        return;
      }
      if (command === "refresh") {
        await refreshSelectedJob();
        return;
      }

      reportIssue({
        scope: "global",
        subjectId: state.selectedJobId ?? "draft",
        code: "COMPOSER_COMMAND_UNRECOGNIZED",
        title: "Composer command rejected",
        detail: `The command "${text}" is not recognized by the current shell.`,
        severity: "warning",
        nextAction: "Use /preflight, /approve, /refresh, /diagnostics, /log, or enter plain text to save a note.",
        raw: { command: text },
      });
    } finally {
      dispatch({ type: "set-pending", key: "composer", pending: false });
    }
  }, [approveCurrentDraft, dispatch, refreshSelectedJob, reportIssue, runPreflight, state.composerText, state.selectedJobId]);
}
