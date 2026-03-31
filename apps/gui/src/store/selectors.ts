import type {
  DiagnosticIssue,
  InstallStatusResponse,
  JobArtifact,
  JobEventRecord,
  JobSummaryResponse,
  NormalizationSummary,
  PreflightResponse,
  IssueRecord,
  StreamHealth,
} from "../lib/types";
import type { SessionRecord, ShellState } from "./shellTypes";

type BadgeTone = "neutral" | "good" | "warning" | "danger";

export interface DisplayStatus {
  label: string;
  tone: BadgeTone;
  detail: string;
}

export interface SummaryRow {
  label: string;
  value: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const SEVERITY_WEIGHT: Record<DiagnosticIssue["severity"], number> = {
  error: 3,
  warning: 2,
  info: 1,
};

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

export function describeDraftExecutionState(preflight: PreflightResponse | null): DisplayStatus {
  if (!preflight) {
    return {
      label: "Draft",
      tone: "neutral",
      detail: "Generate a preflight snapshot to determine execution readiness.",
    };
  }
  if (preflight.runtime_blockers.length > 0) {
    return {
      label: "Blocked",
      tone: "danger",
      detail: preflight.runtime_blockers[0] ?? "This snapshot is blocked for execution.",
    };
  }
  if (preflight.execution_mode === "scaffold") {
    return {
      label: "Deferred",
      tone: "warning",
      detail: "This snapshot is not executable in the current real-path scope.",
    };
  }
  return {
    label: "Ready",
    tone: "good",
    detail: "This snapshot can be approved for real execution.",
  };
}

export function describeAiReviewState(preflight: PreflightResponse | null): DisplayStatus {
  if (!preflight) {
    return {
      label: "Draft",
      tone: "neutral",
      detail: "No preflight snapshot has been generated yet.",
    };
  }
  const aiState = preflight.ai_review_status ?? preflight.ai_assist_mode;
  const aiReason = preflight.ai_review_reason?.trim();
  if (aiState === "disabled") {
    return {
      label: "AI advisory disabled",
      tone: "neutral",
      detail: aiReason || "The advisory path is intentionally disabled for this session.",
    };
  }
  if (aiState === "unavailable") {
    return {
      label: "AI review unavailable",
      tone: "warning",
      detail: aiReason || "The deterministic preflight completed, but AI advisory is unavailable.",
    };
  }
  if (aiState === "failed") {
    return {
      label: "AI review failed",
      tone: "danger",
      detail: aiReason || "The deterministic preflight completed, but the advisory response failed validation.",
    };
  }
  return {
    label: "AI review ready",
    tone: "good",
    detail: "Remote advisory support returned a structured preflight result.",
  };
}

export function describeJobAiReviewState(job: JobSummaryResponse | null): DisplayStatus {
  if (!job) {
    return {
      label: "No session selected",
      tone: "neutral",
      detail: "Select a session to inspect advisory status.",
    };
  }
  const aiState = job.ai_review_status ?? job.ai_assist_mode;
  const aiReason = job.ai_review_reason?.trim();
  if (aiState === "disabled") {
    return {
      label: "AI advisory disabled",
      tone: "neutral",
      detail: aiReason || "The advisory path is intentionally disabled for this session.",
    };
  }
  if (aiState === "unavailable") {
    return {
      label: "AI review unavailable",
      tone: "warning",
      detail: aiReason || "The deterministic path is available, but AI advisory is unavailable.",
    };
  }
  if (aiState === "failed") {
    return {
      label: "AI review failed",
      tone: "danger",
      detail: aiReason || "The deterministic path completed, but the advisory response failed.",
    };
  }
  return {
    label: "AI review ready",
    tone: "good",
    detail: "Remote advisory support returned a structured review.",
  };
}

export function describeProviderState(connectionStatus: ShellState["connectionStatus"]): DisplayStatus {
  if (!connectionStatus) {
    return {
      label: "Unavailable",
      tone: "warning",
      detail: "The provider status has not been loaded yet.",
    };
  }
  if (connectionStatus.connected && connectionStatus.provider_ready) {
    return {
      label: "Ready",
      tone: "good",
      detail: connectionStatus.warnings.length > 0 ? connectionStatus.warnings.join(", ") : "Provider readiness checks completed.",
    };
  }
  return {
    label: "Unavailable",
    tone: "warning",
    detail: connectionStatus.warnings.length > 0 ? connectionStatus.warnings.join(", ") : "Provider readiness checks reported an unavailable state.",
  };
}

export function describeRuntimeState(installStatus: InstallStatusResponse | null): DisplayStatus {
  if (!installStatus) {
    return {
      label: "Unavailable",
      tone: "warning",
      detail: "Local runtime checks have not completed yet.",
    };
  }
  const ready = installStatus.docker_ok && installStatus.gmsh_ok && installStatus.su2_image_ok && installStatus.workspace_ok;
  return {
    label: ready ? "Ready" : "Blocked",
    tone: ready ? "good" : "warning",
    detail: installStatus.install_warnings.length > 0 ? installStatus.install_warnings.join(", ") : ready ? "Local runtime checks completed." : "One or more local runtime checks still need attention.",
  };
}

function sortDiagnostics(issues: DiagnosticIssue[]): DiagnosticIssue[] {
  return [...issues].sort((left, right) => {
    const severityDelta = SEVERITY_WEIGHT[right.severity] - SEVERITY_WEIGHT[left.severity];
    if (severityDelta !== 0) {
      return severityDelta;
    }
    return right.createdAt.localeCompare(left.createdAt);
  });
}

function getVisibleDiagnostics(state: ShellState): DiagnosticIssue[] {
  return state.diagnosticIssues.filter((issue) => !state.dismissedDiagnosticIds.includes(issue.id));
}

export function getAllDiagnostics(state: ShellState): DiagnosticIssue[] {
  return sortDiagnostics(getVisibleDiagnostics(state));
}

export function getCurrentContextDiagnostics(state: ShellState): DiagnosticIssue[] {
  const visible = getVisibleDiagnostics(state);
  const currentSubject = state.selectedJobId ?? "draft";
  return sortDiagnostics(visible.filter((issue) => issue.subjectId === currentSubject));
}

export function getGlobalDiagnostics(state: ShellState): DiagnosticIssue[] {
  return sortDiagnostics(getVisibleDiagnostics(state).filter((issue) => issue.subjectId === null));
}

export function getPrimaryDiagnosticIssue(state: ShellState): DiagnosticIssue | null {
  const contextIssues = getCurrentContextDiagnostics(state);
  if (contextIssues.length > 0) {
    return contextIssues[0];
  }
  const globalIssues = getGlobalDiagnostics(state);
  return globalIssues.length > 0 ? globalIssues[0] : null;
}

export function getDiagnosticsForContext(state: ShellState): DiagnosticIssue[] {
  return getCurrentContextDiagnostics(state);
}

export function getArtifactByKind(job: JobSummaryResponse | null, kind: string | null): JobArtifact | null {
  if (!job || !kind) {
    return null;
  }
  return job.artifacts.find((artifact) => artifact.kind === kind) ?? null;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Not available";
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
  return "Not available";
}

function stringifyValue(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (Array.isArray(value)) {
    const joined = value
      .map((item) => stringifyValue(item))
      .filter((item): item is string => Boolean(item));
    return joined.length > 0 ? joined.join(", ") : null;
  }
  return null;
}

function maybeRow(label: string, value: unknown): SummaryRow | null {
  const rendered = stringifyValue(value);
  if (!rendered) {
    return null;
  }
  return { label, value: rendered };
}

export function summarizeNormalizationSummary(summary: NormalizationSummary | Record<string, unknown> | null | undefined): SummaryRow[] {
  if (!summary) {
    return [];
  }
  const summaryRecord = summary as Record<string, unknown>;
  const rows = [
    maybeRow("Canonical unit", summaryRecord.canonical_unit ?? summaryRecord.normalized_unit ?? summaryRecord.unit),
    maybeRow("Declared unit", summaryRecord.declared_unit),
    maybeRow("Scale factor", summaryRecord.scale_factor_to_meter ?? summaryRecord.applied_scale_factor ?? summaryRecord.scale_factor),
    maybeRow("Forward axis", summaryRecord.forward_axis),
    maybeRow("Up axis", summaryRecord.up_axis),
    maybeRow("Axis mapping", summaryRecord.axis_mapping),
    maybeRow("Source bbox", summaryRecord.source_bbox),
    maybeRow("Normalized bbox", summaryRecord.normalized_bbox),
    maybeRow("Geometry kind", summaryRecord.geometry_kind),
    maybeRow("Watertight", summaryRecord.watertight),
    maybeRow("Repairability", summaryRecord.repairability),
  ];
  return rows.filter((row): row is SummaryRow => row !== null);
}

function summarizeIssueRecords(details: IssueRecord[] | null | undefined): SummaryRow[] {
  if (!details || details.length === 0) {
    return [];
  }
  return details.map((detail) => ({
    label: detail.code,
    value: detail.guidance ? `${detail.message} ${detail.guidance}` : detail.message,
  }));
}

export function summarizeRuntimeBlockerDetails(
  source: Pick<PreflightResponse, "runtime_blocker_details"> | Pick<JobSummaryResponse, "runtime_blocker_details"> | null,
): SummaryRow[] {
  return summarizeIssueRecords(source?.runtime_blocker_details);
}

export function getArtifactDisplayName(artifact: JobArtifact): string {
  switch (artifact.kind) {
    case "report_html":
      return "HTML report";
    case "summary":
      return "Summary payload";
    case "viewer_bundle":
      return "Viewer bundle";
    case "case_bundle":
      return "Case bundle";
    case "solver_log":
      return "Solver log";
    case "mesh_log":
      return "Mesh log";
    case "residual_history":
      return "Residual history";
    case "coefficients":
      return "Coefficients";
    default:
      return artifact.kind.replace(/_/g, " ");
  }
}

export function describeJobEvent(event: JobEventRecord): DisplayStatus {
  const payload = event.payload as Record<string, unknown>;
  const message = stringifyValue(payload.message);
  const detail = message ?? stringifyValue(payload.detail) ?? stringifyValue(payload.phase) ?? stringifyValue(payload.status) ?? "Event received.";

  switch (event.event_type) {
    case "job.status":
      return {
        label: "Job status updated",
        tone:
          payload.status === "completed"
            ? "good"
            : payload.status === "failed" || payload.status === "cancelled"
              ? "danger"
              : "warning",
        detail:
          message ??
          `${stringifyValue(payload.status) ?? "status"}${typeof payload.progress === "number" ? ` (${payload.progress}%)` : ""}`,
      };
    case "preflight.started":
      return { label: "Preflight started", tone: "neutral", detail };
    case "preflight.completed":
      return { label: "Preflight completed", tone: "good", detail };
    case "approval.required":
      return { label: "Approval required", tone: "warning", detail };
    case "subagent.started":
      return { label: "Advisory review started", tone: "neutral", detail };
    case "subagent.completed":
      return { label: "Advisory review completed", tone: "good", detail };
    case "tool.started":
      return { label: "Tool started", tone: "neutral", detail };
    case "tool.progress":
      return { label: "Tool progress", tone: "neutral", detail };
    case "tool.completed":
      return { label: "Tool completed", tone: "good", detail };
    case "solver.stdout":
      return { label: "Solver log", tone: "neutral", detail };
    case "solver.metrics":
      return {
        label: "Solver metrics updated",
        tone: "good",
        detail:
          typeof payload.residual_history_points === "number"
            ? `${payload.residual_history_points} residual points are now available.`
            : `Updated metrics: ${Object.keys((payload.metrics as Record<string, unknown>) ?? {}).join(", ") || "coefficients"}.`,
      };
    case "artifact.ready":
      return {
        label: "Artifact ready",
        tone: "good",
        detail:
          isRecord(payload.artifact) && typeof payload.artifact.kind === "string"
            ? `${getArtifactDisplayName(payload.artifact as unknown as JobArtifact)} published.`
            : detail,
      };
    case "report.ready":
      return {
        label: "Report ready",
        tone: "good",
        detail: stringifyValue(payload.report_path) ? "Report and summary paths are now available." : detail,
      };
    case "job.completed":
      return { label: "Job completed", tone: "good", detail };
    case "job.failed":
      return { label: "Job failed", tone: "danger", detail };
    case "job.cancelled":
      return { label: "Job cancelled", tone: "warning", detail };
    default:
      return { label: event.event_type, tone: "neutral", detail };
  }
}
