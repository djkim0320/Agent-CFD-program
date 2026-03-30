from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC, datetime
from pathlib import Path
import queue
import threading
from typing import Any

from aero_agent_cfd_core import CFDCore, CFDResults, CaseManifest, MaterializedSnapshot
from aero_agent_contracts import (
    EventType,
    JobEventRecord,
    JobRecord,
    JobStatus,
    PreflightSnapshot,
    ReportManifest,
    SnapshotStatus,
    ViewerManifest,
)
from aero_agent_solver_adapters import SolverRuntimeHandle


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class ActiveRun:
    job_id: str
    phase: str
    mesh_handle: SolverRuntimeHandle | None = None
    solver_handle: SolverRuntimeHandle | None = None
    cancel_requested: bool = False
    started_at: datetime = field(default_factory=utc_now)


class JobExecutionService:
    def __init__(self, repository: Any, broker: Any, cfd_core: CFDCore, data_dir: Path):
        self.repository = repository
        self.broker = broker
        self.cfd_core = cfd_core
        self.data_dir = data_dir
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._active_runs: dict[str, ActiveRun] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="aero-agent-worker", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._queue.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def recover_interrupted_jobs(self) -> None:
        for job in self.repository.list_jobs():
            if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.POSTPROCESSING}:
                continue
            job.status = JobStatus.FAILED
            job.error = "Interrupted during application shutdown; rerun required."
            job.failed_at = utc_now()
            self._persist_job_and_event(
                job,
                EventType.JOB_FAILED,
                {"message": job.error, "status": job.status.value},
            )

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def request_cancel(self, job_id: str) -> None:
        with self._lock:
            active = self._active_runs.get(job_id)
            if not active:
                return
            active.cancel_requested = True
            mesh_handle = active.mesh_handle
            handle = active.solver_handle
        if mesh_handle is not None:
            self.cfd_core.terminate_solver(mesh_handle)
        if handle is not None:
            self.cfd_core.terminate_solver(handle)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue

            if job_id is None:
                self._queue.task_done()
                continue

            try:
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)
        if not job:
            return
        if job.status == JobStatus.CANCELLED:
            return

        snapshot = self.repository.get_preflight_snapshot(job.preflight_snapshot_id)
        if snapshot is None:
            self._fail_job(job, "Referenced preflight snapshot was not found.")
            return

        try:
            self._verify_snapshot(snapshot)
            self._consume_snapshot(snapshot, job.id)
            job.started_at = utc_now()
            job.status = JobStatus.RUNNING
            job.progress = 15
            self._persist_job_and_event(job, EventType.JOB_STATUS, {"status": job.status.value, "progress": job.progress})

            job_dir = self._job_dir(job.id)
            snapshot_dir = self._snapshot_dir(snapshot.id)
            materialized = self.cfd_core.materialize_snapshot(
                snapshot_dir,
                job_dir,
                source_file_name=snapshot.source_file_name,
            )

            with self._lock:
                self._active_runs[job.id] = ActiveRun(job_id=job.id, phase="prepare_case")

            case_manifest = self._prepare_case(job, job_dir, materialized)
            self._check_cancel(job)
            self._generate_mesh(job, case_manifest)
            self._check_cancel(job)
            run_manifest = self._run_solver(job, case_manifest)
            self._check_cancel(job)
            results, report, viewer, artifacts = self._postprocess(job, job_dir, run_manifest)
            self._complete_job(job, results, artifacts)
            self._emit_artifact_events(job.id, artifacts, report)
        except CancelledError as exc:
            current = self.repository.get_job(job.id) or job
            current.status = JobStatus.CANCELLED
            current.cancelled_at = utc_now()
            current.error = str(exc)
            self._persist_job_and_event(
                current,
                EventType.JOB_CANCELLED,
                {"message": str(exc), "status": current.status.value},
            )
        except Exception as exc:  # pragma: no cover - runtime guard
            current = self.repository.get_job(job.id) or job
            current.status = JobStatus.FAILED
            current.failed_at = utc_now()
            current.error = str(exc)
            self._persist_job_and_event(
                current,
                EventType.JOB_FAILED,
                {"message": str(exc), "status": current.status.value},
            )
        finally:
            with self._lock:
                self._active_runs.pop(job.id, None)

    def _prepare_case(
        self,
        job: JobRecord,
        job_dir: Path,
        materialized: MaterializedSnapshot,
    ) -> CaseManifest:
        job.progress = 25
        self._persist_job_and_event(
            job,
            EventType.TOOL_STARTED,
            {"tool": "case.prepare", "progress": job.progress, "message": "Preparing SU2 case files."},
        )
        case_manifest = self.cfd_core.prepare_case(
            job_id=job.id,
            job_dir=job_dir,
            request=job.request,
            normalized_geometry_path=materialized.normalized_geometry_path,
            normalized_manifest_path=materialized.normalized_manifest_path,
            normalization_manifest_path=materialized.normalization_manifest_path,
            selected_solver=job.selected_solver,
        )
        self._persist_event(
            job.id,
            EventType.TOOL_COMPLETED,
            {"tool": "case.prepare", "case_dir": str(case_manifest.case_dir)},
        )
        with self._lock:
            if job.id in self._active_runs:
                self._active_runs[job.id].phase = "mesh.generate"
        return case_manifest

    def _generate_mesh(self, job: JobRecord, case_manifest: CaseManifest) -> None:
        job.progress = 40
        self._persist_job_and_event(
            job,
            EventType.TOOL_STARTED,
            {"tool": "mesh.generate", "progress": job.progress, "message": "Generating mesh with gmsh."},
        )
        handle = self.cfd_core.launch_mesh(job_id=job.id, case_manifest=case_manifest)
        with self._lock:
            if job.id in self._active_runs:
                self._active_runs[job.id].mesh_handle = handle
                self._active_runs[job.id].phase = "meshing"
        try:
            mesh_path = self.cfd_core.wait_for_mesh(handle, case_manifest=case_manifest)
        except Exception:
            self._check_cancel(job)
            raise
        self._persist_event(
            job.id,
            EventType.TOOL_COMPLETED,
            {"tool": "mesh.generate", "mesh_path": str(mesh_path)},
        )
        with self._lock:
            if job.id in self._active_runs:
                self._active_runs[job.id].mesh_handle = None
                self._active_runs[job.id].phase = "solver.run"

    def _run_solver(self, job: JobRecord, case_manifest: CaseManifest):
        job.progress = 60
        self._persist_job_and_event(
            job,
            EventType.TOOL_STARTED,
            {"tool": "solver.run", "progress": job.progress, "message": "Running SU2 in Docker."},
        )
        handle = self.cfd_core.launch_solver(job_id=job.id, case_manifest=case_manifest)
        with self._lock:
            if job.id in self._active_runs:
                self._active_runs[job.id].solver_handle = handle
        try:
            run_manifest = self.cfd_core.wait_for_solver(handle)
        except Exception:
            self._check_cancel(job)
            raise
        if run_manifest.status != JobStatus.COMPLETED:
            self._check_cancel(job)
            raise RuntimeError(f"Solver execution failed. Log: {run_manifest.logs_path}")
        self._persist_event(
            job.id,
            EventType.SOLVER_STDOUT,
            {"message": "Solver execution completed.", "logs_path": run_manifest.logs_path},
        )
        return run_manifest

    def _postprocess(
        self,
        job: JobRecord,
        job_dir: Path,
        run_manifest,
    ) -> tuple[CFDResults, ReportManifest, ViewerManifest, list]:
        job.status = JobStatus.POSTPROCESSING
        job.progress = 82
        self._persist_job_and_event(
            job,
            EventType.JOB_STATUS,
            {"status": job.status.value, "progress": job.progress, "message": "Extracting results and building report."},
        )
        results = self.cfd_core.extract_results(job_dir=job_dir, run_manifest=run_manifest)
        report = self.cfd_core.build_report(job_id=job.id, job_dir=job_dir, results=results)
        viewer = self.cfd_core.build_viewer(job_id=job.id, job_dir=job_dir, results=results)
        case_bundle = self.cfd_core.package_case_bundle(job_dir=job_dir)
        artifacts = self.cfd_core.build_artifacts(results=results, report=report, viewer=viewer, case_bundle=case_bundle)
        self._persist_event(
            job.id,
            EventType.SOLVER_METRICS,
            {
                "metrics": {metric.name: metric.value for metric in results.metrics},
                "residual_history_points": len(results.residual_history),
            },
        )
        return results, report, viewer, artifacts

    def _complete_job(self, job: JobRecord, results: CFDResults, artifacts: list) -> None:
        job.status = JobStatus.COMPLETED
        job.progress = 100
        job.completed_at = utc_now()
        job.metrics = list(results.metrics)
        job.artifacts = list(artifacts)
        self._persist_job_and_event(
            job,
            EventType.JOB_COMPLETED,
            {"status": job.status.value, "progress": job.progress, "message": "Analysis completed."},
        )

    def _emit_artifact_events(self, job_id: str, artifacts: list, report: ReportManifest) -> None:
        for artifact in artifacts:
            self._persist_event(
                job_id,
                EventType.ARTIFACT_READY,
                {"artifact": artifact.model_dump(mode="json")},
            )
        self._persist_event(
            job_id,
            EventType.REPORT_READY,
            {"report_path": report.html_path, "summary_path": report.json_path},
        )

    def _fail_job(self, job: JobRecord, message: str) -> None:
        job.status = JobStatus.FAILED
        job.failed_at = utc_now()
        job.error = message
        self._persist_job_and_event(job, EventType.JOB_FAILED, {"message": message, "status": job.status.value})

    def _verify_snapshot(self, snapshot: PreflightSnapshot) -> None:
        if snapshot.status == SnapshotStatus.EXPIRED:
            raise RuntimeError("Preflight snapshot expired.")
        snapshot_dir = self._snapshot_dir(snapshot.id)
        if not snapshot_dir.exists():
            raise RuntimeError("Preflight snapshot directory is missing.")
        source_path = self.data_dir / snapshot.source_file_relpath
        normalized_manifest_path = self.data_dir / snapshot.normalized_manifest_relpath
        normalized_geometry_path = self.data_dir / snapshot.normalized_geometry_relpath
        if not source_path.exists():
            raise RuntimeError("Preflight snapshot source file is missing.")
        if not normalized_manifest_path.exists():
            raise RuntimeError("Preflight snapshot manifest is missing.")
        if not normalized_geometry_path.exists():
            raise RuntimeError("Preflight snapshot normalized geometry is missing.")
        if self.cfd_core.compute_sha256(source_path) != snapshot.source_hash:
            raise RuntimeError("Preflight snapshot source hash mismatch.")
        if self.cfd_core.compute_sha256(normalized_manifest_path) != snapshot.normalized_manifest_hash:
            raise RuntimeError("Preflight snapshot manifest hash mismatch.")
        if self.cfd_core.compute_sha256(normalized_geometry_path) != snapshot.normalized_geometry_hash:
            raise RuntimeError("Preflight snapshot normalized geometry hash mismatch.")

    def _consume_snapshot(self, snapshot: PreflightSnapshot, job_id: str) -> None:
        snapshot.status = SnapshotStatus.CONSUMED
        snapshot.consumed_by_job_id = job_id
        snapshot.consumed_at = utc_now()
        self.repository.update_preflight_snapshot(snapshot)

    def _check_cancel(self, job: JobRecord) -> None:
        current = self.repository.get_job(job.id)
        if current and current.cancel_requested_at:
            raise CancelledError("Job cancelled by user.")

    def _persist_job_and_event(self, job: JobRecord, event_type: EventType, payload: dict[str, Any]) -> None:
        job.updated_at = utc_now()
        self.repository.update_job(job)
        self._persist_event(job.id, event_type, payload)

    def _persist_event(self, job_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
        event = JobEventRecord(
            job_id=job_id,
            seq=self.repository.next_event_seq(job_id),
            event_type=event_type,
            payload=payload,
            created_at=utc_now(),
        )
        stored = self.repository.add_event(event)
        self.broker.publish_from_thread(job_id, stored.model_dump(mode="json"))

    def _snapshot_dir(self, snapshot_id: str) -> Path:
        return self.data_dir / "snapshots" / snapshot_id

    def _job_dir(self, job_id: str) -> Path:
        path = self.data_dir / "jobs" / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path


class CancelledError(RuntimeError):
    pass
