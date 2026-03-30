from __future__ import annotations

import asyncio
import csv
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from aero_agent_contracts import (
    AIAssistMode,
    ArtifactKind,
    ConnectionMode,
    ConnectionRecord,
    ConnectionStatusResponse,
    EventType,
    ExecutionMode,
    GeometryTriageFinding,
    JobEventRecord,
    JobRecord,
    JobStatus,
    JobSummaryResponse,
    PreflightResponse,
    PreflightSnapshot,
    ProviderBackend,
    SnapshotStatus,
    SolverPlannerFinding,
    SubagentFindings,
    AuthPolicyFinding,
)

from .dependencies import (
    get_cfd_core,
    get_codex_provider,
    get_data_dir,
    get_event_broker,
    get_install_manager,
    get_job_service,
    get_openai_provider,
    get_repository,
)
from .models import ArtifactPayload, CreateConnectionRequest, CreateJobFromPreflightRequest, PreflightMultipartForm


SNAPSHOT_TTL_HOURS = 72


@asynccontextmanager
async def lifespan(_: FastAPI):
    repo = get_repository()
    broker = get_event_broker()
    broker.bind_loop(asyncio.get_running_loop())
    cleanup_expired_snapshots(repo)
    worker = get_job_service()
    worker.recover_interrupted_jobs()
    worker.start()
    yield
    worker.shutdown()


app = FastAPI(title="Aero Agent Local API", version="0.2.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/install/status")
def install_status() -> dict[str, Any]:
    status = get_install_manager().check()
    return {
        "docker_ok": status.docker_ok,
        "gmsh_ok": status.gmsh_ok,
        "su2_image_ok": status.su2_image_ok,
        "workspace_ok": status.workspace_ok,
        "install_warnings": status.install_warnings,
    }


@app.get("/api/v1/connections/status")
def connection_status_alias(mode: ConnectionMode = Query(...)) -> ConnectionStatusResponse:
    return build_connection_status_response(mode.value, mode)


@app.post("/api/v1/connections")
def create_connection(payload: CreateConnectionRequest) -> ConnectionRecord:
    repo = get_repository()
    status = build_connection_status_response(payload.mode.value, payload.mode)
    record = ConnectionRecord(
        id=payload.mode.value,
        mode=payload.mode,
        label=payload.label or payload.mode.value,
        status="ready" if status.provider_ready else "missing",
        data_policy=payload.data_policy,
        metadata={
            "backend": status.backend.value,
            "warnings": status.warnings,
            **(payload.credentials_hint or {}),
        },
        last_validated_at=utc_now(),
    )
    repo.upsert_connection(record)
    return record


@app.get("/api/v1/connections")
def list_connections() -> list[ConnectionRecord]:
    return get_repository().list_connections()


@app.get("/api/v1/connections/{connection_id}")
def get_connection(connection_id: str) -> ConnectionRecord:
    connection = get_repository().get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="connection not found")
    return connection


@app.get("/api/v1/connections/{connection_id}/status")
def connection_status(connection_id: str) -> ConnectionStatusResponse:
    connection = get_repository().get_connection(connection_id)
    if connection:
        return build_connection_status_response(connection.id, connection.mode)
    if connection_id in {ConnectionMode.OPENAI_API.value, ConnectionMode.CODEX_OAUTH.value}:
        return build_connection_status_response(connection_id, ConnectionMode(connection_id))
    raise HTTPException(status_code=404, detail="connection not found")


@app.get("/api/v1/jobs")
def list_jobs() -> list[JobSummaryResponse]:
    return [to_job_summary(job) for job in get_repository().list_jobs()]


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> JobSummaryResponse:
    job = get_required_job_record(job_id)
    return to_job_summary(job)


@app.get("/api/v1/jobs/{job_id}/history")
def job_history(job_id: str) -> list[JobEventRecord]:
    ensure_job_exists(job_id)
    return get_repository().list_events(job_id)


