import { useCallback, type Dispatch } from "react";
import { createDiagnosticIssue } from "./diagnostics";
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

  const clearDiagnostics = useCallback((filter?: { scope?: "draft" | "job" | "global"; subjectId?: string | null }) => {
    dispatch({ type: "clear-diagnostics", scope: filter?.scope, subjectId: filter?.subjectId });
  }, [dispatch]);

  return { reportIssue, setStreamHealth, clearDiagnostics };
}
