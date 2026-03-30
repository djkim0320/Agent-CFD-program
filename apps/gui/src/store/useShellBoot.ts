import { useEffect, type Dispatch } from "react";
import { loadConnectionStatus, loadInstallStatus } from "../lib/api";
import type { ConnectionMode } from "../lib/types";
import type { ShellAction } from "./shellTypes";
import type { DiagnosticIssueInput } from "./diagnostics";

interface UseShellBootArgs {
  connectionMode: ConnectionMode;
  dispatch: Dispatch<ShellAction>;
  refreshJobList: () => Promise<void>;
  reportIssue: (input: DiagnosticIssueInput) => void;
}

export function useShellBoot({ connectionMode, dispatch, refreshJobList, reportIssue }: UseShellBootArgs) {
  useEffect(() => {
    let cancelled = false;

    void loadInstallStatus()
      .then((status) => {
        if (!cancelled) {
          dispatch({ type: "set-install-status", status });
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        reportIssue({
          scope: "runtime",
          code: error instanceof Error ? error.name : "INSTALL_STATUS_UNAVAILABLE",
          title: "Runtime status unavailable",
          detail: error instanceof Error ? error.message : "The local runtime check did not return a valid response.",
          severity: "error",
          raw: error,
        });
      });

    void refreshJobList();

    return () => {
      cancelled = true;
    };
  }, [dispatch, refreshJobList, reportIssue]);

  useEffect(() => {
    let cancelled = false;
    void loadConnectionStatus(connectionMode)
      .then((status) => {
        if (!cancelled) {
          dispatch({ type: "set-connection-status", status });
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        reportIssue({
          scope: "provider",
          code: error instanceof Error ? error.name : "CONNECTION_STATUS_UNAVAILABLE",
          title: "Provider status unavailable",
          detail: error instanceof Error ? error.message : "The provider readiness check did not return a valid response.",
          severity: "error",
          raw: error,
        });
      });

    return () => {
      cancelled = true;
    };
  }, [connectionMode, dispatch, reportIssue]);
}