@app.get("/api/v1/jobs/{job_id}/events")
async def job_events(job_id: str):
    ensure_job_exists(job_id)
    repo = get_repository()
    existing = repo.list_events(job_id)
    broker = get_event_broker()
    queue = await broker.subscribe(job_id)

    async def stream():
        try:
            for event in existing:
                yield {"event": str(event.event_type), "data": event.model_dump_json(), "id": str(event.id or event.seq)}
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": str(event["event_type"]), "data": json.dumps(event), "id": str(event.get("seq", ""))}
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": json.dumps({"job_id": job_id})}
        finally:
            await broker.unsubscribe(job_id, queue)

    return EventSourceResponse(stream())


@app.post("/api/v1/jobs/preflight")
async def create_preflight(
    form: PreflightMultipartForm = Depends(PreflightMultipartForm.as_form),
    geometry_file: UploadFile = File(...),
) -> PreflightResponse:
    repo = get_repository()
    cleanup_expired_snapshots(repo)
    connection = ensure_connection(form.connection_mode, form.connection_id)

    preflight_id = str(uuid4())
    snapshot_dir = get_data_dir() / "snapshots" / preflight_id
    source_path = await persist_upload(snapshot_dir / "input" / "original", geometry_file)
    request = form.to_analysis_request(str(source_path))

    install = get_install_manager().check()
    bundle = get_cfd_core().run_preflight(
        request,
        source_path,
        install_status=install,  # type: ignore[arg-type]
        connection_mode=connection.mode,
    )
    provider_status = build_connection_status_response(connection.id, connection.mode)
    subagent_findings, ai_assist_mode, ai_warnings, policy_warnings = run_preflight_subagents(
        connection.mode,
        provider_status,
        bundle,
    )

    normalized_dir = snapshot_dir / "normalized"
    preflight_dir = snapshot_dir / "preflight"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    preflight_dir.mkdir(parents=True, exist_ok=True)

    request_digest = digest_payload(request.model_dump(mode="json"))
    source_hash = get_cfd_core().compute_sha256(source_path)
    normalization_summary: dict[str, Any] = {}
    normalization_manifest_relpath = ""
    normalized_geometry_relpath = ""
    normalized_geometry_hash = ""
    normalization_artifacts = None
    if bundle.geometry_manifest.geometry_kind == bundle.geometry_manifest.geometry_kind.GENERAL_3D:
        try:
            normalization_artifacts = get_cfd_core().normalize_geometry_artifacts(
                request=request,
                source_file_path=source_path,
                geometry_manifest=bundle.geometry_manifest,
                repair_result=bundle.repair_result,
                output_dir=normalized_dir,
            )
            normalization_summary = normalization_artifacts.summary
            normalization_manifest_relpath = str(normalization_artifacts.normalization_manifest_path.relative_to(get_data_dir()))
            normalized_geometry_relpath = str(normalization_artifacts.geometry_path.relative_to(get_data_dir()))
            normalized_geometry_hash = normalization_artifacts.geometry_hash
        except Exception as exc:
            bundle.runtime_blockers = unique_strings(bundle.runtime_blockers + [f"Geometry normalization failed: {exc}"])
            bundle.execution_mode = ExecutionMode.SCAFFOLD
            normalization_summary = {"caveats": [str(exc)]}

    normalized_manifest_path = normalized_dir / "normalized_manifest.json"
    normalized_manifest_path.write_text(
        json.dumps(
            get_cfd_core().normalized_manifest_payload(
                bundle,
                normalization_summary=normalization_summary or None,
                ai_assist_mode=ai_assist_mode,
            ),
            indent=2,
            ensure_ascii=True,
            default=str,
        ),
        encoding="utf-8",
    )
    normalized_manifest_hash = get_cfd_core().compute_sha256(normalized_manifest_path)

    plan_path = preflight_dir / "plan.json"
    plan_path.write_text(
        get_cfd_core().build_preflight_plan(bundle).model_dump_json(indent=2),
        encoding="utf-8",
    )
    findings_path = preflight_dir / "subagent_findings.json"
    findings_path.write_text(subagent_findings.model_dump_json(indent=2), encoding="utf-8")
    integrity_path = preflight_dir / "integrity.json"
    integrity_path.write_text(
        json.dumps(
            {
                "request_digest": request_digest,
                "source_hash": source_hash,
                "normalized_manifest_hash": normalized_manifest_hash,
                "normalized_geometry_hash": normalized_geometry_hash,
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    snapshot = PreflightSnapshot(
        id=preflight_id,
        connection_id=connection.id,
        status=SnapshotStatus.READY,
        source_file_name=geometry_file.filename or source_path.name,
        source_file_relpath=str(source_path.relative_to(get_data_dir())),
        normalized_manifest_relpath=str(normalized_manifest_path.relative_to(get_data_dir())),
        normalization_manifest_relpath=normalization_manifest_relpath,
        normalized_geometry_relpath=normalized_geometry_relpath,
        preflight_plan_relpath=str(plan_path.relative_to(get_data_dir())),
        subagent_findings_relpath=str(findings_path.relative_to(get_data_dir())),
        request=request,
        request_digest=request_digest,
        source_hash=source_hash,
        normalized_manifest_hash=normalized_manifest_hash,
        normalized_geometry_hash=normalized_geometry_hash,
        selected_solver=bundle.solver_selection.selected_solver,
        execution_mode=bundle.execution_mode,
        ai_assist_mode=ai_assist_mode,
        runtime_blockers=list(bundle.runtime_blockers),
        install_warnings=list(bundle.install_warnings),
        ai_warnings=list(ai_warnings),
        policy_warnings=list(policy_warnings),
        created_at=utc_now(),
        expires_at=utc_now() + timedelta(hours=SNAPSHOT_TTL_HOURS),
    )
    repo.create_preflight_snapshot(snapshot)
    return get_cfd_core().build_preflight_response(
        bundle,
        snapshot_id=preflight_id,
        subagent_findings=subagent_findings,
        ai_assist_mode=ai_assist_mode,
        ai_warnings=ai_warnings,
        policy_warnings=policy_warnings,
        request_digest=request_digest,
        source_hash=source_hash,
        normalized_manifest_hash=normalized_manifest_hash,
        normalized_geometry_hash=normalized_geometry_hash,
        normalization_summary=normalization_summary,
    )


@app.post("/api/v1/jobs")
def create_job(payload: CreateJobFromPreflightRequest) -> JobSummaryResponse:
    repo = get_repository()
    snapshot = repo.get_preflight_snapshot(payload.preflight_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="preflight snapshot not found")
    if snapshot.status == SnapshotStatus.EXPIRED or snapshot.expires_at <= utc_now():
        raise HTTPException(status_code=409, detail="preflight snapshot expired")
    if snapshot.status == SnapshotStatus.CONSUMED:
        raise HTTPException(status_code=409, detail="preflight snapshot already consumed")

    source_path = get_data_dir() / snapshot.source_file_relpath
    job = JobRecord(
        connection_id=snapshot.connection_id,
        preflight_snapshot_id=snapshot.id,
        status=JobStatus.WAITING_APPROVAL,
        selected_solver=snapshot.selected_solver,
        execution_mode=snapshot.execution_mode,
        ai_assist_mode=snapshot.ai_assist_mode,
        rationale=f"Preflight selected {snapshot.selected_solver.value}.",
        progress=50,
        runtime_blockers=list(snapshot.runtime_blockers),
        install_warnings=list(snapshot.install_warnings),
        ai_warnings=list(snapshot.ai_warnings),
        policy_warnings=list(snapshot.policy_warnings),
        request=snapshot.request,
        source_file_name=snapshot.source_file_name,
        source_file_path=str(source_path),
    )
    repo.create_job(job)
    persist_event_sync(job.id, EventType.JOB_STATUS, {"status": job.status.value, "progress": job.progress})
    persist_event_sync(job.id, EventType.PREFLIGHT_COMPLETED, {"preflight_id": snapshot.id, "selected_solver": snapshot.selected_solver.value})
    persist_event_sync(job.id, EventType.APPROVAL_REQUIRED, {"message": "Manual approval required before solver execution."})
    return to_job_summary(job)


@app.post("/api/v1/jobs/{job_id}/approve")
def approve_job(job_id: str) -> JobSummaryResponse:
    repo = get_repository()
    job = get_required_job_record(job_id)
    if job.status != JobStatus.WAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="job is not waiting for approval")

    snapshot = repo.get_preflight_snapshot(job.preflight_snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="preflight snapshot not found")
    if snapshot.status != SnapshotStatus.READY:
        raise HTTPException(status_code=409, detail="preflight snapshot is not ready for execution")
    if snapshot.execution_mode != ExecutionMode.REAL or snapshot.runtime_blockers:
        raise HTTPException(status_code=409, detail="preflight snapshot is not executable")
    verify_snapshot_integrity(snapshot)

    job.status = JobStatus.QUEUED
    job.approved_at = utc_now()
    job.queued_at = utc_now()
    job.progress = 55
    repo.update_job(job)
    persist_event_sync(job.id, EventType.JOB_STATUS, {"status": job.status.value, "progress": job.progress})
    get_job_service().enqueue(job.id)
    return to_job_summary(job)


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> JobSummaryResponse:
    repo = get_repository()
    job = get_required_job_record(job_id)
    if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
        return to_job_summary(job)

    if job.status in {JobStatus.WAITING_APPROVAL, JobStatus.QUEUED}:
        job.status = JobStatus.CANCELLED
        job.cancelled_at = utc_now()
        repo.update_job(job)
        persist_event_sync(job.id, EventType.JOB_CANCELLED, {"status": job.status.value, "message": "Job cancelled."})
        return to_job_summary(job)

    job.cancel_requested_at = utc_now()
    repo.update_job(job)
    get_job_service().request_cancel(job.id)
    persist_event_sync(job.id, EventType.JOB_STATUS, {"status": job.status.value, "message": "Cancellation requested."})
    return to_job_summary(job)


@app.get("/api/v1/jobs/{job_id}/report")
def get_report(job_id: str):
    job = get_required_job_record(job_id)
    report_artifact = next((artifact for artifact in job.artifacts if artifact.kind == ArtifactKind.REPORT_HTML), None)
    if report_artifact and Path(report_artifact.path).exists():
        return FileResponse(report_artifact.path, media_type="text/html")
    raise HTTPException(status_code=404, detail="report not found")


@app.get("/api/v1/jobs/{job_id}/artifacts")
def get_artifacts(job_id: str) -> list[ArtifactPayload]:
    job = get_required_job_record(job_id)
    payloads: list[ArtifactPayload] = []
    for artifact in job.artifacts:
        payloads.append(
            ArtifactPayload(
                job_id=job.id,
                kind=artifact.kind.value,
                path=artifact.path,
                size_bytes=int(artifact.size_bytes or 0),
            )
        )
    return payloads


def run_preflight_subagents(
    connection_mode: ConnectionMode,
    provider_status: ConnectionStatusResponse,
    bundle,
) -> tuple[SubagentFindings, AIAssistMode, list[str], list[str]]:
    payloads = get_cfd_core().build_subagent_payloads(
        bundle,
        provider_connected=provider_status.connected,
        provider_ready=provider_status.provider_ready,
        connection_mode=connection_mode,
    )

    warnings: list[str] = list(provider_status.warnings)
    ai_mode = AIAssistMode.DISABLED

    if connection_mode == ConnectionMode.OPENAI_API:
        adapter = get_openai_provider()
        geometry = adapter.run_structured_preflight("geometry-triage", payloads["geometry-triage"])
        solver = adapter.run_structured_preflight("solver-planner", payloads["solver-planner"])
        policy = adapter.run_structured_preflight("auth-and-policy-reviewer", payloads["auth-and-policy-reviewer"])
        ai_mode = AIAssistMode(geometry.ai_assist_mode)
        warnings.extend(geometry.warnings)
        warnings.extend(solver.warnings)
        warnings.extend(policy.warnings)
        findings = SubagentFindings(
            geometry_triage=GeometryTriageFinding.model_validate(geometry.payload),
            solver_planner=SolverPlannerFinding.model_validate(solver.payload),
            auth_and_policy_reviewer=AuthPolicyFinding.model_validate(policy.payload),
        )
    else:
        adapter = get_codex_provider()
        geometry = adapter.run_readonly_preflight("geometry-triage", payloads["geometry-triage"])
        solver = adapter.run_readonly_preflight("solver-planner", payloads["solver-planner"])
        policy = adapter.run_readonly_preflight("auth-and-policy-reviewer", payloads["auth-and-policy-reviewer"])
        ai_mode = AIAssistMode(geometry.ai_assist_mode)
        warnings.extend(geometry.warnings)
        warnings.extend(solver.warnings)
        warnings.extend(policy.warnings)
        findings = SubagentFindings(
            geometry_triage=GeometryTriageFinding.model_validate(geometry.payload),
            solver_planner=SolverPlannerFinding.model_validate(solver.payload),
            auth_and_policy_reviewer=AuthPolicyFinding.model_validate(policy.payload),
        )

    ai_warnings = unique_strings(warnings + findings.auth_and_policy_reviewer.ai_warnings)
    policy_warnings = unique_strings(findings.auth_and_policy_reviewer.policy_warnings + provider_status.warnings)
    return findings, ai_mode, ai_warnings, policy_warnings


def build_connection_status_response(connection_id: str, mode: ConnectionMode) -> ConnectionStatusResponse:
    provider_status = get_openai_provider().healthcheck() if mode == ConnectionMode.OPENAI_API else get_codex_provider().healthcheck()
    return ConnectionStatusResponse(
        connection_id=connection_id,
        connected=provider_status.connected,
        provider_ready=provider_status.provider_ready,
        mode=mode,
        backend=provider_status.backend,
        warnings=list(provider_status.warnings),
    )


def ensure_connection(mode: ConnectionMode, connection_id: str | None = None) -> ConnectionRecord:
    repo = get_repository()
    lookup_id = connection_id or mode.value
    connection = repo.get_connection(lookup_id)
    if connection:
        return connection
    status = build_connection_status_response(lookup_id, mode)
    connection = ConnectionRecord(
        id=lookup_id,
        mode=mode,
        label=lookup_id,
        status="ready" if status.provider_ready else "missing",
        data_policy="summary_first",
        metadata={"backend": status.backend.value, "warnings": status.warnings},
        last_validated_at=utc_now(),
    )
    repo.upsert_connection(connection)
    return connection


async def persist_upload(target_dir: Path, geometry_file: UploadFile) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / (geometry_file.filename or "geometry.dat")
    path.write_bytes(await geometry_file.read())
    return path


def cleanup_expired_snapshots(repo) -> None:
    for snapshot_id in repo.list_expired_snapshot_ids(utc_now()):
        shutil.rmtree(get_data_dir() / "snapshots" / snapshot_id, ignore_errors=True)
        repo.delete_snapshot(snapshot_id)


def verify_snapshot_integrity(snapshot: PreflightSnapshot) -> None:
    snapshot_dir = get_data_dir() / "snapshots" / snapshot.id
    integrity_path = snapshot_dir / "preflight" / "integrity.json"
    source_path = get_data_dir() / snapshot.source_file_relpath
    normalized_manifest_path = get_data_dir() / snapshot.normalized_manifest_relpath
    normalized_geometry_path = get_data_dir() / snapshot.normalized_geometry_relpath
    if not integrity_path.exists():
        raise HTTPException(status_code=409, detail="snapshot integrity file missing")
    payload = json.loads(integrity_path.read_text(encoding="utf-8"))
    if payload.get("request_digest") != snapshot.request_digest:
        raise HTTPException(status_code=409, detail="snapshot request digest mismatch")
    if payload.get("source_hash") != snapshot.source_hash:
        raise HTTPException(status_code=409, detail="snapshot source hash mismatch")
    if payload.get("normalized_manifest_hash") != snapshot.normalized_manifest_hash:
        raise HTTPException(status_code=409, detail="snapshot manifest hash mismatch")
    if payload.get("normalized_geometry_hash") != snapshot.normalized_geometry_hash:
        raise HTTPException(status_code=409, detail="snapshot normalized geometry hash mismatch")
    if not source_path.exists():
        raise HTTPException(status_code=409, detail="snapshot source file missing")
    if not normalized_manifest_path.exists():
        raise HTTPException(status_code=409, detail="snapshot normalized manifest missing")
    if not normalized_geometry_path.exists():
        raise HTTPException(status_code=409, detail="snapshot normalized geometry missing")
    if get_cfd_core().compute_sha256(source_path) != snapshot.source_hash:
        raise HTTPException(status_code=409, detail="snapshot source hash does not match file contents")
    if get_cfd_core().compute_sha256(normalized_manifest_path) != snapshot.normalized_manifest_hash:
        raise HTTPException(status_code=409, detail="snapshot manifest hash does not match file contents")
    if get_cfd_core().compute_sha256(normalized_geometry_path) != snapshot.normalized_geometry_hash:
        raise HTTPException(status_code=409, detail="snapshot normalized geometry hash does not match file contents")


def persist_event_sync(job_id: str, event_type: EventType, payload: dict[str, Any]) -> None:
    repo = get_repository()
    event = JobEventRecord(job_id=job_id, seq=repo.next_event_seq(job_id), event_type=event_type, payload=payload, created_at=utc_now())
    stored = repo.add_event(event)
    get_event_broker().publish_from_thread(job_id, stored.model_dump(mode="json"))


def ensure_job_exists(job_id: str) -> None:
    if not get_repository().get_job(job_id):
        raise HTTPException(status_code=404, detail="job not found")


def get_required_job_record(job_id: str) -> JobRecord:
    job = get_repository().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def get_required_job(job_id: str) -> JobSummaryResponse:
    return to_job_summary(get_required_job_record(job_id))


def to_job_summary(job: JobRecord) -> JobSummaryResponse:
    metrics = {metric.name: metric.value for metric in job.metrics}
    residual_history = []
    artifact_by_kind = {artifact.kind: artifact for artifact in job.artifacts}
    residual_artifact = artifact_by_kind.get(ArtifactKind.RESIDUAL_HISTORY)
    if residual_artifact and Path(residual_artifact.path).exists():
        residual_history = load_residual_history(Path(residual_artifact.path))
    return JobSummaryResponse(
        id=job.id,
        status=job.status,
        selected_solver=job.selected_solver,
        execution_mode=job.execution_mode,
        ai_assist_mode=job.ai_assist_mode,
        rationale=job.rationale,
        progress=job.progress,
        warnings=list(job.warnings),
        runtime_blockers=list(job.runtime_blockers),
        install_warnings=list(job.install_warnings),
        ai_warnings=list(job.ai_warnings),
        policy_warnings=list(job.policy_warnings),
        artifacts=list(job.artifacts),
        metrics=metrics,
        residual_history=residual_history,
        error=job.error,
        preflight_snapshot_id=job.preflight_snapshot_id,
    )


def load_residual_history(path: Path) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as stream:
        reader = csv.DictReader(stream)
        for index, row in enumerate(reader, start=1):
            iteration = parse_float(row, ["iteration", "Iter", "INNER_ITER"], float(index))
            residual = parse_float(row, ["residual", "Residual", "RMS_RES", "Res_Flow[0]", "Res[0]"], 0.0)
            points.append({"iteration": iteration, "residual": residual})
    return points


def parse_float(row: dict[str, str | None], keys: list[str], default: float) -> float:
    for key in keys:
        raw = row.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return default


def digest_payload(payload: Any) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def utc_now() -> datetime:
    return datetime.now(UTC)
