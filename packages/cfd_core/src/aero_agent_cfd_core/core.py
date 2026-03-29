from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aero_agent_common import create_app_paths, json_dumps
from aero_agent_contracts import (
    AnalysisJob,
    AnalysisRequest,
    ArtifactKind,
    ArtifactRecord,
    GeometryKind,
    GeometryManifest,
    GeometryStats,
    MetricRecord,
    PreflightPlan,
    ProviderCapabilities,
    RepairCheckResult,
    ResultField,
    SolverCandidate,
    SolverKind,
    SolverRunManifest,
    SolverSelection,
)
from aero_agent_solver_adapters import SolverAdapterRegistry
from aero_agent_viewer_assets import ViewerAssetBuilder


@dataclass(slots=True)
class CaseManifest:
    job_id: str
    case_dir: Path
    solver: SolverKind
    config_path: Path
    mesh_spec: dict[str, object]


@dataclass(slots=True)
class CFDResults:
    metrics: list[MetricRecord]
    artifacts: list[ArtifactRecord]
    fields: list[ResultField]
    summary_path: Path
    report_path: Path | None = None
    viewer_index_path: Path | None = None


class CFDCore:
    def __init__(
        self,
        *,
        solver_registry: SolverAdapterRegistry | None = None,
        viewer_builder: ViewerAssetBuilder | None = None,
    ) -> None:
        self.solver_registry = solver_registry or SolverAdapterRegistry()
        self.viewer_builder = viewer_builder or ViewerAssetBuilder()

    def inspect_geometry(self, request: AnalysisRequest, source_path: Path) -> GeometryManifest:
        suffix = source_path.suffix.lower()
        inferred_kind = GeometryKind.AIRCRAFT_VSP if suffix == ".vsp3" else GeometryKind.GENERAL_3D
        geometry_kind = request.geometry_kind_hint or inferred_kind
        stats = GeometryStats(
            file_size_bytes=source_path.stat().st_size if source_path.exists() else 0,
            bbox=(0.0, 0.0, 0.0, 1.0, 0.6, 0.4),
            face_count=128_000 if geometry_kind == GeometryKind.GENERAL_3D else 24_000,
            edge_count=84_000 if geometry_kind == GeometryKind.GENERAL_3D else 14_000,
            component_count=1,
            watertight=geometry_kind != GeometryKind.AIRCRAFT_VSP,
            estimated_scale=1.0,
        )
        warnings: list[str] = []
        blockers: list[str] = []
        if geometry_kind == GeometryKind.GENERAL_3D and suffix not in {".stl", ".obj", ".step", ".stp"}:
            warnings.append("General 3D workflow is optimized for STL/OBJ/STEP inputs.")
        if geometry_kind == GeometryKind.AIRCRAFT_VSP and suffix != ".vsp3":
            warnings.append("Aircraft mode without .vsp3 may reduce VSPAERO suitability.")
        return GeometryManifest(
            geometry_file=str(source_path),
            geometry_kind=geometry_kind,
            unit=request.unit,
            stats=stats,
            warnings=warnings,
            blockers=blockers,
        )

    def repair_check(self, manifest: GeometryManifest) -> RepairCheckResult:
        actions = ["deduplicated_vertices", "normalized_normals"]
        blockers = list(manifest.blockers)
        if manifest.geometry_kind == GeometryKind.GENERAL_3D and manifest.stats.watertight is False:
            blockers.append("Geometry is not watertight enough for the current general 3D pipeline.")
        return RepairCheckResult(
            repairable=not blockers,
            repair_actions=actions if not blockers else actions + ["manual_fix_required"],
            blockers=blockers,
            preview_mesh_path=manifest.preview_path,
        )

    def select_solver(
        self,
        request: AnalysisRequest,
        manifest: GeometryManifest,
        repair: RepairCheckResult,
        provider_capabilities: ProviderCapabilities,
    ) -> SolverSelection:
        candidates: list[SolverCandidate] = []
        candidates.append(self._candidate(SolverKind.VSPAERO, request, manifest))
        candidates.append(self._candidate(SolverKind.SU2, request, manifest))
        candidates.append(self._candidate(SolverKind.OPENFOAM, request, manifest))
        filtered = [candidate for candidate in candidates if candidate.score > 0]
        selected = max(filtered, key=lambda item: item.score, default=self._candidate(SolverKind.SU2, request, manifest))
        if request.solver_preference != SolverKind.AUTO:
            override = next((item for item in filtered if item.solver == request.solver_preference), None)
            if override is not None:
                selected = override
        rationale_parts = [
            selected.rationale,
            f"Provider backend: {provider_capabilities.backend.value}.",
        ]
        if repair.blockers:
            rationale_parts.append("Repair blockers detected; confidence reduced.")
        fit_score = round(selected.score / 100, 2)
        return SolverSelection(
            selected_solver=selected.solver,
            rationale=" ".join(rationale_parts),
            candidates=filtered,
            user_override=request.solver_preference if request.solver_preference != SolverKind.AUTO else None,
            runtime_estimate_minutes=selected.runtime_estimate_minutes,
            memory_estimate_gb=selected.memory_estimate_gb,
            fit_score=fit_score,
        )

    def prepare_case(self, request: AnalysisRequest, plan: PreflightPlan, *, job_id: str) -> CaseManifest:
        app_paths = create_app_paths(Path.cwd())
        case_dir = app_paths.jobs / job_id / "case"
        case_dir.mkdir(parents=True, exist_ok=True)
        config_path = case_dir / "case_manifest.json"
        mesh_spec = {
            "fidelity": request.fidelity,
            "selected_solver": plan.solver_selection.selected_solver.value,
            "runtime_estimate_minutes": plan.estimated_runtime_minutes,
            "memory_estimate_gb": plan.estimated_memory_gb,
        }
        config_path.write_text(
            json_dumps(
                {
                    "job_id": job_id,
                    "request": request.model_dump(mode="json"),
                    "solver_selection": plan.solver_selection.model_dump(mode="json"),
                    "mesh_spec": mesh_spec,
                }
            ),
            encoding="utf-8",
        )
        return CaseManifest(
            job_id=job_id,
            case_dir=case_dir,
            solver=plan.solver_selection.selected_solver,
            config_path=config_path,
            mesh_spec=mesh_spec,
        )

    def run_solver(self, case: CaseManifest) -> SolverRunManifest:
        return self.solver_registry.run(case.job_id, case.case_dir, case.solver)

    def extract_results(self, case: CaseManifest, run: SolverRunManifest) -> CFDResults:
        results_dir = case.case_dir.parent / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        summary_path = results_dir / "summary.json"
        metrics = self._default_metrics(case.solver)
        fields = [
            ResultField(name="pressure_coefficient", path=str(results_dir / "cp.vtp")),
            ResultField(name="velocity_magnitude", path=str(results_dir / "velocity.vtp")),
        ]
        summary_path.write_text(
            json_dumps(
                {
                    "solver": case.solver.value,
                    "status": run.status.value,
                    "metrics": [metric.model_dump(mode="json") for metric in metrics],
                    "fields": [field.model_dump(mode="json") for field in fields],
                    "warnings": run.warnings,
                }
            ),
            encoding="utf-8",
        )
        return CFDResults(
            metrics=metrics,
            artifacts=[
                ArtifactRecord(kind=ArtifactKind.SUMMARY, path=str(summary_path), size_bytes=summary_path.stat().st_size),
                ArtifactRecord(kind=ArtifactKind.LOGS, path=run.logs_path or "", size_bytes=None),
            ],
            fields=fields,
            summary_path=summary_path,
        )

    def build_report(self, job: AnalysisJob, plan: PreflightPlan, results: CFDResults) -> CFDResults:
        report_dir = Path(results.summary_path).parent.parent / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "report.html"
        report_path.write_text(
            "\n".join(
                [
                    "<html><body>",
                    "<h1>Aero Agent Report</h1>",
                    f"<p>Solver: {plan.solver_selection.selected_solver.value}</p>",
                    f"<p>Status: {job.status.value}</p>",
                    f"<p>Rationale: {plan.solver_selection.rationale}</p>",
                    "<ul>",
                    *[
                        f"<li>{metric.name}: {metric.value}{metric.unit or ''}</li>"
                        for metric in results.metrics
                    ],
                    "</ul>",
                    "</body></html>",
                ]
            ),
            encoding="utf-8",
        )
        results.report_path = report_path
        results.artifacts.append(
            ArtifactRecord(kind=ArtifactKind.REPORT_HTML, path=str(report_path), size_bytes=report_path.stat().st_size)
        )
        return results

    def build_viewer(self, job: AnalysisJob, results: CFDResults) -> CFDResults:
        viewer_manifest = self.viewer_builder.build(job.id.hex, results.fields)
        results.viewer_index_path = Path(viewer_manifest.index_path)
        results.artifacts.append(
            ArtifactRecord(
                kind=ArtifactKind.VIEWER_BUNDLE,
                path=viewer_manifest.index_path,
                size_bytes=Path(viewer_manifest.index_path).stat().st_size,
            )
        )
        return results

    def _candidate(
        self, solver: SolverKind, request: AnalysisRequest, manifest: GeometryManifest
    ) -> SolverCandidate:
        score = 0.0
        runtime = 30
        memory = 4.0
        rationale = ""
        if solver == SolverKind.VSPAERO:
            runtime = 10
            memory = 2.0
            if manifest.geometry_kind == GeometryKind.AIRCRAFT_VSP:
                score = 92 if request.fidelity != "high" else 72
                rationale = "Aircraft geometry strongly favors VSPAERO."
            else:
                rationale = "VSPAERO is reserved for aircraft-focused workflows."
        elif solver == SolverKind.SU2:
            runtime = 45 if request.fidelity == "balanced" else 20
            memory = 6.0 if request.fidelity == "high" else 4.0
            if manifest.geometry_kind == GeometryKind.GENERAL_3D:
                score = 86 if request.fidelity != "high" else 68
                rationale = "SU2 is the default steady external aero path for general 3D geometry."
            else:
                score = 58
                rationale = "SU2 remains a safe fallback for aircraft geometry."
        elif solver == SolverKind.OPENFOAM:
            runtime = 120
            memory = 10.0
            if request.fidelity == "high":
                score = 88
                rationale = "High-fidelity requests elevate OpenFOAM due to separation handling."
            elif manifest.geometry_kind == GeometryKind.GENERAL_3D:
                score = 64
                rationale = "OpenFOAM is a heavier fallback for general 3D separation risk."
            else:
                score = 34
                rationale = "OpenFOAM is available but not preferred for the current aircraft-focused case."
        return SolverCandidate(
            solver=solver,
            score=score,
            rationale=rationale,
            runtime_estimate_minutes=runtime,
            memory_estimate_gb=memory,
        )

    def _default_metrics(self, solver: SolverKind) -> list[MetricRecord]:
        return [
            MetricRecord(name="CL", value=0.42 if solver != SolverKind.OPENFOAM else 0.45),
            MetricRecord(name="CD", value=0.031 if solver != SolverKind.OPENFOAM else 0.034),
            MetricRecord(name="Cm", value=-0.08),
        ]
