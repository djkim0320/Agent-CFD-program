import { useMemo } from "react";
import { useShell } from "../../store/ShellProvider";
import { formatTimestamp, getArtifactByKind, getSelectedJob } from "../../store/selectors";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

export function InspectorDrawer() {
  const { state, actions } = useShell();
  const selectedJob = useMemo(() => getSelectedJob(state), [state]);
  const selectedArtifact = getArtifactByKind(selectedJob, state.selectedArtifactKind);

  return (
    <aside className="inspector-drawer">
      <div className="inspector-drawer__tabs">
        {(["snapshot", "run", "artifacts", "environment"] as const).map((tab) => (
          <button key={tab} type="button" className={state.selectedInspectorTab === tab ? "is-active" : ""} onClick={() => actions.setInspectorTab(tab)}>
            {tab}
          </button>
        ))}
      </div>

      {state.selectedInspectorTab === "snapshot" ? (
        state.draftPreflight ? (
          <div className="inspector-section">
            <div className="inspector-section__header">
              <div>
                <span>Snapshot</span>
                <strong>{state.draftPreflight.preflight_id}</strong>
              </div>
              <StatusBadge label={state.draftPreflight.execution_mode} tone={state.draftPreflight.execution_mode === "real" ? "good" : "warning"} />
            </div>
            <dl className="inspector-kv">
              <dt>Selected solver</dt>
              <dd>{state.draftPreflight.selected_solver}</dd>
              <dt>request_digest</dt>
              <dd>{state.draftPreflight.request_digest}</dd>
              <dt>source_hash</dt>
              <dd>{state.draftPreflight.source_hash}</dd>
              <dt>normalized_manifest_hash</dt>
              <dd>{state.draftPreflight.normalized_manifest_hash}</dd>
              <dt>normalized_geometry_hash</dt>
              <dd>{state.draftPreflight.normalized_geometry_hash}</dd>
            </dl>
            <h4>Warnings and blockers</h4>
            <JsonBlock
              value={{
                runtime_blockers: state.draftPreflight.runtime_blockers,
                install_warnings: state.draftPreflight.install_warnings,
                ai_warnings: state.draftPreflight.ai_warnings,
                policy_warnings: state.draftPreflight.policy_warnings,
              }}
            />
            <h4>Normalization summary</h4>
            <JsonBlock value={state.draftPreflight.normalization_summary} />
          </div>
        ) : (
          <EmptyState title="No snapshot selected" body="Generate a preflight snapshot to inspect hashes, blockers, and normalization metadata." />
        )
      ) : null}

      {state.selectedInspectorTab === "run" ? (
        selectedJob ? (
          <div className="inspector-section">
            <div className="inspector-section__header">
              <div>
                <span>Run</span>
                <strong>{selectedJob.id}</strong>
              </div>
              <StatusBadge label={selectedJob.status} tone={selectedJob.status === "completed" ? "good" : selectedJob.status === "failed" ? "danger" : "warning"} />
            </div>
            <dl className="inspector-kv">
              <dt>Source file</dt>
              <dd>{selectedJob.source_file_name}</dd>
              <dt>Created</dt>
              <dd>{formatTimestamp(selectedJob.created_at)}</dd>
              <dt>Updated</dt>
              <dd>{formatTimestamp(selectedJob.updated_at)}</dd>
              <dt>Snapshot</dt>
              <dd>{selectedJob.preflight_snapshot_id}</dd>
            </dl>
            <h4>Run metadata</h4>
            <JsonBlock value={{ execution_mode: selectedJob.execution_mode, ai_assist_mode: selectedJob.ai_assist_mode, progress: selectedJob.progress, metrics: selectedJob.metrics, error: selectedJob.error }} />
          </div>
        ) : (
          <EmptyState title="No session selected" body="Pick a session from the sidebar to inspect run details." />
        )
      ) : null}

      {state.selectedInspectorTab === "artifacts" ? (
        selectedJob ? (
          <div className="inspector-section">
            <div className="inspector-section__header">
              <div>
                <span>Artifacts</span>
                <strong>{selectedJob.artifacts.length}</strong>
              </div>
              {selectedArtifact ? <StatusBadge label={selectedArtifact.kind} /> : null}
            </div>
            {selectedArtifact ? (
              <>
                <dl className="inspector-kv">
                  <dt>Name</dt>
                  <dd>{selectedArtifact.name}</dd>
                  <dt>Path</dt>
                  <dd>{selectedArtifact.path}</dd>
                  <dt>Download</dt>
                  <dd>{selectedArtifact.download_url ?? "Local path only"}</dd>
                </dl>
                <JsonBlock value={selectedArtifact} />
              </>
            ) : (
              <EmptyState title="No artifact selected" body="Choose an artifact from the workspace thread to inspect its metadata." />
            )}
          </div>
        ) : (
          <EmptyState title="No artifacts yet" body="Artifact metadata appears here after you select a session and artifact." />
        )
      ) : null}

      {state.selectedInspectorTab === "environment" ? (
        <div className="inspector-section">
          <div className="inspector-section__header">
            <div>
              <span>Environment</span>
              <strong>Local-first status</strong>
            </div>
          </div>
          <h4>Connection</h4>
          <JsonBlock value={state.connectionStatus} />
          <h4>Runtime</h4>
          <JsonBlock value={state.installStatus} />
        </div>
      ) : null}
    </aside>
  );
}
