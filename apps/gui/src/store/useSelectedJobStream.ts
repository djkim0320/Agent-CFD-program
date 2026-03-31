import { useEffect, type Dispatch } from "react";
import {
  decodeArtifactReadyEventPayload,
  decodeJobStatusEventPayload,
  decodeReportReadyEventPayload,
  decodeSolverMetricsEventPayload,
  loadJobEvents,
  subscribeJobEvents,
  type JobEventType,
} from "../lib/api";
import type { JobEventRecord, JobSummaryResponse, StreamHealth } from "../lib/types";
import type { DiagnosticIssueInput } from "./diagnostics";
import type { ShellAction } from "./shellTypes";

const TERMINAL_JOB_EVENTS: Set<JobEventType> = new Set(["job.completed", "job.failed", "job.cancelled"]);

interface UseSelectedJobStreamArgs {
  selectedJobId: string | null;
  dispatch: Dispatch<ShellAction>;
  refreshJobById: (jobId: string) => Promise<JobSummaryResponse | null>;
  refreshJobList: (debounced?: boolean) => Promise<void>;
  reportIssue: (input: DiagnosticIssueInput) => void;
  setStreamHealth: (jobId: string, state: StreamHealth["state"], patch?: Partial<StreamHealth>) => void;
}

function reportDecodeFailure(jobId: string, event: JobEventRecord, error: unknown, reportIssue: (input: DiagnosticIssueInput) => void) {
  reportIssue({
    scope: "decode",
    subjectId: jobId,
    code: error instanceof Error ? error.name : "JOB_EVENT_PATCH_FAILED",
    title: "Session event could not be merged",
    detail: error instanceof Error ? error.message : "A live session event payload could not be decoded.",
    severity: "warning",
    raw: { event_type: event.event_type, payload: event.payload },
  });
}

function applyEventPatch(jobId: string, event: JobEventRecord, dispatch: Dispatch<ShellAction>, reportIssue: (input: DiagnosticIssueInput) => void) {
  const path = `/jobs/${jobId}/events/${event.event_type}`;

  try {
    switch (event.event_type) {
      case "job.status": {
        const payload = decodeJobStatusEventPayload(event.payload, path);
        dispatch({
          type: "merge-job-status",
          jobId,
          status: payload.status,
          progress: payload.progress ?? undefined,
          error: payload.status === "failed" ? payload.message ?? undefined : undefined,
          updatedAt: event.created_at,
        });
        return;
      }
      case "solver.metrics": {
        const payload = decodeSolverMetricsEventPayload(event.payload, path);
        dispatch({
          type: "merge-job-metrics",
          jobId,
          metrics: payload.metrics,
          updatedAt: event.created_at,
        });
        return;
      }
      case "artifact.ready": {
        const payload = decodeArtifactReadyEventPayload(event.payload, path);
        dispatch({
          type: "append-job-artifact",
          jobId,
          artifact: payload.artifact,
          updatedAt: event.created_at,
        });
        return;
      }
      case "report.ready":
        decodeReportReadyEventPayload(event.payload, path);
        return;
      case "job.completed":
        dispatch({
          type: "merge-job-status",
          jobId,
          status: "completed",
          progress: 100,
          updatedAt: event.created_at,
        });
        return;
      case "job.failed": {
        const payload = decodeJobStatusEventPayload(event.payload, path);
        dispatch({
          type: "merge-job-status",
          jobId,
          status: "failed",
          progress: payload.progress ?? undefined,
          error: payload.message ?? "The selected session failed.",
          updatedAt: event.created_at,
        });
        return;
      }
      case "job.cancelled":
        dispatch({
          type: "merge-job-status",
          jobId,
          status: "cancelled",
          updatedAt: event.created_at,
        });
        return;
      default:
        return;
    }
  } catch (error) {
    reportDecodeFailure(jobId, event, error, reportIssue);
  }
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
    let eventCount = 0;
    setStreamHealth(jobId, "connecting", { eventCount: 0, lastError: null });

    void loadJobEvents(jobId)
      .then((events) => {
        if (cancelled) {
          return;
        }
        eventCount = Math.max(eventCount, events.length);
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
        eventCount += 1;
        setStreamHealth(jobId, "open", { lastEventAt: event.created_at, eventCount, lastError: null });
        dispatch({ type: "append-event", jobId, event });
        applyEventPatch(jobId, event, dispatch, reportIssue);
        if (TERMINAL_JOB_EVENTS.has(event.event_type)) {
          void refreshJobById(jobId);
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
