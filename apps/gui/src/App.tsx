import { useEffect, useMemo, useState } from "react";
import {
  approveJob,
  createJob,
  getJob,
  listJobs,
  loadConnectionStatus,
  loadJobEvents,
  submitPreflight,
  subscribeJobEvents,
} from "./lib/api";
import { createMockPlan } from "./lib/mock";
import type {
  AnalysisJob,
  AnalysisRequest,
  ConnectionMode,
  ConnectionStatus,
  JobEvent,
  PreflightPlan,
} from "./lib/types";

const initialRequest: AnalysisRequest = {
  geometryFile: null,
  unit: "m",
  frame: {
    forwardAxis: "x",
    upAxis: "z",
    symmetryPlane: "",
    momentCenter: "0, 0, 0",
  },
  referenceValues: {
    area: "1.0",
    length: "1.0",
    span: "1.0",
  },
  flow: {
    velocity: "60",
    mach: "0.18",
    aoa: "4",
    sideslip: "0",
    altitude: "0",
    density: "1.225",
    viscosity: "1.81e-5",
  },
  fidelity: "balanced",
  solverPreference: "auto",
  notes: "Steady external aerodynamics for a local desktop workflow.",
};

const screens = ["Connection", "Upload", "Conditions", "Preflight", "Run", "Report", "History"] as const;
type Screen = (typeof screens)[number];

function formatFileInfo(file: File | null) {
  if (!file) {
    return "No geometry selected";
  }
  return `${file.name} | ${(file.size / 1024 / 1024).toFixed(2)} MB | ${file.type || "unknown type"}`;
}

