import type { JobArtifact, JobEventRecord, JobSummaryResponse, PreflightResponse } from "../lib/types";
import type { SessionRecord, ShellState } from "./shellTypes";

export function getSelectedJob(state: ShellState): JobSummaryResponse | null {
  if (!state.selectedJobId) {
    return null;
  }
  return state.jobsById[state.selectedJobId]?.job ?? null;
}

export function getSelectedJobRecord(state: ShellState): SessionRecord | null {
  if (!state.selectedJobId) {
    return null;
  }
  return state.jobsById[state.selectedJobId] ?? null;
}

export function getSelectedJobEvents(state: ShellState): JobEventRecord[] {
  if (!state.selectedJobId) {
    return [];
  }
  return state.eventsByJobId[state.selectedJobId] ?? [];
}

export function selectDraftNotes(state: ShellState) {
  return state.notesByScope.draft ?? [];
}

export function selectSessionNotes(state: ShellState) {
  if (!state.selectedJobId) {
    return [];
  }
  return state.notesByScope[state.selectedJobId] ?? [];
}

export function getSidebarSessions(state: ShellState): JobSummaryResponse[] {
  return state.jobOrder
    .map((jobId) => state.jobsById[jobId]?.job)
    .filter((job): job is JobSummaryResponse => Boolean(job));
}

export function getReportJobs(state: ShellState): JobSummaryResponse[] {
  return getSidebarSessions(state).filter((job) =>
    job.artifacts.some((artifact) => artifact.kind.includes("report") || artifact.kind.includes("summary")),
  );
}

export function canApprovePreflight(preflight: PreflightResponse | null): boolean {
  return Boolean(preflight && preflight.execution_mode === "real" && preflight.runtime_blockers.length === 0);
}

export function getOverallState(preflight: PreflightResponse | null): string {
  if (!preflight) {
    return "draft";
  }
  if (preflight.runtime_blockers.length > 0) {
    return "blocked";
  }
  if (preflight.execution_mode === "scaffold") {
    return "scaffold";
  }
  if (preflight.ai_assist_mode === "local_fallback") {
    return "ai-fallback";
  }
  return "real";
}

export function getArtifactByKind(job: JobSummaryResponse | null, kind: string | null): JobArtifact | null {
  if (!job || !kind) {
    return null;
  }
  return job.artifacts.find((artifact) => artifact.kind === kind) ?? null;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export function formatMaybeNumber(value: number | string | null | undefined, digits = 3): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toFixed(digits);
  }
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return "—";
}
