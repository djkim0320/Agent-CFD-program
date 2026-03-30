import { useMemo } from "react";
import { useShell } from "../../store/ShellProvider";
import {
  canApprovePreflight,
  formatMaybeNumber,
  formatTimestamp,
  getArtifactByKind,
  getReportJobs,
  getSelectedJob,
  getSelectedJobEvents,
  selectDraftNotes,
  selectSessionNotes,
} from "../../store/selectors";
import type { JobArtifact } from "../../lib/types";
import { EmptyState } from "../common/EmptyState";
import { StatusBadge } from "../common/StatusBadge";

function ArtifactPanel({ artifacts, onSelect }: { artifacts: JobArtifact[]; onSelect: (kind: string) => void }) {
  if (artifacts.length === 0) {
    return (
      <EmptyState
        title="Artifacts not ready yet"
        body="Report, solver log, case bundle, and summary links will appear here after the worker finishes."
      />
    );
  }

  return (
    <div className="artifact-panel">
      {artifacts.map((artifact) => (
        <button key={`${artifact.kind}-${artifact.path}`} type="button" className="artifact-row" onClick={() => onSelect(artifact.kind)}>
          <div>
            <strong>{artifact.name}</strong>
            <span>{artifact.kind}</span>
          </div>
          <small>{artifact.path}</small>
        </button>
      ))}
    </div>
  );
}

