import type {
  AnalysisJob,
  AnalysisRequest,
  ConnectionStatus,
  JobEvent,
  PreflightPlan,
} from "./types";

const now = () => new Date().toISOString();

export const createMockConnection = (mode: ConnectionStatus["mode"] = "openai_api"): ConnectionStatus => ({
  connected: true,
  mode,
  providerReady: true,
  backend: "local-mock",
  warnings: ["Backend API not reachable yet. Using local fallback state."],
});

export const createMockPlan = (request: AnalysisRequest): PreflightPlan => {
  const selectedSolver =
    request.solverPreference !== "auto"
      ? request.solverPreference
      : request.geometryFile?.name.toLowerCase().includes("vsp")
        ? "vspaero"
        : request.fidelity === "high"
          ? "openfoam"
          : "su2";

  return {
    selectedSolver,
    candidateSolvers: ["su2", "openfoam", "vspaero"],
    runtimeEstimate:
      selectedSolver === "openfoam" ? "90-180 min" : selectedSolver === "su2" ? "30-90 min" : "2-15 min",
    memoryEstimate:
      selectedSolver === "openfoam" ? "8-16 GB" : selectedSolver === "su2" ? "4-8 GB" : "1-2 GB",
    confidence: selectedSolver === "openfoam" ? 0.78 : selectedSolver === "su2" ? 0.84 : 0.71,
    warnings: request.geometryFile ? [] : ["Upload a geometry file before running analysis."],
    rationale:
      selectedSolver === "vspaero"
        ? "Aircraft-style geometry detected, so a lifting-surface solver is the fastest fit."
        : selectedSolver === "openfoam"
          ? "Higher-fidelity separation analysis is better served by OpenFOAM."
          : "Watertight general 3D geometry maps well to SU2's steady external aero workflow.",
  };
};

export const createMockJob = (
  request: AnalysisRequest,
  plan: PreflightPlan,
): { job: AnalysisJob; events: JobEvent[] } => {
  const jobId = `job_${Math.random().toString(36).slice(2, 8)}`;
  const events: JobEvent[] = [
    {
      id: `evt_${Math.random().toString(36).slice(2, 8)}`,
      type: "preflight.started",
      message: "Preflight analysis started.",
      timestamp: now(),
      progress: 10,
    },
    {
      id: `evt_${Math.random().toString(36).slice(2, 8)}`,
      type: "subagent.completed",
      message: "geometry-triage completed.",
      timestamp: now(),
      progress: 25,
    },
    {
      id: `evt_${Math.random().toString(36).slice(2, 8)}`,
      type: "approval.required",
      message: "Manual approval requested before solver execution.",
      timestamp: now(),
      progress: 40,
    },
    {
      id: `evt_${Math.random().toString(36).slice(2, 8)}`,
      type: "tool.started",
      message: `Preparing ${plan.selectedSolver} case.`,
      timestamp: now(),
      progress: 60,
    },
    {
      id: `evt_${Math.random().toString(36).slice(2, 8)}`,
      type: "solver.stdout",
      message: "Residuals trending downward. Mesh quality within tolerance.",
      timestamp: now(),
      progress: 78,
    },
    {
      id: `evt_${Math.random().toString(36).slice(2, 8)}`,
      type: "report.ready",
      message: "HTML report and viewer assets are ready.",
      timestamp: now(),
      progress: 100,
    },
  ];

  const job: AnalysisJob = {
    id: jobId,
    status: "completed",
    selectedSolver: plan.selectedSolver,
    rationale: plan.rationale,
    progress: 100,
    warnings: [
      request.geometryFile ? "" : "No geometry uploaded yet.",
      "Mock run used until backend is connected.",
    ].filter(Boolean),
    artifacts: [
      { name: "report.html", path: `data/jobs/${jobId}/report/index.html` },
      { name: "viewer.vtm", path: `data/jobs/${jobId}/viewer/result.vtm` },
      { name: "summary.json", path: `data/jobs/${jobId}/results/summary.json` },
    ],
    metrics: {
      CL: 0.42,
      CD: 0.031,
      Cm: -0.08,
      Convergence: "good",
    },
  };

  return { job, events };
};
