import { useEffect, useMemo, useState } from "react";
import {
  approveJob,
  cancelJob,
  createJobFromPreflight,
  getJob,
  listJobs,
  loadConnectionStatus,
  loadInstallStatus,
  loadJobEvents,
  submitPreflight,
  subscribeJobEvents,
} from "./lib/api";
import type {
  AnalysisFormState,
  ConnectionMode,
  ConnectionStatusResponse,
  InstallStatusResponse,
  JobArtifact,
  JobEventRecord,
  JobSummaryResponse,
  PreflightResponse,
} from "./lib/types";

const initialRequest: AnalysisFormState = {
  geometryFile: null,
  unit: "m",
  frame: { forwardAxis: "x", upAxis: "z", symmetryPlane: "", momentCenter: "0, 0, 0" },
  referenceValues: { area: "1.0", length: "1.0", span: "1.0" },
  flow: { velocity: "60", mach: "0.18", aoa: "4", sideslip: "0", altitude: "0", density: "1.225", viscosity: "1.81e-5" },
  fidelity: "balanced",
  solverPreference: "auto",
  notes: "Steady external aerodynamics for a local desktop workflow.",
};

const placeholderResidualHistory: JobSummaryResponse["residual_history"] = [
  { iteration: 0, residual: 1 },
  { iteration: 10, residual: 0.23 },
  { iteration: 20, residual: 0.054 },
  { iteration: 30, residual: 0.012 },
  { iteration: 40, residual: 0.004 },
];

const placeholderMetrics: Record<string, string | number> = { CL: "—", CD: "—", Cm: "—" };

function formatFileInfo(file: File | null) {
  return file ? `${file.name} | ${(file.size / 1024 / 1024).toFixed(2)} MB` : "No geometry selected";
}

function formatStatusText(value: boolean | undefined) {
  if (typeof value !== "boolean") return "—";
  return value ? "Ready" : "Not ready";
}

function formatMaybeNumber(value: number | string | null | undefined, digits = 2) {
  if (typeof value === "number" && Number.isFinite(value)) return value.toFixed(digits);
  if (typeof value === "string" && value.trim()) return value;
  return "—";
}

function formatPercent(value: number | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "—";
}

function getOverallState(preflight: PreflightResponse | null) {
  if (!preflight) return "scaffold";
  if (preflight.runtime_blockers.length > 0) return "blocked";
  if (preflight.execution_mode === "scaffold") return "scaffold";
  if (preflight.ai_assist_mode === "local_fallback") return "AI-fallback";
  return "real";
}

function isRealExecutionReady(preflight: PreflightResponse | null) {
  return !!preflight && preflight.execution_mode === "real" && preflight.runtime_blockers.length === 0;
}

function findArtifact(job: JobSummaryResponse | null, predicate: (artifact: JobArtifact) => boolean) {
  return job?.artifacts.find(predicate) ?? null;
}

function artifactHref(artifact: JobArtifact | null) {
  return artifact?.download_url ?? artifact?.path ?? "#";
}

