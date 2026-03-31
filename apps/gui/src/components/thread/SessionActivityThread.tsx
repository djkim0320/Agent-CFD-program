import { useShell } from "../../store/ShellProvider";
import { describeJobAiReviewState, describeJobEvent, formatTimestamp, getSelectedJob, getSelectedJobEvents, selectSessionNotes } from "../../store/selectors";
import { EmptySelectionState } from "./EmptySelectionState";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

export function SessionActivityThread() {
  const { state, actions } = useShell();
  const selectedJob = getSelectedJob(state);
  const events = getSelectedJobEvents(state);
  const sessionNotes = selectSessionNotes(state);
  const jobAiReviewState = describeJobAiReviewState(selectedJob);
  const isRefreshBusy = state.pending.refresh;
  const isCancelBusy = state.pending.cancel;

  if (!selectedJob) {
    return <EmptySelectionState title="No persistent session selected" body="Choose a recent session or approve the current snapshot to create one." />;
  }

  return (
    <section className="thread-block">
      <div className="thread-block__header">
        <div>
          <span className="thread-block__eyebrow">Session thread</span>
          <h2>{selectedJob.source_file_name}</h2>
        </div>
        <div className="thread-block__actions">
          <button type="button" className="secondary-btn" onClick={() => void actions.refreshSelectedJob()} disabled={isRefreshBusy}>
            Refresh
          </button>
          <button
            type="button"
            className="secondary-btn"
            onClick={() => void actions.cancelSelectedJob()}
            disabled={isCancelBusy || selectedJob.status === "completed" || selectedJob.status === "cancelled"}
          >
            Cancel
          </button>
        </div>
      </div>

      <div className="thread-card">
        <div className="thread-card__meta">
          <StatusBadge
            label={selectedJob.status}
            tone={selectedJob.status === "completed" ? "good" : selectedJob.status === "failed" ? "danger" : "warning"}
          />
          <StatusBadge label={selectedJob.selected_solver} />
          <StatusBadge label={jobAiReviewState.label} tone={jobAiReviewState.tone} />
        </div>
        <h3>Run timeline</h3>
        <div className="summary-grid">
          <div>
            <span>Job ID</span>
            <strong>{selectedJob.id}</strong>
          </div>
          <div>
            <span>Updated</span>
            <strong>{formatTimestamp(selectedJob.updated_at)}</strong>
          </div>
          <div>
            <span>Progress</span>
            <strong>{selectedJob.progress}%</strong>
          </div>
          <div>
            <span>Solver</span>
            <strong>{selectedJob.selected_solver}</strong>
          </div>
        </div>
      </div>

      <div className="event-list">
        {events.length === 0 ? (
          <EmptyState title="No events yet" body="The worker timeline will stream here as the selected session runs." />
        ) : (
          events.map((event) => {
            const summary = describeJobEvent(event);
            return (
              <article key={`${event.seq}-${event.id}`} className="event-row">
                <div className="event-row__meta">
                  <span>{summary.label}</span>
                  <small>{formatTimestamp(event.created_at)}</small>
                </div>
                <strong>{summary.detail}</strong>
              </article>
            );
          })
        )}
      </div>

      {sessionNotes.length > 0 ? (
        <div className="note-stack">
          {sessionNotes.map((note) => (
            <article key={note.id} className="note-card">
              <span>Composer note</span>
              <p>{note.text}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}
