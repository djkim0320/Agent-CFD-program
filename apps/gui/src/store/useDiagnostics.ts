import { useCallback, type Dispatch } from "react";
import { formatIssueNotice, createDiagnosticIssue } from "./diagnostics";
import type { DiagnosticIssue, DiagnosticScope, DiagnosticSeverity, StreamHealth, StreamHealthState } from "../lib/types";
import type { ShellAction } from "./shellTypes";

export function useDiagnostics(dispatch: Dispatch<ShellAction>) {
  const reportIssue = useCallback(
    (input: {
      scope: DiagnosticScope;
      code: string;
      title: string;
      detail: string;
      severity: DiagnosticSeverity;
      subjectId?: string | null;
      impact?: string | null;
      nextAction?: string | null;
      raw?: unknown;
      showNotice?: boolean;
    }): DiagnosticIssue => {
      const issue = createDiagnosticIssue(input);
      dispatch({ type: "append-diagnostic-issue", issue });
      if (input.showNotice !== false) {
        dispatch({ type: "set-notice", notice: formatIssueNotice(issue) });
      }
      return issue;
    },
    [dispatch],
  );

  const setStreamHealth = useCallback(
    (jobId: string, state: StreamHealthState, patch?: Partial<StreamHealth>) => {
      dispatch({ type: "set-stream-health", jobId, state, patch });
    },
    [dispatch],
  );

  const clearDiagnostics = useCallback(() => {
    dispatch({ type: "clear-diagnostics" });
  }, [dispatch]);

  return { reportIssue, setStreamHealth, clearDiagnostics };
}
