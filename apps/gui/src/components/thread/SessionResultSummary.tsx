import { useShell } from "../../store/ShellProvider";
import { formatMaybeNumber, getArtifactDisplayName, getSelectedJob } from "../../store/selectors";
import { EmptySelectionState } from "./EmptySelectionState";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

function ArtifactPanel({
  artifacts,
  selectedKind,
  onSelect,
}: {
  artifacts: { kind: string; path: string; sha256?: string | null; created_at?: string | null }[];
  selectedKind: string | null;
  onSelect: (kind: string) => void;
}) {
  if (artifacts.length === 0) {
    return <EmptyState title="Artifacts not ready yet" body="Report, solver log, case bundle, and summary links will appear here after the worker finishes." />;
  }

  return (
    <div className="artifact-panel">
      {artifacts.map((artifact) => (
        <button
          key={`${artifact.kind}-${artifact.path}`}
          type="button"
          className={selectedKind === artifact.kind ? "artifact-row is-active" : "artifact-row"}
          onClick={() => onSelect(artifact.kind)}
        >
          <div>
            <strong>{getArtifactDisplayName(artifact)}</strong>
            <span>{artifact.kind}</span>
          </div>
          <small>{artifact.path}</small>
          {artifact.sha256 ? <small>{artifact.sha256}</small> : null}
        </button>
      ))}
    </div>
  );
}

export function SessionResultSummary() {
  const { state, actions } = useShell();
  const selectedJob = getSelectedJob(state);

  if (!selectedJob) {
    return <EmptySelectionState title="No session results yet" body="Select a persistent session to inspect metrics, residual history, and artifacts." />;
  }

  return (
    <section className="thread-block">
      <div className="thread-block__header">
        <div>
          <span className="thread-block__eyebrow">Results</span>
          <h2>Summary and artifacts</h2>
        </div>
        <StatusBadge label={selectedJob.status} tone={selectedJob.status === "completed" ? "good" : selectedJob.status === "failed" ? "danger" : "warning"} />
      </div>

      <div className="result-grid">
        <div className="detail-card">
          <span>CL</span>
          <strong>{formatMaybeNumber(selectedJob.metrics.CL)}</strong>
          <span>CD</span>
          <strong>{formatMaybeNumber(selectedJob.metrics.CD)}</strong>
          <span>Cm</span>
          <strong>{formatMaybeNumber(selectedJob.metrics.Cm)}</strong>
        </div>
        <div className="detail-card">
          <span>Residual history</span>
          {selectedJob.residual_history.length > 0 ? (
            <div className="residual-list">
              {selectedJob.residual_history.slice(-8).map((point) => (
                <div key={`${point.iteration}-${point.residual}`} className="residual-row">
                  <span>{point.iteration}</span>
                  <strong>{formatMaybeNumber(point.residual, 6)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p>Residual history has not been published yet.</p>
          )}
        </div>
        <div className="detail-card">
          <span>Artifacts</span>
          <ArtifactPanel
            artifacts={selectedJob.artifacts}
            selectedKind={state.selectedArtifactKind}
            onSelect={(kind) => {
              actions.setSelectedArtifactKind(kind);
              actions.setInspectorTab("artifacts");
            }}
          />
        </div>
      </div>
    </section>
  );
}
