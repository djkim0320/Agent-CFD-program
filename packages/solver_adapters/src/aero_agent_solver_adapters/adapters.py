from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import subprocess
from typing import IO

from aero_agent_common import json_dumps
from aero_agent_contracts import JobStatus, MetricRecord, SolverKind, SolverRunManifest


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SolverProbeResult:
    docker_ok: bool
    gmsh_ok: bool
    su2_image_ok: bool
    workspace_ok: bool
    issues: list[str]


@dataclass(slots=True)
class SolverRuntimeHandle:
    job_id: str
    solver: SolverKind
    runtime_backend: str
    case_dir: Path
    cfg_path: Path
    log_path: Path
    container_name: str | None = None
    process: subprocess.Popen[bytes] | None = None
    started_at: datetime = field(default_factory=utc_now)
    _log_stream: IO[bytes] | None = field(default=None, repr=False)


class SolverAdapterRegistry:
    def probe(self) -> SolverProbeResult:
        return self.probe_runtime()

    def probe_runtime(self) -> SolverProbeResult:
        docker_ok = shutil.which("docker") is not None
        gmsh_ok = shutil.which("gmsh") is not None or bool(os.getenv("AERO_AGENT_GMSH_PATH"))
        workspace_ok = self._probe_workspace()
        su2_image_ok = self._probe_su2_image(docker_ok=docker_ok)

        issues: list[str] = []
        if not docker_ok:
            issues.append("Docker not detected.")
        if not gmsh_ok:
            issues.append("gmsh not detected.")
        if not su2_image_ok:
            issues.append("Pinned SU2 Docker image not detected.")
        if not workspace_ok:
            issues.append("Workspace is not writable.")

        return SolverProbeResult(
            docker_ok=docker_ok,
            gmsh_ok=gmsh_ok,
            su2_image_ok=su2_image_ok,
            workspace_ok=workspace_ok,
            issues=issues,
        )

    def launch(self, job_id: str, case_dir: Path, cfg_path: Path, solver: SolverKind) -> SolverRuntimeHandle:
        if solver != SolverKind.SU2:
            raise ValueError(f"Unsupported solver for this release: {solver.value}")

        probe = self.probe_runtime()
        if probe.issues:
            raise RuntimeError("; ".join(probe.issues))

        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("Docker executable not found.")

        image = os.getenv("AERO_AGENT_SU2_IMAGE", "aero-agent-su2:latest")
        results_dir = case_dir.parent / "results"
        logs_dir = case_dir.parent / "logs"
        results_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_path = logs_dir / "solver.log"
        container_name = f"aero-agent-{job_id[:12]}"
        command = [
            docker,
            "run",
            "--name",
            container_name,
            "--rm",
            "-v",
            f"{case_dir}:/work",
            "-w",
            "/work",
            image,
            "sh",
            "-lc",
            f"SU2_CFD {cfg_path.name}",
        ]

        log_stream = log_path.open("wb")
        try:
            process = subprocess.Popen(command, stdout=log_stream, stderr=subprocess.STDOUT)
        except Exception:
            log_stream.close()
            raise

        return SolverRuntimeHandle(
            job_id=job_id,
            solver=solver,
            runtime_backend="docker",
            case_dir=case_dir,
            cfg_path=cfg_path,
            log_path=log_path,
            container_name=container_name,
            process=process,
            _log_stream=log_stream,
        )

    def wait(self, handle: SolverRuntimeHandle, timeout: float | None = None) -> SolverRunManifest:
        if handle.process is None:
            raise RuntimeError("Solver runtime handle has no process.")

        returncode = handle.process.wait(timeout=timeout)
        self._close_stream(handle)

        status = JobStatus.COMPLETED if returncode == 0 else JobStatus.FAILED
        metrics = []
        if status == JobStatus.COMPLETED:
            metrics = [
                MetricRecord(name="iterations", value=0.0),
            ]

        manifest = SolverRunManifest(
            solver=handle.solver,
            case_dir=str(handle.case_dir),
            runtime_backend="docker",
            run_id=handle.container_name,
            pid_or_container_id=handle.container_name,
            started_at=handle.started_at,
            finished_at=utc_now(),
            status=status,
            logs_path=str(handle.log_path),
            metrics=metrics,
            warnings=[],
        )
        manifest_path = handle.case_dir.parent / "results" / "solver_run_manifest.json"
        manifest_path.write_text(json_dumps(manifest.model_dump(mode="json")), encoding="utf-8")
        return manifest

    def terminate(self, handle: SolverRuntimeHandle, *, timeout_seconds: int = 10) -> None:
        docker = shutil.which("docker")
        if handle.container_name and docker is not None:
            subprocess.run(
                [docker, "stop", "-t", str(timeout_seconds), handle.container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=max(timeout_seconds + 5, 15),
            )
            if handle.process and handle.process.poll() is None:
                subprocess.run(
                    [docker, "kill", handle.container_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=15,
                )

        if handle.process and handle.process.poll() is None:
            handle.process.terminate()
            try:
                handle.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                handle.process.kill()
                handle.process.wait(timeout=5)

        self._close_stream(handle)

    def run(self, job_id: str, case_dir: Path, cfg_path: Path, solver: SolverKind) -> SolverRunManifest:
        handle = self.launch(job_id, case_dir, cfg_path, solver)
        return self.wait(handle)

    def _close_stream(self, handle: SolverRuntimeHandle) -> None:
        if handle._log_stream and not handle._log_stream.closed:
            handle._log_stream.flush()
            handle._log_stream.close()

    def _probe_workspace(self) -> bool:
        candidate_root = Path(os.getenv("AERO_AGENT_WORKSPACE_ROOT", Path.cwd()))
        try:
            candidate_root.mkdir(parents=True, exist_ok=True)
            probe_dir = candidate_root / ".aero_agent_workspace_probe"
            probe_dir.mkdir(exist_ok=True)
            marker = probe_dir / "write_test.txt"
            marker.write_text("ok", encoding="utf-8")
            marker.unlink(missing_ok=True)
            probe_dir.rmdir()
            return True
        except OSError:
            return False

    def _probe_su2_image(self, *, docker_ok: bool) -> bool:
        image = os.getenv("AERO_AGENT_SU2_IMAGE", "aero-agent-su2:latest")
        if not docker_ok:
            return False
        docker = shutil.which("docker")
        if docker is None:
            return False
        try:
            completed = subprocess.run(
                [docker, "image", "inspect", image],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0
