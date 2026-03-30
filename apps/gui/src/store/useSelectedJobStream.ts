import { useEffect, type Dispatch } from "react";
import { loadJobEvents, subscribeJobEvents, type JobEventType } from "../lib/api";
import type { JobEventRecord, JobSummaryResponse, StreamHealth } from "../lib/types";
import type { DiagnosticIssueInput } from "./diagnostics";
import type { ShellAction } from "./shellTypes";

const REFRESH_JOB_EVENTS: Set<JobEventType> = new Set([
  "job.status",
  "solver.metrics",
  "artifact.ready",
  "report.ready",
  "job.completed",
  "job.failed",
  "job.cancelled",
]);

const REFRESH_LIST_EVENTS: Set<JobEventType> = new Set(["job.status", "job.completed", "job.failed", "job.cancelled"]);

interface UseSelectedJobStreamArgs {
  selectedJobId: string | null;
  dispatch: Dispatch<ShellAction>;
  refreshJobById: (jobId: string) => Promise<JobSummaryResponse | null>;
  refreshJobList: (debounced?: boolean) => Promise<void>;
  reportIssue: (input: DiagnosticIssueInput) => void;
  setStreamHealth: (jobId: string, state: StreamHealth["state"], patch?: Partial<StreamHealth>) => void;
}

export function useSelectedJobStream({
  selectedJobId,
  dispatch,
  refreshJobById,
  refreshJobList,
  reportIssue,
  setStreamHealth,
}: UseSelectedJobStreamArgs) {
  useEffect(() => {
    const jobId = selectedJobId;
    if (!jobId) {
      return;
    }

    let cancelled = false;
    setStreamHealth(jobId, "connecting", { eventCount: 0, lastError: null });

    void loadJobEvents(jobId)
      .then((events) => {
        if (cancelled) {
          return;
        }
        dispatch({ type: "set-events", jobId, events });
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        reportIssue({
          scope: "stream",
          subjectId: jobId,
          code: error instanceof Error ? error.name : "JOB_HISTORY_DECODE_FAILED",
          title: "Session history unavailable",
          detail: error instanceof Error ? error.message : "The selected session history could not be decoded.",
          severity: "error",
          raw: error,
        });
        setStreamHealth(jobId, "failed", { lastError: error instanceof Error ? error.message : "Session history unavailable" });
      });

    void refreshJobById(jobId);

    const unsubscribe = subscribeJobEvents(
      jobId,
      (event: JobEventRecord) => {
        if (cancelled) {
          return;
        }
        setStreamHealth(jobId, "open", { lastEventAt: event.created_at });
        dispatch({ type: "append-event", jobId, event });
        if (REFRESH_JOB_EVENTS.has(event.event_type)) {
          void refreshJobById(jobId);
        }
        if (REFRESH_LIST_EVENTS.has(event.event_type)) {
          void refreshJobList(true);
        }
      },
      (error) => {
        if (cancelled) {
          return;
        }
        reportIssue({
          scope: "stream",
          subjectId: jobId,
          code: error instanceof Error ? error.name : "JOB_STREAM_FAILED",
          title: "Session stream disconnected",
          detail: error instanceof Error ? error.message : "The live event stream ended unexpectedly.",
          severity: "error",
          raw: error,
        });
        setStreamHealth(jobId, "failed", { lastError: error instanceof Error ? error.message : "Session stream disconnected" });
      },
    );

    return () => {
      cancelled = true;
      unsubscribe();
      setStreamHealth(jobId, "disconnected");
    };
  }, [dispatch, refreshJobById, refreshJobList, reportIssue, selectedJobId, setStreamHealth]);
}
