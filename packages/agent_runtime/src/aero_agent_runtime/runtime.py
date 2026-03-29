from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from aero_agent_common import EventBus, EventRecord, InMemoryEventBus, create_app_paths
from aero_agent_contracts import (
    AnalysisJob,
    AnalysisRequest,
    ArtifactKind,
    ArtifactRecord,
    ConnectionProfile,
    EventType,
    GeometryManifest,
    JobStatus,
    PreflightPlan,
    SolverKind,
    ToolName,
    ToolRequest,
    ToolResult,
)
from aero_agent_cfd_core import CFDCore
from aero_agent_provider_codex import CodexProviderAdapter
from aero_agent_provider_openai import OpenAIProviderAdapter


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolExecutor(Protocol):
    def invoke(self, request: ToolRequest) -> ToolResult: ...


@dataclass(slots=True)
class SubagentRun:
    id: UUID = field(default_factory=uuid4)
    agent_type: str = ""
    input_payload: dict[str, Any] = field(default_factory=dict)
    output_payload: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    status: JobStatus = JobStatus.UPLOADED


@dataclass(slots=True)
class AnalysisSession:
    id: UUID = field(default_factory=uuid4)
    job: AnalysisJob | None = None
    subagents: list[SubagentRun] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class RuntimeContext:
    root: Path
    connection: ConnectionProfile
    request: AnalysisRequest
    job: AnalysisJob
    session: AnalysisSession


class AgentRuntime:
    def __init__(
        self,
        *,
        event_bus: EventBus | None = None,
        cfd_core: CFDCore | None = None,
        openai_provider: OpenAIProviderAdapter | None = None,
        codex_provider: CodexProviderAdapter | None = None,
    ) -> None:
        self.event_bus = event_bus or InMemoryEventBus()
        self.cfd_core = cfd_core or CFDCore()
        self.openai_provider = openai_provider or OpenAIProviderAdapter()
        self.codex_provider = codex_provider or CodexProviderAdapter()

    def choose_provider(self, connection: ConnectionProfile):
        if connection.mode.value == "codex_oauth":
            return self.codex_provider
        return self.openai_provider

    def build_session(self, request: AnalysisRequest, connection: ConnectionProfile, job: AnalysisJob) -> RuntimeContext:
        return RuntimeContext(
            root=Path.cwd(),
            connection=connection,
            request=request,
            job=job,
            session=AnalysisSession(job=job),
        )

    def run_preflight(self, ctx: RuntimeContext) -> PreflightPlan:
        provider = self.choose_provider(ctx.connection)
        geom = self.cfd_core.inspect_geometry(ctx.request, Path.cwd() / ctx.request.geometry_file)
        repair = self.cfd_core.repair_check(geom)
        solver_selection = self.cfd_core.select_solver(ctx.request, geom, repair, provider.capabilities())
        plan = PreflightPlan(
            request=ctx.request,
            geometry_manifest=geom,
            repair=repair,
            solver_selection=solver_selection,
            warnings=list(dict.fromkeys(geom.warnings + repair.blockers)),
            blockers=list(dict.fromkeys(geom.blockers + repair.blockers)),
            approval_required=True,
            estimated_runtime_minutes=solver_selection.runtime_estimate_minutes,
            estimated_memory_gb=solver_selection.memory_estimate_gb,
        )
        ctx.job.status = JobStatus.WAITING_APPROVAL
        ctx.job.preflight_plan = plan
        ctx.job.request = ctx.request
        ctx.job.updated_at = utc_now()
        self.event_bus.publish(EventRecord(type=EventType.PREFLIGHT_COMPLETED, payload=plan.model_dump(), job_id=ctx.job.id))
        return plan

    def approve_and_run(self, ctx: RuntimeContext, plan: PreflightPlan) -> AnalysisJob:
        ctx.job.status = JobStatus.RUNNING
        ctx.job.preflight_plan = plan
        ctx.job.selected_solver = plan.solver_selection.selected_solver
        ctx.job.rationale = plan.solver_selection.rationale
        self.event_bus.publish(EventRecord(type=EventType.APPROVAL_REQUIRED, payload=plan.model_dump(), job_id=ctx.job.id))
        self.event_bus.publish(EventRecord(type=EventType.JOB_STATUS, payload={"status": ctx.job.status.value}, job_id=ctx.job.id))

        case_manifest = self.cfd_core.prepare_case(ctx.request, plan, job_id=str(ctx.job.id))
        solver_run = self.cfd_core.run_solver(case_manifest)
        results = self.cfd_core.extract_results(case_manifest, solver_run)
        report = self.cfd_core.build_report(ctx.job, plan, results)
        viewer = self.cfd_core.build_viewer(ctx.job, results)

        ctx.job.artifacts = results.artifacts + report.artifacts + viewer.artifacts
        ctx.job.metrics = results.metrics
        ctx.job.status = JobStatus.COMPLETED
        ctx.job.progress = 1.0
        ctx.job.updated_at = utc_now()
        self.event_bus.publish(EventRecord(type=EventType.JOB_COMPLETED, payload=ctx.job.model_dump(), job_id=ctx.job.id))
        return ctx.job


class LocalAgentRuntime(AgentRuntime):
    def bootstrap_workspace(self, root: Path) -> dict[str, Path]:
        app_paths = create_app_paths(root)
        return {
            "data": app_paths.data,
            "jobs": app_paths.jobs,
            "artifacts": app_paths.artifacts,
            "logs": app_paths.logs,
        }

