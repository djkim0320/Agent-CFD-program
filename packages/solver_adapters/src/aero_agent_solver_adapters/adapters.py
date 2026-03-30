from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
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


class ExternalRuntimeKind(str, Enum):
    GMSH = "gmsh"
    SU2 = "su2"


@dataclass(slots=True)
class SolverRuntimeHandle:
    job_id: str
    runtime_backend: str
    case_dir: Path
    log_path: Path
    solver: SolverKind | None = None
    cfg_path: Path | None = None
    runtime_kind: ExternalRuntimeKind = ExternalRuntimeKind.SU2
    output_path: Path | None = None
    manifest_path: Path | None = None
    container_name: str | None = None
    command: list[str] = field(default_factory=list, repr=False)
    process: subprocess.Popen[bytes] | None = None
    started_at: datetime = field(default_factory=utc_now)
    _log_stream: IO[bytes] | None = field(default=None, repr=False)


@dataclass(slots=True)
class GmshRunManifest:
    runtime_kind: ExternalRuntimeKind
    case_dir: str
    runtime_backend: str
    run_id: str | None
    pid_or_container_id: str | None
    started_at: datetime
    finished_at: datetime
    status: JobStatus
    logs_path: str
    mesh_path: str | None = None
    command: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SolverAdapterRegistry:
    def probe(self) -> SolverProbeResult:
        return self.probe_runtime()

    def probe_runtime(self) -> SolverProbeResult:
        docker_ok = self.resolve_docker_binary() is not None
        gmsh_ok = self.resolve_gmsh_binary() is not None
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

        docker = self.resolve_docker_binary()
        if docker is None:
            raise RuntimeError("Docker executable not found.")

        image = os.getenv("AERO_AGENT_SU2_IMAGE", "aero-agent-su2:latest")
        results_dir = case_dir.parent / "results"
        logs_dir = case_dir.parent / "logs"
        results_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_path = logs_dir / "solver.log"
        container_name = f"aero-agent-{job_id[:12]}"
        command = self.build_su2_command(
            docker=docker,
            image=image,
            container_name=container_name,
            case_dir=case_dir,
            cfg_path=cfg_path,
        )

        return self._launch_runtime(
            job_id=job_id,
            runtime_backend="docker",
            case_dir=case_dir,
            log_path=log_path,
            solver=solver,
            cfg_path=cfg_path,
            runtime_kind=ExternalRuntimeKind.SU2,
            container_name=container_name,
            command=command,
        )

    def wait(self, handle: SolverRuntimeHandle, timeout: float | None = None) -> SolverRunManifest:
        if handle.process is None:
            raise RuntimeError("Solver runtime handle has no process.")

        return self._wait_solver_runtime(handle, timeout=timeout)

    def terminate(self, handle: SolverRuntimeHandle, *, timeout_seconds: int = 10) -> None:
        docker = self.resolve_docker_binary()
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

    def resolve_gmsh_binary(self) -> str | None:
        return shutil.which("gmsh") or os.getenv("AERO_AGENT_GMSH_PATH")

    def resolve_docker_binary(self) -> str | None:
        return shutil.which("docker")

    def build_gmsh_command(self, *, gmsh: str, input_path: Path, output_path: Path) -> list[str]:
        return [
            gmsh,
            str(input_path),
            "-3",
            "-format",
            "su2",
            "-o",
            str(output_path),
        ]

    def build_su2_command(
        self,
        *,
        docker: str,
        image: str,
        container_name: str,
        case_dir: Path,
        cfg_path: Path,
    ) -> list[str]:
        return [
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

    def launch_gmsh(
        self,
        job_id: str,
        input_path: Path,
        output_path: Path,
        *,
        work_dir: Path | None = None,
        log_path: Path | None = None,
        manifest_path: Path | None = None,
    ) -> SolverRuntimeHandle:
        gmsh = self.resolve_gmsh_binary()
        if gmsh is None:
            raise RuntimeError("gmsh not detected.")

        work_dir = work_dir or output_path.parent
        work_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_path or (work_dir / "gmsh.log")
        manifest_path = manifest_path or (work_dir / "gmsh_run_manifest.json")
        command = self.build_gmsh_command(gmsh=gmsh, input_path=input_path, output_path=output_path)
        return self._launch_runtime(
            job_id=job_id,
            runtime_backend="local",
            case_dir=work_dir,
            log_path=log_path,
            solver=None,
            cfg_path=input_path,
            runtime_kind=ExternalRuntimeKind.GMSH,
            output_path=output_path,
            manifest_path=manifest_path,
            command=command,
        )

    def wait_gmsh(self, handle: SolverRuntimeHandle, timeout: float | None = None) -> GmshRunManifest:
        return self._wait_gmsh_runtime(handle, timeout=timeout)

    def terminate_gmsh(self, handle: SolverRuntimeHandle, *, timeout_seconds: int = 10) -> None:
        self.terminate(handle, timeout_seconds=timeout_seconds)

    def _close_stream(self, handle: SolverRuntimeHandle) -> None:
        if handle._log_stream and not handle._log_stream.closed:
            handle._log_stream.flush()
            handle._log_stream.close()

    def _launch_runtime(
        self,
        *,
        job_id: str,
        runtime_backend: str,
        case_dir: Path,
        log_path: Path,
        solver: SolverKind | None,
        cfg_path: Path | None,
        runtime_kind: ExternalRuntimeKind,
        output_path: Path | None = None,
        manifest_path: Path | None = None,
        container_name: str | None = None,
        command: list[str],
    ) -> SolverRuntimeHandle:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_stream = log_path.open("wb")
        try:
            process = subprocess.Popen(command, stdout=log_stream, stderr=subprocess.STDOUT)
        except Exception:
            log_stream.close()
            raise

        return SolverRuntimeHandle(
            job_id=job_id,
            runtime_backend=runtime_backend,
            case_dir=case_dir,
            log_path=log_path,
            solver=solver,
            cfg_path=cfg_path,
            runtime_kind=runtime_kind,
            output_path=output_path,
            manifest_path=manifest_path,
            container_name=container_name,
            command=command,
            process=process,
            _log_stream=log_stream,
        )

    def _wait_solver_runtime(self, handle: SolverRuntimeHandle, timeout: float | None = None) -> SolverRunManifest:
        returncode = self._wait_process(handle, timeout=timeout)
        self._close_stream(handle)

        status = JobStatus.COMPLETED if returncode == 0 else JobStatus.FAILED
        metrics = []
        if status == JobStatus.COMPLETED:
            metrics = [
                MetricRecord(name="iterations", value=0.0),
            ]

        manifest = SolverRunManifest(
            solver=handle.solver or SolverKind.SU2,
            case_dir=str(handle.case_dir),
            runtime_backend=handle.runtime_backend,
            run_id=handle.container_name,
            pid_or_container_id=handle.container_name,
            started_at=handle.started_at,
            finished_at=utc_now(),
            status=status,
            logs_path=str(handle.log_path),
            metrics=metrics,
            warnings=[],
        )
        manifest_path = handle.manifest_path or (handle.case_dir.parent / "results" / "solver_run_manifest.json")
        manifest_path.write_text(json_dumps(manifest.model_dump(mode="json")), encoding="utf-8")
        return manifest

    def _wait_gmsh_runtime(self, handle: SolverRuntimeHandle, timeout: float | None = None) -> GmshRunManifest:
        returncode = self._wait_process(handle, timeout=timeout)
        self._close_stream(handle)

        status = JobStatus.COMPLETED if returncode == 0 else JobStatus.FAILED
        manifest = GmshRunManifest(
            runtime_kind=ExternalRuntimeKind.GMSH,
            case_dir=str(handle.case_dir),
            runtime_backend=handle.runtime_backend,
            run_id=handle.container_name,
            pid_or_container_id=str(handle.process.pid) if handle.process else None,
            started_at=handle.started_at,
            finished_at=utc_now(),
            status=status,
            logs_path=str(handle.log_path),
            mesh_path=str(handle.output_path) if handle.output_path else None,
            command=list(handle.command),
            warnings=[],
        )
        manifest_path = handle.manifest_path or (handle.case_dir / "gmsh_run_manifest.json")
        manifest_path.write_text(json_dumps(manifest.model_dump(mode="json")), encoding="utf-8")
        return manifest

    def _wait_process(self, handle: SolverRuntimeHandle, timeout: float | None = None) -> int:
        if handle.process is None:
            raise RuntimeError("Solver runtime handle has no process.")
        return handle.process.wait(timeout=timeout)

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
