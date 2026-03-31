import { startTransition, useCallback, useEffect, useRef, type Dispatch } from "react";
import { getJob, listJobs } from "../lib/api";
import type { JobSummaryResponse } from "../lib/types";
import type { DiagnosticIssueInput } from "./diagnostics";
import type { ShellAction } from "./shellTypes";

interface UseSessionQueriesArgs {
  dispatch: Dispatch<ShellAction>;
  reportIssue: (input: DiagnosticIssueInput) => void;
}

export function useSessionQueries({ dispatch, reportIssue }: UseSessionQueriesArgs) {
  const listRefreshTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (listRefreshTimerRef.current !== null) {
        window.clearTimeout(listRefreshTimerRef.current);
      }
    };
  }, []);

  const refreshJobList = useCallback(
    async (debounced = false) => {
      const execute = async () => {
        try {
          const jobs = await listJobs();
          startTransition(() => {
            dispatch({ type: "ingest-jobs", jobs, receivedAt: new Date().toISOString() });
          });
        } catch (error) {
          reportIssue({
            scope: "global",
            code: error instanceof Error ? error.name : "JOB_LIST_UNAVAILABLE",
            title: "Session list unavailable",
            detail: error instanceof Error ? error.message : "The session list could not be loaded.",
            severity: "error",
            raw: error,
          });
        }
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
    },
    [dispatch, reportIssue],
  );

  const refreshJobById = useCallback(
    async (jobId: string): Promise<JobSummaryResponse | null> => {
      try {
        const job = await getJob(jobId);
        startTransition(() => {
          dispatch({ type: "upsert-job", job, updatedAt: new Date().toISOString() });
        });
        return job;
      } catch (error) {
        reportIssue({
          scope: "runtime",
          subjectId: jobId,
          code: error instanceof Error ? error.name : "JOB_REFRESH_FAILED",
          title: "Selected session unavailable",
          detail: error instanceof Error ? error.message : "The selected session could not be loaded.",
          severity: "error",
          raw: error,
        });
        return null;
      }
    },
    [dispatch, reportIssue],
  );

  return { refreshJobList, refreshJobById };
}