function App() {
  const [screen, setScreen] = useState<Screen>("Connection");
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("codex_oauth");
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus | null>(null);
  const [request, setRequest] = useState<AnalysisRequest>(initialRequest);
  const [plan, setPlan] = useState<PreflightPlan | null>(null);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [jobHistory, setJobHistory] = useState<AnalysisJob[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void loadConnectionStatus(connectionMode).then(setConnectionStatus);
  }, [connectionMode]);

  useEffect(() => {
    void listJobs().then(setJobHistory);
  }, []);

  useEffect(() => {
    if (!job) {
      return;
    }
    const unsubscribe = subscribeJobEvents(job.id, (event) => {
      setEvents((current) => {
        if (current.some((item) => item.id === event.id)) {
          return current;
        }
        return [...current, event];
      });
      void getJob(job.id)
        .then((nextJob) => {
          setJob(nextJob);
          return listJobs();
        })
        .then(setJobHistory)
        .catch(() => {
          // Keep current state if the API is temporarily unavailable.
        });
    });
    return unsubscribe;
  }, [job?.id]);

  const previewStyle = useMemo(() => {
    const fileName = request.geometryFile?.name.toLowerCase() ?? "";
    if (fileName.includes("wing") || fileName.includes("aircraft")) {
      return { shape: "Wing-body silhouette", accent: "linear-gradient(135deg, #f0ab3b, #155eef)" };
    }
    if (fileName.includes("body") || fileName.includes("car")) {
      return { shape: "Streamlined body", accent: "linear-gradient(135deg, #22c55e, #0f766e)" };
    }
    return { shape: "Generic 3D volume", accent: "linear-gradient(135deg, #38bdf8, #0f172a)" };
  }, [request.geometryFile]);

  async function runPreflight() {
    if (!request.geometryFile) {
      setPlan(createMockPlan(request));
      setScreen("Preflight");
      return;
    }
    setBusy(true);
    try {
      const nextPlan = await submitPreflight(request, connectionMode);
      setPlan(nextPlan);
      setScreen("Preflight");
    } finally {
      setBusy(false);
    }
  }

  async function approveAndRun() {
    if (!plan || !request.geometryFile) {
      return;
    }
    setBusy(true);
    try {
      const createdJob = await createJob(request, connectionMode);
      setJob(createdJob);
      setEvents(await loadJobEvents(createdJob.id));
      const runningJob = await approveJob(createdJob.id);
      setJob(runningJob);
      setScreen("Run");
      void listJobs().then(setJobHistory);
    } finally {
      setBusy(false);
    }
  }

  async function refreshJobTimeline() {
    if (!job) {
      return;
    }
    const remoteEvents = await loadJobEvents(job.id);
    if (remoteEvents.length > 0) {
      setEvents(remoteEvents);
    }
    try {
      setJob(await getJob(job.id));
    } catch {
      // Ignore refresh failures.
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AA</div>
          <div>
            <h1>Aero Agent</h1>
            <p>Local aerodynamic analysis workspace</p>
          </div>
        </div>

        <nav className="nav">
          {screens.map((item) => (
            <button
              key={item}
              className={item === screen ? "nav-item active" : "nav-item"}
              onClick={() => setScreen(item)}
            >
              {item}
            </button>
          ))}
        </nav>

        <div className="sidebar-card">
          <div className="label">Connection</div>
          <strong>{connectionMode}</strong>
          <span>{connectionStatus?.backend ?? "checking..."}</span>
          <span>{connectionStatus?.providerReady ? "ready" : "not ready"}</span>
        </div>
      </aside>

      <main className="main">
        <header className="hero">
          <div>
            <p className="eyebrow">Plan - Preflight - Approval - Run - Report</p>
            <h2>Deterministic CFD with guided agent orchestration</h2>
            <p className="hero-copy">
              Upload a geometry, review the solver plan, approve execution, and inspect results in one local-first
              desktop workflow.
            </p>
          </div>
          <div className="hero-stats">
            <div>
              <span>Mode</span>
              <strong>{connectionMode}</strong>
            </div>
            <div>
              <span>Selected solver</span>
              <strong>{plan?.selectedSolver ?? "auto"}</strong>
            </div>
            <div>
              <span>Job status</span>
              <strong>{job?.status ?? "idle"}</strong>
            </div>
          </div>
        </header>

        {screen === "Connection" && (
          <section className="panel grid-two">
            <div className="card">
              <div className="section-head">
                <h3>Connection Settings</h3>
                <span className="badge">Provider routing</span>
              </div>
              <div className="toggle-row">
                <button
                  className={connectionMode === "codex_oauth" ? "toggle active" : "toggle"}
                  onClick={() => setConnectionMode("codex_oauth")}
                >
                  codex_oauth
                </button>
                <button
                  className={connectionMode === "openai_api" ? "toggle active" : "toggle"}
                  onClick={() => setConnectionMode("openai_api")}
                >
                  openai_api
                </button>
              </div>
              <div className="field-list">
                <label>
                  Backend status
                  <input value={connectionStatus?.backend ?? ""} readOnly />
                </label>
                <label>
                  Provider ready
                  <input value={connectionStatus?.providerReady ? "Yes" : "No"} readOnly />
                </label>
                <label>
                  Warnings
                  <textarea value={connectionStatus?.warnings.join("\n") ?? ""} readOnly rows={5} />
                </label>
              </div>
            </div>
            <div className="card">
              <div className="section-head">
                <h3>Operational Notes</h3>
                <span className="badge soft">Beta policy</span>
              </div>
              <ul className="bullet-list">
                <li>Windows codex_oauth runs as a beta path and prefers WSL-backed execution.</li>
                <li>openai_api stays separate so quota, auth, and data handling remain explicit.</li>
                <li>Raw token handling is owned by the provider runtime, not the GUI.</li>
              </ul>
            </div>
          </section>
        )}

        {screen === "Upload" && (
          <section className="panel grid-two">
            <div className="card">
              <div className="section-head">
                <h3>Upload & Preview</h3>
                <span className="badge">STEP / STL / OBJ / .vsp3</span>
              </div>
              <label className="upload-zone">
                <input
                  type="file"
                  accept=".step,.stp,.stl,.obj,.vsp3"
                  onChange={(event) =>
                    setRequest((previous) => ({ ...previous, geometryFile: event.target.files?.[0] ?? null }))
                  }
                />
                <strong>Drop geometry here or browse</strong>
                <span>{formatFileInfo(request.geometryFile)}</span>
              </label>
              <div className="preview-card" style={{ background: previewStyle.accent }}>
                <span>{previewStyle.shape}</span>
                <strong>{request.geometryFile?.name ?? "Preview surface"}</strong>
                <p>Desktop-friendly placeholder viewer for the selected geometry.</p>
              </div>
            </div>
            <div className="card">
              <div className="section-head">
                <h3>Geometry Summary</h3>
                <span className="badge soft">Local only</span>
              </div>
              <div className="metric-grid">
                <div>
                  <span>Format</span>
                  <strong>{request.geometryFile ? request.geometryFile.name.split(".").pop()?.toUpperCase() : "--"}</strong>
                </div>
                <div>
                  <span>Unit</span>
                  <strong>{request.unit}</strong>
                </div>
                <div>
                  <span>Frame</span>
                  <strong>
                    {request.frame.forwardAxis}/{request.frame.upAxis}
                  </strong>
                </div>
                <div>
                  <span>Solver hint</span>
                  <strong>{request.solverPreference}</strong>
                </div>
              </div>
              <button className="primary-btn" onClick={runPreflight} disabled={busy}>
                {busy ? "Analyzing..." : "Generate Preflight"}
              </button>
            </div>
          </section>
        )}

        {screen === "Conditions" && (
          <section className="panel grid-two">
            <div className="card">
              <div className="section-head">
                <h3>Conditions</h3>
                <span className="badge">Flight state</span>
              </div>
              <div className="field-grid">
                <label>
                  Unit
                  <input value={request.unit} onChange={(event) => setRequest({ ...request, unit: event.target.value })} />
                </label>
                <label>
                  Fidelity
                  <select
                    value={request.fidelity}
                    onChange={(event) =>
                      setRequest({ ...request, fidelity: event.target.value as AnalysisRequest["fidelity"] })
                    }
                  >
                    <option value="fast">fast</option>
                    <option value="balanced">balanced</option>
                    <option value="high">high</option>
                  </select>
                </label>
                <label>
                  Solver preference
                  <select
                    value={request.solverPreference}
                    onChange={(event) =>
                      setRequest({
                        ...request,
                        solverPreference: event.target.value as AnalysisRequest["solverPreference"],
                      })
                    }
                  >
                    <option value="auto">auto</option>
                    <option value="vspaero">vspaero</option>
                    <option value="su2">su2</option>
                    <option value="openfoam">openfoam</option>
                  </select>
                </label>
                <label>
                  Velocity
                  <input
                    value={request.flow.velocity}
                    onChange={(event) =>
                      setRequest({ ...request, flow: { ...request.flow, velocity: event.target.value } })
                    }
                  />
                </label>
                <label>
                  Mach
                  <input
                    value={request.flow.mach}
                    onChange={(event) => setRequest({ ...request, flow: { ...request.flow, mach: event.target.value } })}
                  />
                </label>
                <label>
                  AoA
                  <input
                    value={request.flow.aoa}
                    onChange={(event) => setRequest({ ...request, flow: { ...request.flow, aoa: event.target.value } })}
                  />
                </label>
                <label>
                  Sideslip
                  <input
                    value={request.flow.sideslip}
                    onChange={(event) =>
                      setRequest({ ...request, flow: { ...request.flow, sideslip: event.target.value } })
                    }
                  />
                </label>
                <label>
                  Altitude
                  <input
                    value={request.flow.altitude}
                    onChange={(event) =>
                      setRequest({ ...request, flow: { ...request.flow, altitude: event.target.value } })
                    }
                  />
                </label>
              </div>
            </div>
            <div className="card">
              <div className="section-head">
                <h3>Reference Values</h3>
                <span className="badge soft">CFD coefficients</span>
              </div>
              <div className="field-grid">
                <label>
                  Area
                  <input
                    value={request.referenceValues.area}
                    onChange={(event) =>
                      setRequest({
                        ...request,
                        referenceValues: { ...request.referenceValues, area: event.target.value },
                      })
                    }
                  />
                </label>
                <label>
                  Length
                  <input
                    value={request.referenceValues.length}
                    onChange={(event) =>
                      setRequest({
                        ...request,
                        referenceValues: { ...request.referenceValues, length: event.target.value },
                      })
                    }
                  />
                </label>
                <label>
                  Span
                  <input
                    value={request.referenceValues.span}
                    onChange={(event) =>
                      setRequest({
                        ...request,
                        referenceValues: { ...request.referenceValues, span: event.target.value },
                      })
                    }
                  />
                </label>
                <label>
                  Notes
                  <textarea
                    rows={5}
                    value={request.notes}
                    onChange={(event) => setRequest({ ...request, notes: event.target.value })}
                  />
                </label>
              </div>
            </div>
          </section>
        )}

        {screen === "Preflight" && (
          <section className="panel grid-two">
            <div className="card">
              <div className="section-head">
                <h3>Preflight Review</h3>
                <span className="badge">Approval gate</span>
              </div>
              {plan ? (
                <>
                  <div className="metric-grid">
                    <div>
                      <span>Selected solver</span>
                      <strong>{plan.selectedSolver}</strong>
                    </div>
                    <div>
                      <span>Runtime</span>
                      <strong>{plan.runtimeEstimate}</strong>
                    </div>
                    <div>
                      <span>Memory</span>
                      <strong>{plan.memoryEstimate}</strong>
                    </div>
                    <div>
                      <span>Confidence</span>
                      <strong>{Math.round(plan.confidence * 100)}%</strong>
                    </div>
                  </div>
                  <p className="detail-copy">{plan.rationale}</p>
                  <ul className="bullet-list">
                    {plan.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                  <button className="primary-btn" onClick={approveAndRun} disabled={busy || !request.geometryFile}>
                    {busy ? "Starting..." : "Approve & Run"}
                  </button>
                </>
              ) : (
                <p className="detail-copy">Run preflight from Upload to generate the solver plan.</p>
              )}
            </div>
            <div className="card">
              <div className="section-head">
                <h3>Plan Snapshot</h3>
                <span className="badge soft">History-safe</span>
              </div>
              <div className="timeline">
                <div className="timeline-item">
                  <span>1</span>
                  <div>
                    <strong>Geometry triage</strong>
                    <p>Inspect file shape, units, and repairability.</p>
                  </div>
                </div>
                <div className="timeline-item">
                  <span>2</span>
                  <div>
                    <strong>Solver selection</strong>
                    <p>Choose VSPAERO, SU2, or OpenFOAM based on fit.</p>
                  </div>
                </div>
                <div className="timeline-item">
                  <span>3</span>
                  <div>
                    <strong>Manual approval</strong>
                    <p>Confirm the plan before any mutable solver work starts.</p>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {screen === "Run" && (
          <section className="panel grid-two">
            <div className="card">
              <div className="section-head">
                <h3>Run Stream</h3>
                <span className="badge">{job?.status ?? "idle"}</span>
              </div>
              <div className="progress-wrap">
                <div className="progress-bar">
                  <div style={{ width: `${job?.progress ?? 0}%` }} />
                </div>
                <strong>{job?.progress ?? 0}% complete</strong>
              </div>
              <div className="event-stream">
                {events.map((event) => (
                  <div key={event.id} className="event-item">
                    <span>{event.type}</span>
                    <strong>{event.message}</strong>
                    <small>{new Date(event.timestamp).toLocaleString()}</small>
                  </div>
                ))}
              </div>
              <button className="ghost-btn" onClick={refreshJobTimeline}>
                Refresh stream
              </button>
            </div>
            <div className="card">
              <div className="section-head">
                <h3>Runtime Diagnostics</h3>
                <span className="badge soft">Local worker</span>
              </div>
              <div className="metric-grid">
                <div>
                  <span>Job ID</span>
                  <strong>{job?.id ?? "n/a"}</strong>
                </div>
                <div>
                  <span>Solver</span>
                  <strong>{job?.selectedSolver ?? "n/a"}</strong>
                </div>
                <div>
                  <span>Warnings</span>
                  <strong>{job?.warnings.length ?? 0}</strong>
                </div>
                <div>
                  <span>Artifact count</span>
                  <strong>{job?.artifacts.length ?? 0}</strong>
                </div>
              </div>
              <p className="detail-copy">
                This screen listens to the local SSE stream and mirrors the current deterministic scaffold run.
              </p>
            </div>
          </section>
        )}

        {screen === "Report" && (
          <section className="panel grid-two">
            <div className="card">
              <div className="section-head">
                <h3>Result Report</h3>
                <span className="badge">HTML + artifacts</span>
              </div>
              {job ? (
                <>
                  <div className="metric-grid">
                    {Object.entries(job.metrics).map(([key, value]) => (
                      <div key={key}>
                        <span>{key}</span>
                        <strong>{String(value)}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="artifact-list">
                    {job.artifacts.map((artifact) => (
                      <div key={artifact.path} className="artifact-row">
                        <strong>{artifact.name}</strong>
                        <span>{artifact.path}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="detail-copy">Run a job to generate report artifacts.</p>
              )}
            </div>
            <div className="card">
              <div className="section-head">
                <h3>Viewer Snapshot</h3>
                <span className="badge soft">vtk.js ready</span>
              </div>
              <div className="viewer-frame">
                <div className="viewer-fake-mesh" />
                <p>Placeholder 3D result viewer with field overlays and color scale.</p>
              </div>
            </div>
          </section>
        )}

        {screen === "History" && (
          <section className="panel">
            <div className="card">
              <div className="section-head">
                <h3>Job History</h3>
                <span className="badge">{jobHistory.length} jobs</span>
              </div>
              <div className="history-grid">
                {jobHistory.length === 0 ? (
                  <p className="detail-copy">No jobs stored yet. Completed local runs will appear here.</p>
                ) : (
                  jobHistory.map((item) => (
                    <div key={item.id} className="history-card">
                      <strong>{item.id}</strong>
                      <span>{item.status}</span>
                      <span>{item.selectedSolver}</span>
                      <small>{item.rationale}</small>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
