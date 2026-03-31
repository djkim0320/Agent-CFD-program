import { useMemo } from "react";
import { useShell } from "../../store/ShellProvider";
import { formatTimestamp, getReportJobs } from "../../store/selectors";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

export function ReportsView() {
  const { state, actions } = useShell();
  const reports = useMemo(() => getReportJobs(state), [state]);

  if (reports.length === 0) {
    return <EmptyState title="No reports yet" body="Completed sessions with generated report or summary artifacts will appear here." />;
  }

  return (
    <div className="thread-block">
      <div className="thread-block__header">
        <div>
          <span className="thread-block__eyebrow">Reports</span>
          <h2>Generated artifacts</h2>
        </div>
      </div>
      <div className="report-list">
        {reports.map((job) => (
          <button key={job.id} type="button" className="session-row" onClick={() => actions.selectJob(job.id)}>
            <div className="session-row__top">
              <strong>{job.source_file_name}</strong>
              <StatusBadge label={job.status} tone={job.status === "completed" ? "good" : "neutral"} />
            </div>
            <div className="session-row__meta">
              <span>{job.selected_solver}</span>
              <span>{formatTimestamp(job.updated_at)}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
