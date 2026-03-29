from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil

from aero_agent_common import json_dumps
from aero_agent_contracts import JobStatus, MetricRecord, SolverKind, SolverRunManifest


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SolverProbeResult:
    docker_ok: bool
    su2_ok: bool
    openfoam_ok: bool
    vspaero_ok: bool
    issues: list[str]


class SolverAdapterRegistry:
    def probe(self) -> SolverProbeResult:
        docker_ok = shutil.which("docker") is not None
        return SolverProbeResult(
            docker_ok=docker_ok,
            su2_ok=docker_ok,
            openfoam_ok=docker_ok,
            vspaero_ok=True,
            issues=[] if docker_ok else ["Docker not detected; solver execution will stay in deterministic mock mode."],
        )

    def run(self, job_id: str, case_dir: Path, solver: SolverKind) -> SolverRunManifest:
        results_dir = case_dir.parent / "results"
        logs_dir = case_dir.parent / "logs"
        results_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "solver.log"
        log_path.write_text(
            f"[{utc_now().isoformat()}] Running {solver.value} in deterministic scaffold mode for job {job_id}\n",
            encoding="utf-8",
        )
        run_manifest_path = results_dir / "solver_run_manifest.json"
        run_manifest = SolverRunManifest(
            solver=solver,
            case_dir=str(case_dir),
            runtime_backend="mock",
            run_id=f"{solver.value}-{job_id}",
            pid_or_container_id=f"mock-{job_id[:8]}",
            started_at=utc_now(),
            finished_at=utc_now(),
            status=JobStatus.COMPLETED,
            logs_path=str(log_path),
            metrics=[
                MetricRecord(name="iterations", value=250),
                MetricRecord(name="residual", value=1.2e-5),
            ],
            warnings=["Deterministic scaffold run. Replace with real solver adapter."],
        )
        run_manifest_path.write_text(json_dumps(run_manifest.model_dump(mode="json")), encoding="utf-8")
        return run_manifest
