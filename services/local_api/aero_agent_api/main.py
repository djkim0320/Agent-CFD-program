from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from aero_agent_api.dependencies import get_data_dir, get_event_broker, get_job_service, get_repository
from aero_agent_api.models import (
    AnalysisRequest,
    ArtifactPayload,
    ConnectionCreate,
    ConnectionMode,
    ConnectionRecord,
    JobEvent,
    JobRecord,
    JobStatus,
    PreflightPlan,
    make_job_folder,
    utcnow,
)
from aero_agent_job_runner.contracts import JobExecutionContext


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_repository()
    yield


app = FastAPI(title="Aero Agent Local API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/connections/status")
def connection_status(mode: ConnectionMode = Query(...)) -> dict[str, object]:
    return build_connection_status(mode)


@app.post("/api/v1/connections")
def create_connection(payload: ConnectionCreate) -> ConnectionRecord:
    repo = get_repository()
    status = build_connection_status(payload.mode)
    record = ConnectionRecord(
        mode=payload.mode,
        label=payload.label or payload.mode.value,
        status="ready" if status["providerReady"] else "missing",
        data_policy=payload.data_policy,
        metadata={
            "backend": status["backend"],
            "warnings": status["warnings"],
            **(payload.credentials_hint or {}),
        },
        last_validated_at=utcnow(),
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


@app.post("/api/v1/connections/{connection_id}/validate")
def validate_connection(connection_id: str) -> ConnectionRecord:
    repo = get_repository()
    connection = repo.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="connection not found")
    status = build_connection_status(connection.mode)
    connection.status = "ready" if status["providerReady"] else "missing"
    connection.last_validated_at = utcnow()
    connection.metadata.update({"backend": status["backend"], "warnings": status["warnings"]})
    repo.upsert_connection(connection)
    return connection


@app.get("/api/v1/jobs")
def list_jobs() -> list[JobRecord]:
    return get_repository().list_jobs()


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> JobRecord:
    job = get_repository().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/api/v1/jobs/{job_id}/history")
def job_history(job_id: str) -> list[JobEvent]:
    return get_repository().list_events(job_id)


