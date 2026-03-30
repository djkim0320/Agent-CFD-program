import { useMemo } from "react";
import { useShell } from "../../store/ShellProvider";
import {
  describeAiReviewState,
  describeJobAiReviewState,
  describeProviderState,
  describeRuntimeState,
  formatTimestamp,
  getArtifactByKind,
  getDiagnosticsForContext,
  getSelectedJob,
  summarizeNormalizationSummary,
  summarizeRuntimeBlockerDetails,
} from "../../store/selectors";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

function renderRaw(value: unknown) {
  if (value instanceof Error) {
    return JSON.stringify({ name: value.name, message: value.message, stack: value.stack }, null, 2);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function toneForDiagnostic(severity: "info" | "warning" | "error") {
  if (severity === "error") {
    return "danger" as const;
  }
  if (severity === "warning") {
    return "warning" as const;
  }
  return "neutral" as const;
}

export function InspectorDrawer() {
  const { state, actions } = useShell();
  const selectedJob = useMemo(() => getSelectedJob(state), [state]);
  const selectedArtifact = getArtifactByKind(selectedJob, state.selectedArtifactKind);
  const diagnostics = useMemo(() => getDiagnosticsForContext(state), [state]);
  const providerState = describeProviderState(state.connectionStatus);
  const runtimeState = describeRuntimeState(state.installStatus);
  const aiReviewState = describeAiReviewState(state.draftPreflight);
  const jobAiReviewState = describeJobAiReviewState(selectedJob);
  const streamHealth = selectedJob ? state.streamHealthByJobId[selectedJob.id] : null;
  const normalizationRows = useMemo(
    () => (state.draftPreflight ? summarizeNormalizationSummary(state.draftPreflight.normalization_summary) : []),
    [state.draftPreflight],
  );
  const blockerRows = useMemo(() => summarizeRuntimeBlockerDetails(state.draftPreflight), [state.draftPreflight]);

  return (
    <aside className="inspector-drawer">
      <div className="inspector-drawer__tabs">
        {(["snapshot", "run", "artifacts", "environment", "diagnostics"] as const).map((tab) => (
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
            <div className="inspector-card-grid">
              <div className="inspector-card">
                <span>Selected solver</span>
                <strong>{state.draftPreflight.selected_solver}</strong>
              </div>
              <div className="inspector-card">
                <span>AI review</span>
                <strong>{aiReviewState.label}</strong>
              </div>
              <div className="inspector-card">
                <span>Runtime blockers</span>
                <strong>{state.draftPreflight.runtime_blockers.length}</strong>
              </div>
              <div className="inspector-card">
                <span>Warnings</span>
                <strong>{state.draftPreflight.ai_warnings.length + state.draftPreflight.policy_warnings.length}</strong>
              </div>
            </div>
            <dl className="inspector-kv">
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
            <div className="warning-stack">
              {state.draftPreflight.runtime_blockers.length > 0 ? (
                <div className="warning-block">
                  <span>Runtime blockers</span>
                  <ul>
                    {state.draftPreflight.runtime_blockers.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : (
                <div className="warning-block warning-block--muted">
                  <span>Runtime blockers</span>
                  <p>None reported.</p>
                </div>
              )}
              <div className="warning-block">
                <span>AI warnings</span>
                {state.draftPreflight.ai_warnings.length > 0 ? (
                  <ul>
                    {state.draftPreflight.ai_warnings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>None reported.</p>
                )}
              </div>
              <div className="warning-block">
                <span>Policy warnings</span>
                {state.draftPreflight.policy_warnings.length > 0 ? (
                  <ul>
                    {state.draftPreflight.policy_warnings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>None reported.</p>
                )}
              </div>
            </div>
            {blockerRows.length > 0 ? (
              <>
                <h4>Blocker guidance</h4>
                <div className="inspector-card-grid">
                  {blockerRows.map((row) => (
                    <div key={`${row.label}-${row.value}`} className="inspector-card">
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
            <h4>Normalization summary</h4>
            <div className="inspector-card-grid">
              {normalizationRows.length > 0 ? (
                normalizationRows.map((row) => (
                  <div key={`${row.label}-${row.value}`} className="inspector-card">
                    <span>{row.label}</span>
                    <strong>{row.value}</strong>
                  </div>
                ))
              ) : (
                <EmptyState title="Normalization summary unavailable" body="The normalized geometry summary has not been published yet." />
              )}
            </div>
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
            <div className="inspector-card-grid">
              <div className="inspector-card">
                <span>Source file</span>
                <strong>{selectedJob.source_file_name}</strong>
              </div>
              <div className="inspector-card">
                <span>Progress</span>
                <strong>{selectedJob.progress}%</strong>
              </div>
              <div className="inspector-card">
                <span>Solver</span>
                <strong>{selectedJob.selected_solver}</strong>
              </div>
              <div className="inspector-card">
                <span>Stream</span>
                <strong>{streamHealth ? streamHealth.state : "idle"}</strong>
              </div>
            </div>
            <dl className="inspector-kv">
              <dt>Created</dt>
              <dd>{formatTimestamp(selectedJob.created_at)}</dd>
              <dt>Updated</dt>
              <dd>{formatTimestamp(selectedJob.updated_at)}</dd>
              <dt>Snapshot</dt>
              <dd>{selectedJob.preflight_snapshot_id}</dd>
              <dt>Runtime</dt>
              <dd>{selectedJob.execution_mode}</dd>
            </dl>
            {streamHealth ? (
              <div className="warning-block">
                <span>Stream status</span>
                <p>{streamHealth.lastError ?? "Live events are streaming normally."}</p>
                <small>{streamHealth.lastEventAt ? `Last event: ${formatTimestamp(streamHealth.lastEventAt)}` : "No live events received yet."}</small>
              </div>
            ) : null}
            <div className="summary-detail-grid">
              <div className="summary-detail-card">
                <span>AI review</span>
                <strong>{jobAiReviewState.label}</strong>
              </div>
              <div className="summary-detail-card">
                <span>Runtime blockers</span>
                <strong>{selectedJob.runtime_blockers.length}</strong>
              </div>
              <div className="summary-detail-card">
                <span>Warnings</span>
                <strong>{selectedJob.ai_warnings.length + selectedJob.policy_warnings.length}</strong>
              </div>
              <div className="summary-detail-card">
                <span>Artifacts</span>
                <strong>{selectedJob.artifacts.length}</strong>
              </div>
            </div>
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
              <div className="inspector-card-grid">
                <div className="inspector-card">
                  <span>Name</span>
                  <strong>{selectedArtifact.name}</strong>
                </div>
                <div className="inspector-card">
                  <span>Kind</span>
                  <strong>{selectedArtifact.kind}</strong>
                </div>
                <div className="inspector-card">
                  <span>Path</span>
                  <strong>{selectedArtifact.path}</strong>
                </div>
                <div className="inspector-card">
                  <span>Download</span>
                  <strong>{selectedArtifact.download_url ?? "Local path only"}</strong>
                </div>
              </div>
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
          <div className="inspector-card-grid">
            <div className="inspector-card">
              <span>Provider</span>
              <strong>{providerState.label}</strong>
              <p>{providerState.detail}</p>
            </div>
            <div className="inspector-card">
              <span>Runtime</span>
              <strong>{runtimeState.label}</strong>
              <p>{runtimeState.detail}</p>
            </div>
            <div className="inspector-card">
              <span>AI review</span>
              <strong>{aiReviewState.label}</strong>
              <p>{aiReviewState.detail}</p>
            </div>
          </div>
        </div>
      ) : null}

      {state.selectedInspectorTab === "diagnostics" ? (
        <div className="inspector-section">
          <div className="inspector-section__header">
            <div>
              <span>Diagnostics</span>
              <strong>{diagnostics.length}</strong>
            </div>
          </div>
          {diagnostics.length === 0 ? (
            <EmptyState title="No diagnostics yet" body="Decode, provider, stream, runtime, artifact, and preflight issues will surface here." />
          ) : (
            <div className="diagnostic-list">
              {diagnostics.map((issue) => (
                <article key={issue.id} className="diagnostic-card">
                  <div className="diagnostic-card__header">
                    <div>
                      <span>{issue.scope}</span>
                      <strong>{issue.title}</strong>
                    </div>
                    <StatusBadge label={issue.severity} tone={toneForDiagnostic(issue.severity)} />
                  </div>
                  <p>{issue.detail}</p>
                  <dl className="inspector-kv">
                    <dt>Code</dt>
                    <dd>{issue.code}</dd>
                    <dt>Impact</dt>
                    <dd>{issue.impact ?? "Not provided"}</dd>
                    <dt>Next action</dt>
                    <dd>{issue.nextAction ?? "Not provided"}</dd>
                  </dl>
                  {issue.raw ? (
                    <>
                      <h4>Raw payload</h4>
                      <pre className="json-block">{renderRaw(issue.raw)}</pre>
                    </>
                  ) : null}
                </article>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </aside>
  );
}