function ReportsView() {
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

function SettingsView() {
  const { state, actions } = useShell();

  return (
    <div className="thread-block">
      <div className="thread-block__header">
        <div>
          <span className="thread-block__eyebrow">Settings</span>
          <h2>Provider and runtime status</h2>
        </div>
      </div>
      <div className="thread-block__actions">
        <button
          type="button"
          className={state.connectionMode === "openai_api" ? "primary-btn" : "secondary-btn"}
          onClick={() => actions.setConnectionMode("openai_api")}
        >
          openai_api
        </button>
        <button
          type="button"
          className={state.connectionMode === "codex_oauth" ? "primary-btn" : "secondary-btn"}
          onClick={() => actions.setConnectionMode("codex_oauth")}
        >
          codex_oauth
        </button>
      </div>
      <div className="settings-grid">
        <div className="detail-card">
          <span>Connection mode</span>
          <strong>{state.connectionMode}</strong>
          <p>{state.connectionStatus?.warnings.join(", ") || "Primary OpenAI path with deterministic fallback."}</p>
        </div>
        <div className="detail-card">
          <span>Runtime readiness</span>
          <strong>
            {state.installStatus?.docker_ok && state.installStatus?.gmsh_ok && state.installStatus?.su2_image_ok
              ? "Docker + gmsh + SU2 ready"
              : "Runtime checks needed"}
          </strong>
          <p>{state.installStatus?.install_warnings.join(", ") || "No local runtime warnings reported."}</p>
        </div>
      </div>
    </div>
  );
}

export function WorkspaceThread() {
  const { state, actions } = useShell();
  const selectedJob = useMemo(() => getSelectedJob(state), [state]);
  const events = useMemo(() => getSelectedJobEvents(state), [state]);
  const draftNotes = useMemo(() => selectDraftNotes(state), [state]);
  const sessionNotes = useMemo(() => selectSessionNotes(state), [state]);
  const canApprove = canApprovePreflight(state.draftPreflight);
  const selectedArtifact = getArtifactByKind(selectedJob, state.selectedArtifactKind);

  if (state.routePane === "reports") {
    return <ReportsView />;
  }

  if (state.routePane === "settings") {
    return <SettingsView />;
  }

  return (
    <div className="workspace-thread">
      <section className="thread-block">
        <div className="thread-block__header">
          <div>
            <span className="thread-block__eyebrow">Draft workspace</span>
            <h2>Prepare the next analysis</h2>
          </div>
          <StatusBadge label={state.draftPreflight ? "snapshot ready" : "draft only"} tone={state.draftPreflight ? "good" : "neutral"} />
        </div>

        <div className="draft-grid">
          <label className="upload-card">
            <span>Geometry file</span>
            <input
              type="file"
              accept=".step,.stp,.stl,.obj,.vsp3"
              onChange={(event) => actions.setDraftField("geometryFile", event.target.files?.[0] ?? null)}
            />
            <strong>{state.draft.geometryFile?.name ?? "Choose a geometry file"}</strong>
            <small>STL/OBJ are the primary happy path. STEP remains conditional on tessellation success.</small>
          </label>

          <div className="detail-card">
            <span>Conditions</span>
            <div className="form-grid">
              <label>
                <span>Unit</span>
                <select value={state.draft.unit} onChange={(event) => actions.setDraftField("unit", event.target.value)}>
                  <option value="m">m</option>
                  <option value="cm">cm</option>
                  <option value="mm">mm</option>
                  <option value="in">in</option>
                  <option value="ft">ft</option>
                </select>
              </label>
              <label>
                <span>Fidelity</span>
                <select value={state.draft.fidelity} onChange={(event) => actions.setDraftField("fidelity", event.target.value)}>
                  <option value="fast">fast</option>
                  <option value="balanced">balanced</option>
                  <option value="high">high</option>
                </select>
              </label>
              <label>
                <span>Solver preference</span>
                <select value={state.draft.solverPreference} onChange={(event) => actions.setDraftField("solverPreference", event.target.value)}>
                  <option value="auto">auto</option>
                  <option value="su2">su2</option>
                  <option value="vspaero">vspaero</option>
                  <option value="openfoam">openfoam</option>
                </select>
              </label>
              <label>
                <span>Forward / Up</span>
                <div className="axis-pair">
                  <select value={state.draft.frame.forwardAxis} onChange={(event) => actions.setDraftSection("frame", { forwardAxis: event.target.value })}>
                    <option value="x">x</option>
                    <option value="y">y</option>
                    <option value="z">z</option>
                  </select>
                  <select value={state.draft.frame.upAxis} onChange={(event) => actions.setDraftSection("frame", { upAxis: event.target.value })}>
                    <option value="x">x</option>
                    <option value="y">y</option>
                    <option value="z">z</option>
                  </select>
                </div>
              </label>
              <label>
                <span>AoA</span>
                <input value={state.draft.flow.aoa} onChange={(event) => actions.setDraftSection("flow", { aoa: event.target.value })} />
              </label>
              <label>
                <span>Sideslip</span>
                <input value={state.draft.flow.sideslip} onChange={(event) => actions.setDraftSection("flow", { sideslip: event.target.value })} />
              </label>
              <label>
                <span>Velocity</span>
                <input value={state.draft.flow.velocity} onChange={(event) => actions.setDraftSection("flow", { velocity: event.target.value })} />
              </label>
              <label>
                <span>Mach</span>
                <input value={state.draft.flow.mach} onChange={(event) => actions.setDraftSection("flow", { mach: event.target.value })} />
              </label>
              <label>
                <span>Area</span>
                <input value={state.draft.referenceValues.area} onChange={(event) => actions.setDraftSection("referenceValues", { area: event.target.value })} />
              </label>
              <label>
                <span>Length</span>
                <input value={state.draft.referenceValues.length} onChange={(event) => actions.setDraftSection("referenceValues", { length: event.target.value })} />
              </label>
              <label>
                <span>Span</span>
                <input value={state.draft.referenceValues.span} onChange={(event) => actions.setDraftSection("referenceValues", { span: event.target.value })} />
              </label>
              <label className="form-grid__notes">
                <span>Notes</span>
                <textarea value={state.draft.notes} rows={4} onChange={(event) => actions.setDraftField("notes", event.target.value)} />
              </label>
            </div>
          </div>
        </div>

        {draftNotes.length > 0 ? (
          <div className="note-stack">
            {draftNotes.map((note) => (
              <article key={note.id} className="note-card">
                <span>Composer note</span>
                <p>{note.text}</p>
              </article>
            ))}
          </div>
        ) : null}
      </section>

      <section className="thread-block">
        <div className="thread-block__header">
          <div>
            <span className="thread-block__eyebrow">Preflight</span>
            <h2>Snapshot review</h2>
          </div>
          <div className="thread-block__actions">
            <button type="button" className="secondary-btn" onClick={() => void actions.runPreflight()} disabled={state.busy}>
              {state.busy ? "Analyzing..." : "Generate preflight"}
            </button>
            <button type="button" className="primary-btn" onClick={() => void actions.approveCurrentDraft()} disabled={state.busy || !canApprove}>
              Approve &amp; run
            </button>
          </div>
        </div>

        {state.draftPreflight ? (
          <div className="thread-card">
            <div className="thread-card__meta">
              <StatusBadge label={state.draftPreflight.execution_mode} tone={state.draftPreflight.execution_mode === "real" ? "good" : "warning"} />
              <StatusBadge label={state.draftPreflight.ai_assist_mode} tone={state.draftPreflight.ai_assist_mode === "local_fallback" ? "warning" : "neutral"} />
              <StatusBadge label={state.draftPreflight.mesh_strategy} />
            </div>
            <h3>{state.draftPreflight.selected_solver} selected</h3>
            <p>{state.draftPreflight.rationale}</p>
            <div className="summary-grid">
              <div>
                <span>Snapshot</span>
                <strong>{state.draftPreflight.preflight_id}</strong>
              </div>
              <div>
                <span>Confidence</span>
                <strong>{Math.round(state.draftPreflight.confidence * 100)}%</strong>
              </div>
              <div>
                <span>Runtime blockers</span>
                <strong>{state.draftPreflight.runtime_blockers.length}</strong>
              </div>
              <div>
                <span>AI warnings</span>
                <strong>{state.draftPreflight.ai_warnings.length}</strong>
              </div>
            </div>
            <div className="thread-card__warnings">
              <label>
                <span>Runtime blockers</span>
                <textarea readOnly rows={Math.max(state.draftPreflight.runtime_blockers.length, 3)} value={state.draftPreflight.runtime_blockers.join("\n")} />
              </label>
              <label>
                <span>Normalization summary</span>
                <textarea readOnly rows={7} value={JSON.stringify(state.draftPreflight.normalization_summary, null, 2)} />
              </label>
            </div>
          </div>
        ) : (
          <EmptyState title="No snapshot yet" body="Generate a preflight snapshot to review solver choice, blockers, hashes, and normalization details before creating a session." />
        )}
      </section>

      <section className="thread-block">
        <div className="thread-block__header">
          <div>
            <span className="thread-block__eyebrow">Session thread</span>
            <h2>{selectedJob ? selectedJob.source_file_name : "No active session selected"}</h2>
          </div>
          <div className="thread-block__actions">
            <button type="button" className="secondary-btn" onClick={() => void actions.refreshSelectedJob()} disabled={!selectedJob || state.busy}>
              Refresh
            </button>
            <button
              type="button"
              className="secondary-btn"
              onClick={() => void actions.cancelSelectedJob()}
              disabled={!selectedJob || state.busy || selectedJob.status === "completed" || selectedJob.status === "cancelled"}
            >
              Cancel
            </button>
          </div>
        </div>

        {!selectedJob ? (
          <EmptyState title="No persistent session selected" body="Create a job from the current snapshot or pick a recent session from the sidebar." />
        ) : (
          <>
            <div className="thread-card">
              <div className="thread-card__meta">
                <StatusBadge label={selectedJob.status} tone={selectedJob.status === "completed" ? "good" : selectedJob.status === "failed" ? "danger" : "warning"} />
                <StatusBadge label={selectedJob.execution_mode} tone={selectedJob.execution_mode === "real" ? "good" : "warning"} />
                <StatusBadge label={selectedJob.ai_assist_mode} tone={selectedJob.ai_assist_mode === "local_fallback" ? "warning" : "neutral"} />
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
                events.map((event) => (
                  <article key={`${event.seq}-${event.id}`} className="event-row">
                    <div className="event-row__meta">
                      <span>{event.event_type}</span>
                      <small>{formatTimestamp(event.created_at)}</small>
                    </div>
                    <strong>{typeof event.payload.message === "string" ? event.payload.message : event.event_type}</strong>
                    <pre>{JSON.stringify(event.payload, null, 2)}</pre>
                  </article>
                ))
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
                  <p>No residual history published yet.</p>
                )}
              </div>
              <ArtifactPanel
                artifacts={selectedJob.artifacts}
                onSelect={(kind) => {
                  actions.setSelectedArtifactKind(kind);
                  actions.setInspectorTab("artifacts");
                }}
              />
            </div>

            {selectedArtifact ? (
              <div className="thread-card">
                <div className="thread-card__header">
                  <div>
                    <span className="thread-block__eyebrow">Selected artifact</span>
                    <h3>{selectedArtifact.name}</h3>
                  </div>
                  <StatusBadge label={selectedArtifact.kind} />
                </div>
                <p>{selectedArtifact.path}</p>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  );
}