function App() {
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("openai_api");
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatusResponse | null>(null);
  const [installStatus, setInstallStatus] = useState<InstallStatusResponse | null>(null);
  const [request, setRequest] = useState<AnalysisFormState>(initialRequest);
  const [preflight, setPreflight] = useState<PreflightResponse | null>(null);
  const [job, setJob] = useState<JobSummaryResponse | null>(null);
  const [events, setEvents] = useState<JobEventRecord[]>([]);
  const [history, setHistory] = useState<JobSummaryResponse[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadInstallStatus().then((status) => !cancelled && setInstallStatus(status)).catch((error) => !cancelled && setNotice(error instanceof Error ? error.message : "Install status is unavailable."));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadConnectionStatus(connectionMode).then((status) => !cancelled && setConnectionStatus(status)).catch((error) => !cancelled && setNotice(error instanceof Error ? error.message : "Connection status is unavailable."));
    return () => {
      cancelled = true;
    };
  }, [connectionMode]);

  useEffect(() => {
    let cancelled = false;
    listJobs().then((jobs) => !cancelled && setHistory(jobs)).catch(() => !cancelled && setHistory([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!job?.id) return;
    return subscribeJobEvents(job.id, (event) => {
      setEvents((current) => (current.some((item) => item.id === event.id) ? current : [...current, event]));
      void getJob(job.id)
        .then((nextJob) => {
          setJob(nextJob);
          return listJobs();
        })
        .then((jobs) => setHistory(jobs))
        .catch(() => undefined);
    });
  }, [job?.id]);

  const previewStyle = useMemo(() => {
    const fileName = request.geometryFile?.name.toLowerCase() ?? "";
    if (fileName.includes("wing") || fileName.includes("aircraft")) return { shape: "Wing-body silhouette", accent: "linear-gradient(135deg, #f0ab3b, #155eef)" };
    if (fileName.includes("body") || fileName.includes("car")) return { shape: "Streamlined body", accent: "linear-gradient(135deg, #22c55e, #0f766e)" };
    return { shape: "Generic 3D volume", accent: "linear-gradient(135deg, #38bdf8, #0f172a)" };
  }, [request.geometryFile]);

  const overallState = getOverallState(preflight);
  const activeResidualHistory = job?.residual_history?.length ? job.residual_history : placeholderResidualHistory;
  const activeMetrics = job?.metrics && Object.keys(job.metrics).length > 0 ? job.metrics : placeholderMetrics;
  const runtimeBlockers = preflight?.runtime_blockers ?? [];
  const installWarnings = preflight?.install_warnings ?? [];
  const aiWarnings = preflight?.ai_warnings ?? [];
  const policyWarnings = preflight?.policy_warnings ?? [];
  const canApprove = isRealExecutionReady(preflight);

  async function runPreflight() {
    if (!request.geometryFile) {
      setNotice("Pick a geometry file before generating a preflight snapshot.");
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const nextPreflight = await submitPreflight(request, connectionMode);
      setPreflight(nextPreflight);
      setJob(null);
      setEvents([]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Preflight request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function approveAndRun() {
    if (!preflight) return setNotice("Generate a preflight snapshot first.");
    if (!canApprove) return setNotice("This snapshot is not approved for real execution.");
    setBusy(true);
    setNotice(null);
    try {
      const draftJob = await createJobFromPreflight(preflight.preflight_id);
      setJob(draftJob);
      const runningJob = await approveJob(draftJob.id);
      setJob(runningJob);
      setEvents(await loadJobEvents(draftJob.id));
      setHistory(await listJobs());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Failed to create or approve the job.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshJobTimeline() {
    if (!job) return;
    setBusy(true);
    try {
      setEvents(await loadJobEvents(job.id));
      setJob(await getJob(job.id));
      setHistory(await listJobs());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to refresh job timeline.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!job) return;
    setBusy(true);
    try {
      setJob(await cancelJob(job.id));
      setHistory(await listJobs());
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Unable to cancel the job.");
    } finally {
      setBusy(false);
    }
  }

  const solverLogArtifact = findArtifact(job, (artifact) => artifact.kind.includes("log") || artifact.name.includes("log"));
  const caseBundleArtifact = findArtifact(job, (artifact) => artifact.kind.includes("package") || artifact.name.includes("bundle"));
  const reportArtifact = findArtifact(job, (artifact) => artifact.kind.includes("report") || artifact.name.includes("report"));
  const summaryArtifact = findArtifact(job, (artifact) => artifact.kind.includes("summary") || artifact.name.includes("summary"));
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AA</div>
          <div>
            <h1>Aero Agent</h1>
            <p>Snapshot-based local aerodynamic analysis</p>
          </div>
        </div>
        <div className="sidebar-card">
          <div className="label">Connection</div>
          <strong>{connectionMode}</strong>
          <span>{connectionStatus?.backend ?? "checking..."}</span>
          <span>{connectionStatus?.provider_ready ? "provider ready" : "provider unavailable"}</span>
        </div>
        <div className="sidebar-card">
          <div className="label">Runtime</div>
          <strong>{overallState}</strong>
          <span>{installStatus ? "install status loaded" : "install status unavailable"}</span>
          <span>{preflight?.preflight_id ?? "no preflight snapshot yet"}</span>
        </div>
      </aside>

      <main className="main">
        <header className="hero">
          <div>
            <p className="eyebrow">Plan - Preflight - Approval - Run - Report</p>
            <h2>Single-path CFD with explicit snapshot approval</h2>
            <p className="hero-copy">Upload a geometry, review a persisted preflight snapshot, approve the same snapshot, and monitor the run without client-side mock fallback.</p>
          </div>
          <div className="hero-stats">
            <div><span>Execution</span><strong>{preflight?.execution_mode ?? "scaffold"}</strong></div>
            <div><span>AI assist</span><strong>{preflight?.ai_assist_mode ?? "remote"}</strong></div>
            <div><span>Overall state</span><strong>{overallState}</strong></div>
            <div><span>Job status</span><strong>{job?.status ?? "idle"}</strong></div>
          </div>
        </header>

        {notice ? (
          <section className="panel"><div className="card"><div className="section-head"><h3>Notice</h3><span className="badge soft">Action needed</span></div><p className="detail-copy">{notice}</p></div></section>
        ) : null}

        <section className="panel grid-two">
          <div className="card">
            <div className="section-head"><h3>Connection Settings</h3><span className="badge">Provider routing</span></div>
            <div className="toggle-row">
              <button className={connectionMode === "openai_api" ? "toggle active" : "toggle"} onClick={() => setConnectionMode("openai_api")}>openai_api</button>
              <button className={connectionMode === "codex_oauth" ? "toggle active" : "toggle"} onClick={() => setConnectionMode("codex_oauth")}>codex_oauth</button>
            </div>
            <div className="field-list">
              <label><span>Connection ID</span><input value={connectionStatus?.connection_id ?? connectionMode} readOnly /></label>
              <label><span>Backend</span><input value={connectionStatus?.backend ?? "checking..."} readOnly /></label>
              <label><span>Provider ready</span><input value={formatStatusText(connectionStatus?.provider_ready)} readOnly /></label>
              <label><span>Warnings</span><textarea value={connectionStatus?.warnings.join("\n") ?? ""} readOnly rows={4} /></label>
            </div>
          </div>
          <div className="card">
            <div className="section-head"><h3>Runtime Readiness</h3><span className="badge soft">Local only</span></div>
            <div className="metric-grid">
              <div><span>Docker</span><strong>{formatStatusText(installStatus?.docker_ok)}</strong></div>
              <div><span>gmsh</span><strong>{formatStatusText(installStatus?.gmsh_ok)}</strong></div>
              <div><span>SU2 image</span><strong>{formatStatusText(installStatus?.su2_image_ok)}</strong></div>
              <div><span>Workspace</span><strong>{formatStatusText(installStatus?.workspace_ok)}</strong></div>
            </div>
            <label><span>Install warnings</span><textarea value={installStatus?.install_warnings.join("\n") ?? ""} readOnly rows={4} /></label>
          </div>
        </section>

        <section className="panel grid-two">
          <div className="card">
            <div className="section-head"><h3>Upload & Preview</h3><span className="badge">STEP / STL / OBJ / .vsp3</span></div>
            <label className="upload-zone">
              <input type="file" accept=".step,.stp,.stl,.obj,.vsp3" onChange={(event) => setRequest((previous) => ({ ...previous, geometryFile: event.target.files?.[0] ?? null }))} />
              <strong>Drop geometry here or browse</strong>
              <span>{formatFileInfo(request.geometryFile)}</span>
            </label>
            <div className="preview-card" style={{ background: previewStyle.accent }}>
              <span>{previewStyle.shape}</span>
              <strong>{request.geometryFile?.name ?? "Preview surface"}</strong>
              <p>Geometry preview placeholder for the selected file.</p>
            </div>
          </div>
          <div className="card">
            <div className="section-head"><h3>Geometry Summary</h3><span className="badge soft">Snapshot input</span></div>
            <div className="metric-grid">
              <div><span>Format</span><strong>{request.geometryFile ? request.geometryFile.name.split(".").pop()?.toUpperCase() : "--"}</strong></div>
              <div><span>Unit</span><strong>{request.unit}</strong></div>
              <div><span>Frame</span><strong>{request.frame.forwardAxis}/{request.frame.upAxis}</strong></div>
              <div><span>Solver hint</span><strong>{request.solverPreference}</strong></div>
            </div>
            <button className="primary-btn" onClick={runPreflight} disabled={busy}>{busy ? "Analyzing..." : "Generate Preflight Snapshot"}</button>
            <p className="detail-copy">This button persists a preflight snapshot first. It does not fabricate a client-side fallback plan.</p>
          </div>
        </section>

        <section className="panel grid-two">
          <div className="card">
            <div className="section-head"><h3>Conditions</h3><span className="badge">Flight state</span></div>
            <div className="field-grid">
              <label><span>Unit</span><input value={request.unit} onChange={(event) => setRequest({ ...request, unit: event.target.value })} /></label>
              <label><span>Fidelity</span><select value={request.fidelity} onChange={(event) => setRequest({ ...request, fidelity: event.target.value as AnalysisFormState["fidelity"] })}><option value="fast">fast</option><option value="balanced">balanced</option><option value="high">high</option></select></label>
              <label><span>Solver preference</span><select value={request.solverPreference} onChange={(event) => setRequest({ ...request, solverPreference: event.target.value as AnalysisFormState["solverPreference"] })}><option value="auto">auto</option><option value="vspaero">vspaero</option><option value="su2">su2</option><option value="openfoam">openfoam</option></select></label>
              <label><span>Velocity</span><input value={request.flow.velocity} onChange={(event) => setRequest({ ...request, flow: { ...request.flow, velocity: event.target.value } })} /></label>
              <label><span>Mach</span><input value={request.flow.mach} onChange={(event) => setRequest({ ...request, flow: { ...request.flow, mach: event.target.value } })} /></label>
              <label><span>AoA</span><input value={request.flow.aoa} onChange={(event) => setRequest({ ...request, flow: { ...request.flow, aoa: event.target.value } })} /></label>
              <label><span>Sideslip</span><input value={request.flow.sideslip} onChange={(event) => setRequest({ ...request, flow: { ...request.flow, sideslip: event.target.value } })} /></label>
              <label><span>Altitude</span><input value={request.flow.altitude} onChange={(event) => setRequest({ ...request, flow: { ...request.flow, altitude: event.target.value } })} /></label>
              <label><span>Density</span><input value={request.flow.density} onChange={(event) => setRequest({ ...request, flow: { ...request.flow, density: event.target.value } })} /></label>
              <label><span>Viscosity</span><input value={request.flow.viscosity} onChange={(event) => setRequest({ ...request, flow: { ...request.flow, viscosity: event.target.value } })} /></label>
            </div>
          </div>
          <div className="card">
            <div className="section-head"><h3>Reference Values</h3><span className="badge soft">CFD coefficients</span></div>
            <div className="field-grid">
              <label><span>Area</span><input value={request.referenceValues.area} onChange={(event) => setRequest({ ...request, referenceValues: { ...request.referenceValues, area: event.target.value } })} /></label>
              <label><span>Length</span><input value={request.referenceValues.length} onChange={(event) => setRequest({ ...request, referenceValues: { ...request.referenceValues, length: event.target.value } })} /></label>
              <label><span>Span</span><input value={request.referenceValues.span} onChange={(event) => setRequest({ ...request, referenceValues: { ...request.referenceValues, span: event.target.value } })} /></label>
              <label><span>Notes</span><textarea rows={5} value={request.notes} onChange={(event) => setRequest({ ...request, notes: event.target.value })} /></label>
            </div>
          </div>
        </section>

        <section className="panel grid-two">
          <div className="card">
            <div className="section-head"><h3>Preflight Review</h3><span className="badge">Approval gate</span></div>
            {preflight ? (
              <>
                <div className="metric-grid">
                  <div><span>preflight_id</span><strong>{preflight.preflight_id}</strong></div>
                  <div><span>Selected solver</span><strong>{preflight.selected_solver}</strong></div>
                  <div><span>Execution mode</span><strong>{preflight.execution_mode}</strong></div>
                  <div><span>AI assist mode</span><strong>{preflight.ai_assist_mode}</strong></div>
                  <div><span>Runtime estimate</span><strong>{formatMaybeNumber(preflight.runtime_estimate_minutes)} min</strong></div>
                  <div><span>Memory estimate</span><strong>{formatMaybeNumber(preflight.memory_estimate_gb)} GB</strong></div>
                  <div><span>Confidence</span><strong>{formatPercent(preflight.confidence)}</strong></div>
                  <div><span>Integrity</span><strong>Snapshot-bound</strong></div>
                </div>
                <div className="state-row">
                  <span className="badge soft">Overall: {overallState}</span>
                  <span className="badge soft">Execution: {preflight.execution_mode}</span>
                  <span className="badge soft">AI: {preflight.ai_assist_mode}</span>
                  <span className="badge soft">Runtime blockers: {runtimeBlockers.length}</span>
                </div>
                <p className="detail-copy">{preflight.rationale}</p>
                <div className="field-list">
                  <label><span>Runtime blockers</span><textarea value={runtimeBlockers.join("\n")} readOnly rows={runtimeBlockers.length || 3} /></label>
                  <label><span>Install warnings</span><textarea value={installWarnings.join("\n")} readOnly rows={installWarnings.length || 3} /></label>
                  <label><span>AI warnings</span><textarea value={aiWarnings.join("\n")} readOnly rows={aiWarnings.length || 3} /></label>
                  <label><span>Policy warnings</span><textarea value={policyWarnings.join("\n")} readOnly rows={policyWarnings.length || 3} /></label>
                </div>
                <div className="field-grid">
                  <label><span>request_digest</span><input value={preflight.request_digest} readOnly /></label>
                  <label><span>source_hash</span><input value={preflight.source_hash} readOnly /></label>
                  <label><span>normalized_manifest_hash</span><input value={preflight.normalized_manifest_hash} readOnly /></label>
                </div>
                <div className="subagent-grid">
                  <div className="subagent-card"><div className="section-head"><h4>geometry-triage</h4><span className="badge soft">{preflight.subagent_findings.geometry_triage.repairability}</span></div><p className="detail-copy">{preflight.subagent_findings.geometry_triage.geometry_kind}</p><ul className="bullet-list">{preflight.subagent_findings.geometry_triage.risks.map((item) => <li key={item}>{item}</li>)}</ul></div>
                  <div className="subagent-card"><div className="section-head"><h4>solver-planner</h4><span className="badge soft">{preflight.subagent_findings.solver_planner.execution_mode}</span></div><p className="detail-copy">{preflight.subagent_findings.solver_planner.recommended_solver}</p><ul className="bullet-list">{preflight.subagent_findings.solver_planner.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>
                  <div className="subagent-card"><div className="section-head"><h4>auth-and-policy-reviewer</h4><span className="badge soft">{preflight.subagent_findings.auth_and_policy_reviewer.export_scope}</span></div><p className="detail-copy">{preflight.subagent_findings.auth_and_policy_reviewer.allowed ? "Allowed" : "Blocked"}</p><ul className="bullet-list">{preflight.subagent_findings.auth_and_policy_reviewer.policy_warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>
                </div>
                <button className="primary-btn" onClick={approveAndRun} disabled={busy || !canApprove}>{busy ? "Starting..." : canApprove ? "Approve & Run" : "Blocked for real execution"}</button>
              </>
            ) : (
              <p className="detail-copy">Run preflight from Upload to generate the persisted snapshot.</p>
            )}
          </div>
          <div className="card">
            <div className="section-head"><h3>Snapshot Contract</h3><span className="badge soft">History-safe</span></div>
            <div className="timeline">
              <div className="timeline-item"><span>1</span><div><strong>Persist snapshot</strong><p>Upload, normalize, and hash the same geometry once.</p></div></div>
              <div className="timeline-item"><span>2</span><div><strong>Approve the snapshot</strong><p>Job creation uses preflight_id instead of re-uploading geometry.</p></div></div>
              <div className="timeline-item"><span>3</span><div><strong>Execute from the same state</strong><p>The worker materializes the immutable snapshot into the job workspace.</p></div></div>
            </div>
          </div>
        </section>
        <section className="panel grid-two">
          <div className="card">
            <div className="section-head"><h3>Run Stream</h3><span className="badge">{job?.status ?? "idle"}</span></div>
            <div className="progress-wrap"><div className="progress-bar"><div style={{ width: `${job?.progress ?? 0}%` }} /></div><strong>{job?.progress ?? 0}% complete</strong></div>
            <div className="event-stream">
              {events.length === 0 ? <p className="detail-copy">No live events yet. Approve a snapshot to start the worker stream.</p> : events.map((event) => <div key={event.id} className="event-item"><span>{event.event_type}</span><strong>{typeof event.payload.message === "string" ? event.payload.message : event.event_type}</strong><small>{new Date(event.created_at).toLocaleString()}</small></div>)}
            </div>
            <div className="button-row">
              <button className="ghost-btn" onClick={refreshJobTimeline} disabled={busy || !job}>Refresh stream</button>
              <button className="ghost-btn" onClick={handleCancel} disabled={busy || !job || job.status === "completed" || job.status === "cancelled"}>Cancel job</button>
            </div>
          </div>
          <div className="card">
            <div className="section-head"><h3>Runtime Diagnostics</h3><span className="badge soft">Local worker</span></div>
            <div className="metric-grid">
              <div><span>Job ID</span><strong>{job?.id ?? "n/a"}</strong></div>
              <div><span>Preflight snapshot</span><strong>{job?.preflight_snapshot_id ?? preflight?.preflight_id ?? "n/a"}</strong></div>
              <div><span>Solver</span><strong>{job?.selected_solver ?? preflight?.selected_solver ?? "su2"}</strong></div>
              <div><span>AI assist</span><strong>{job?.ai_assist_mode ?? preflight?.ai_assist_mode ?? "remote"}</strong></div>
              <div><span>Warnings</span><strong>{(job?.runtime_blockers.length ?? runtimeBlockers.length) + (job?.install_warnings.length ?? installWarnings.length)}</strong></div>
              <div><span>Artifact count</span><strong>{job?.artifacts.length ?? 0}</strong></div>
            </div>
            <p className="detail-copy">The worker keeps the FastAPI loop responsive while the solver runs in the background.</p>
          </div>
        </section>

        <section className="panel grid-two">
          <div className="card">
            <div className="section-head"><h3>Result Report</h3><span className="badge">Residuals + coefficients</span></div>
            <div className="result-grid">
              <div className="result-card">
                <div className="section-head"><h4>Residual plot</h4><span className="badge soft">{job ? "Real or partial data" : "Placeholder data"}</span></div>
                <div className="residual-chart">
                  {activeResidualHistory.map((point) => {
                    const maxResidual = Math.max(...activeResidualHistory.map((item) => item.residual), 1);
                    const height = Math.max((point.residual / maxResidual) * 100, 4);
                    return <div key={point.iteration} className="residual-bar-wrap"><div className="residual-bar-label">{point.iteration}</div><div className="residual-bar-track"><div className="residual-bar" style={{ height: `${height}%` }} /></div><div className="residual-bar-value">{point.residual.toFixed(3)}</div></div>;
                  })}
                </div>
              </div>
              <div className="result-card">
                <div className="section-head"><h4>CL / CD / Cm</h4><span className="badge soft">Coefficient summary</span></div>
                <div className="metric-grid">{["CL", "CD", "Cm"].map((key) => <div key={key}><span>{key}</span><strong>{formatMaybeNumber(activeMetrics[key])}</strong></div>)}</div>
                <p className="detail-copy">The UI keeps coefficient summaries visible even when the full scalar field viewer is deferred.</p>
              </div>
            </div>
            <div className="artifact-list">
              <ArtifactRow title="Solver log link" artifact={solverLogArtifact} fallbackText="solver.log" />
              <ArtifactRow title="Case bundle" artifact={caseBundleArtifact} fallbackText="case_bundle.zip" />
              <ArtifactRow title="Report link" artifact={reportArtifact} fallbackText="report.html" />
              <ArtifactRow title="Summary artifact" artifact={summaryArtifact} fallbackText="summary.json" />
            </div>
          </div>
          <div className="card">
            <div className="section-head"><h3>Viewer Snapshot</h3><span className="badge soft">Artifact shell</span></div>
            <div className="viewer-frame"><div className="viewer-fake-mesh" /><p>This release keeps the viewer honest: artifact shell plus summary links, with full field rendering deferred to a later milestone.</p></div>
          </div>
        </section>

        <section className="panel">
          <div className="card">
            <div className="section-head"><h3>Job History</h3><span className="badge">{history.length} jobs</span></div>
            <div className="history-grid">
              {history.length === 0 ? <p className="detail-copy">No jobs stored yet. Completed snapshot runs will appear here.</p> : history.map((item) => <div key={item.id} className="history-card"><strong>{item.id}</strong><span>{item.status}</span><span>{item.selected_solver}</span><span>{item.execution_mode}</span><span>{item.ai_assist_mode}</span><small>{item.preflight_snapshot_id}</small></div>)}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

function ArtifactRow({ title, artifact, fallbackText }: { title: string; artifact: JobArtifact | null; fallbackText: string }) {
  const href = artifactHref(artifact);
  return (
    <div className="artifact-row">
      <strong>{title}</strong>
      {artifact ? (
        <a href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
          {artifact.name}
        </a>
      ) : (
        <a href={href} onClick={(event) => event.preventDefault()}>
          {fallbackText}
        </a>
      )}
      <span>{artifact?.path ?? "Not generated yet"}</span>
      <small>{artifact?.kind ?? "Placeholder link until the real artifact exists."}</small>
    </div>
  );
}
export default App;