@app.get("/api/v1/jobs/{job_id}/events")
async def job_events(job_id: str):
    repo = get_repository()
    existing = repo.list_events(job_id)
    broker = get_event_broker()
    queue = await broker.subscribe(job_id)

    async def stream():
        try:
            for event in existing:
                yield {"event": event.event_type, "data": event.model_dump_json(), "id": str(event.id or event.seq)}
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {
                        "event": event["event_type"],
                        "data": json.dumps(event),
                        "id": str(event.get("seq", "")),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": json.dumps({"job_id": job_id})}
        finally:
            await broker.unsubscribe(job_id, queue)

    return EventSourceResponse(stream())


@app.post("/api/v1/jobs/preflight")
async def create_preflight(
    connection_mode: ConnectionMode = Form(...),
    unit: str = Form(...),
    geometry_kind: str = Form(...),
    solver_preference: str = Form("auto"),
    fidelity: str = Form("balanced"),
    aoa: float = Form(0.0),
    sideslip: float = Form(0.0),
    velocity: float | None = Form(None),
    mach: float | None = Form(None),
    geometry_file: UploadFile = File(...),
) -> dict[str, object]:
    preflight_dir = get_data_dir() / "preflight-cache" / str(uuid4())
    source_path = await persist_upload(preflight_dir, geometry_file)
    request = build_request(
        unit=unit,
        geometry_kind=geometry_kind,
        solver_preference=solver_preference,
        fidelity=fidelity,
        aoa=aoa,
        sideslip=sideslip,
        velocity=velocity,
        mach=mach,
    )
    context = JobExecutionContext(
        job_id=f"preflight-{uuid4()}",
        connection_mode=connection_mode.value,
        job_dir=preflight_dir,
        request=request.model_dump(),
        source_file_path=source_path,
        source_file_name=geometry_file.filename or source_path.name,
    )
    plan = get_job_service().run_preflight(context)
    return to_frontend_preflight(plan)


@app.post("/api/v1/jobs")
async def create_job(
    connection_mode: ConnectionMode = Form(...),
    unit: str = Form(...),
    geometry_kind: str = Form(...),
    solver_preference: str = Form("auto"),
    fidelity: str = Form("balanced"),
    aoa: float = Form(0.0),
    sideslip: float = Form(0.0),
    velocity: float | None = Form(None),
    mach: float | None = Form(None),
    geometry_file: UploadFile = File(...),
) -> JobRecord:
    repo = get_repository()
    connection = ensure_connection(connection_mode)

    job_id = str(uuid4())
    job_dir = make_job_folder(get_data_dir(), job_id)
    source_path = await persist_upload(job_dir, geometry_file)
    request = build_request(
        unit=unit,
        geometry_kind=geometry_kind,
        solver_preference=solver_preference,
        fidelity=fidelity,
        aoa=aoa,
        sideslip=sideslip,
        velocity=velocity,
        mach=mach,
    )
    job = JobRecord(
        id=job_id,
        connection_id=connection.id,
        status=JobStatus.uploaded,
        selected_solver="auto",
        request=request,
        source_file_name=geometry_file.filename or source_path.name,
        source_file_path=str(source_path),
        progress=0,
    )
    repo.create_job(job)
    await emit_event(job.id, "job.status", {"status": "uploaded", "message": "Geometry uploaded."})

    job.status = JobStatus.preflighting
    job.progress = 10
    repo.update_job(job)
    await emit_event(job.id, "preflight.started", {"message": "Preflight analysis started.", "progress": 10})

    context = make_execution_context(repo, job, job_dir)
    preflight = get_job_service().run_preflight(context)
    job.selected_solver = preflight["selected_solver"]
    job.rationale = preflight["rationale"]
    job.warnings = preflight.get("warnings", [])
    job.status = JobStatus.waiting_approval
    job.progress = 50
    repo.update_job(job)
    await emit_event(
        job.id,
        "preflight.completed",
        {"message": f"Recommended solver: {job.selected_solver}.", "progress": 50, "preflight": preflight},
    )
    await emit_event(
        job.id,
        "approval.required",
        {"message": "Manual approval required before mutable solver execution.", "progress": 50},
    )
    return job


@app.post("/api/v1/jobs/{job_id}/approve")
async def approve_job(job_id: str) -> JobRecord:
    repo = get_repository()
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.waiting_approval:
        raise HTTPException(status_code=409, detail="job is not waiting for approval")
    job.approved_at = utcnow()
    job.status = JobStatus.running
    job.progress = 60
    repo.update_job(job)
    await emit_event(job.id, "job.status", {"status": "running", "message": "Execution approved.", "progress": 60})
    asyncio.create_task(run_execution(job.id))
    return job


@app.post("/api/v1/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> JobRecord:
    repo = get_repository()
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    job.status = JobStatus.cancelled
    job.cancelled_at = utcnow()
    repo.update_job(job)
    await emit_event(job.id, "job.status", {"status": "cancelled", "message": "Job cancelled."})
    return job


@app.get("/api/v1/jobs/{job_id}/report")
def get_report(job_id: str):
    job = get_required_job(job_id)
    report_artifact = next((item for item in job.artifacts if item.get("kind") == "report"), None)
    if report_artifact and Path(report_artifact["path"]).exists():
        return FileResponse(report_artifact["path"], media_type="text/html")
    report_path = Path(job.source_file_path).parents[2] / "report" / "report.html"
    if report_path.exists():
        return FileResponse(report_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="report not found")


@app.get("/api/v1/jobs/{job_id}/artifacts")
def get_artifacts(job_id: str) -> list[ArtifactPayload]:
    job = get_required_job(job_id)
    payloads: list[ArtifactPayload] = []
    for artifact in job.artifacts:
        artifact_path = Path(artifact.get("path", ""))
        size = artifact.get("size_bytes")
        if size is None and artifact_path.exists():
            size = artifact_path.stat().st_size
        payloads.append(
            ArtifactPayload(
                job_id=job.id,
                kind=str(artifact.get("kind", "artifact")),
                path=str(artifact_path),
                size_bytes=int(size or 0),
            )
        )
    return payloads


def get_required_job(job_id: str) -> JobRecord:
    job = get_repository().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def ensure_connection(mode: ConnectionMode) -> ConnectionRecord:
    repo = get_repository()
    for connection in repo.list_connections():
        if connection.mode == mode:
            return connection
    status = build_connection_status(mode)
    record = ConnectionRecord(
        mode=mode,
        label=mode.value,
        status="ready" if status["providerReady"] else "missing",
        data_policy="summary_first",
        metadata={"backend": status["backend"], "warnings": status["warnings"]},
        last_validated_at=utcnow(),
    )
    repo.upsert_connection(record)
    return record


def build_connection_status(mode: ConnectionMode) -> dict[str, object]:
    if mode == ConnectionMode.codex_oauth:
        codex_available = shutil.which("codex") is not None
        wsl_available = shutil.which("wsl") is not None or bool(os.getenv("WSL_DISTRO_NAME"))
        warnings = ["Windows codex_oauth path is Beta and WSL-preferred."]
        if not codex_available:
            warnings.append("Codex runtime not detected; fallback behavior only.")
        if not wsl_available:
            warnings.append("WSL not detected; native Windows support is best-effort only.")
        return {
            "connected": codex_available,
            "mode": mode.value,
            "providerReady": codex_available,
            "backend": "codex_sdk" if codex_available else "mock",
            "warnings": warnings,
        }
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "connected": has_key,
        "mode": mode.value,
        "providerReady": has_key,
        "backend": "openai",
        "warnings": [] if has_key else ["OPENAI_API_KEY is not set. The API route will stay in scaffold mode."],
    }


def build_request(
    *,
    unit: str,
    geometry_kind: str,
    solver_preference: str,
    fidelity: str,
    aoa: float,
    sideslip: float,
    velocity: float | None,
    mach: float | None,
) -> AnalysisRequest:
    return AnalysisRequest(
        unit=unit,
        geometry_kind=geometry_kind,  # type: ignore[arg-type]
        solver_preference=solver_preference,  # type: ignore[arg-type]
        fidelity=fidelity,  # type: ignore[arg-type]
        flow={
            "aoa": aoa,
            "sideslip": sideslip,
            "velocity": velocity,
            "mach": mach,
        },
    )


def make_execution_context(repo, job: JobRecord, job_dir: Path) -> JobExecutionContext:
    connection = repo.get_connection(job.connection_id)
    connection_mode = connection.mode.value if connection else "openai_api"
    return JobExecutionContext(
        job_id=job.id,
        connection_mode=connection_mode,
        job_dir=job_dir,
        request=job.request.model_dump(),
        source_file_path=Path(job.source_file_path),
        source_file_name=job.source_file_name,
    )


async def persist_upload(root_dir: Path, geometry_file: UploadFile) -> Path:
    input_dir = root_dir / "input" / "original"
    input_dir.mkdir(parents=True, exist_ok=True)
    source_path = input_dir / (geometry_file.filename or "geometry.dat")
    source_path.write_bytes(await geometry_file.read())
    return source_path


def to_frontend_preflight(plan: dict[str, object]) -> dict[str, object]:
    selected = str(plan["selected_solver"])
    runtime_minutes = int(plan.get("runtime_estimate_minutes", 20))
    memory_gb = float(plan.get("memory_estimate_gb", 4.0))
    confidence = 0.84 if selected == "su2" else 0.78 if selected == "openfoam" else 0.72
    return {
        "selectedSolver": selected,
        "candidateSolvers": ["vspaero", "su2", "openfoam"],
        "runtimeEstimate": f"{max(5, runtime_minutes // 2)}-{runtime_minutes} min",
        "memoryEstimate": f"{memory_gb:.1f} GB",
        "confidence": confidence,
        "warnings": plan.get("warnings", []),
        "rationale": plan.get("rationale", ""),
    }


async def run_execution(job_id: str) -> None:
    repo = get_repository()
    service = get_job_service()
    job = repo.get_job(job_id)
    if not job:
        return
    job_dir = make_job_folder(get_data_dir(), job.id)
    context = make_execution_context(repo, job, job_dir)
    try:
        context.request["selected_solver"] = job.selected_solver
        await emit_event(job.id, "tool.started", {"message": f"Preparing {job.selected_solver} case.", "progress": 65})
        result = service.run_execution(context, approval=True)
        job.status = JobStatus.postprocessing
        job.progress = 85
        repo.update_job(job)
        await emit_event(job.id, "solver.stdout", {"message": "Deterministic solver run completed.", "progress": 78})
        await emit_event(job.id, "solver.metrics", {"message": "Metrics extracted from scaffold run.", "metrics": result.metrics})
        job.status = JobStatus.completed
        job.progress = 100
        job.metrics = result.metrics
        job.artifacts = result.artifacts
        job.completed_at = utcnow()
        repo.update_job(job)
        for artifact in result.artifacts:
            await emit_event(job.id, "artifact.ready", {"message": f"Artifact ready: {artifact.get('kind', 'artifact')}", "artifact": artifact})
        await emit_event(job.id, "report.ready", {"message": "Report bundle generated.", "reportPath": result.report_path})
        await emit_event(job.id, "job.completed", {"message": "Analysis completed.", "progress": 100})
    except Exception as exc:  # pragma: no cover - runtime guard
        job.status = JobStatus.failed
        job.error = str(exc)
        job.failed_at = utcnow()
        repo.update_job(job)
        await emit_event(job.id, "job.failed", {"message": str(exc), "progress": 100})


async def emit_event(job_id: str, event_type: str, payload: dict[str, object]) -> None:
    repo = get_repository()
    broker = get_event_broker()
    event = JobEvent(job_id=job_id, seq=repo.next_event_seq(job_id), event_type=event_type, payload=payload)
    repo.add_event(event)
    await broker.publish(job_id, event.model_dump(mode="json"))
