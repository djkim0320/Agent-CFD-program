from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import csv
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import zipfile

from aero_agent_common import json_dumps
from aero_agent_contracts import (
    AnalysisRequest,
    AIAssistMode,
    ArtifactKind,
    ArtifactRecord,
    ConnectionMode,
    ExecutionMode,
    GeometryKind,
    GeometryManifest,
    GeometryStats,
    InstallStatus,
    JobStatus,
    MetricRecord,
    PreflightPlan,
    PreflightResponse,
    RepairCheckResult,
    ReportManifest,
    ResultField,
    SolverCandidate,
    SolverKind,
    SolverRunManifest,
    SolverSelection,
    SubagentFindings,
    ViewerManifest,
)
from aero_agent_solver_adapters import SolverAdapterRegistry, SolverRuntimeHandle
from aero_agent_viewer_assets import ViewerAssetBuilder


@dataclass(slots=True)
class TriangleMesh:
    vertices: list[tuple[float, float, float]]
    faces: list[tuple[int, int, int]]


@dataclass(slots=True)
class CaseManifest:
    job_id: str
    solver: SolverKind
    case_dir: Path
    cfg_path: Path
    geometry_path: Path
    mesh_path: Path
    results_dir: Path
    logs_dir: Path


@dataclass(slots=True)
class CFDResults:
    solver_log_path: Path
    residual_history_path: Path
    coefficients_path: Path
    residual_history: list[dict[str, float]]
    coefficients: dict[str, float]
    metrics: list[MetricRecord]
    fields: list[ResultField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PreflightBundle:
    request: AnalysisRequest
    geometry_manifest: GeometryManifest
    repair_result: RepairCheckResult
    solver_selection: SolverSelection
    execution_mode: ExecutionMode
    runtime_blockers: list[str]
    install_warnings: list[str]
    confidence: float


class CFDCore:
    def __init__(
        self,
        solver_registry: SolverAdapterRegistry | None = None,
        viewer_builder: ViewerAssetBuilder | None = None,
    ) -> None:
        self.solver_registry = solver_registry or SolverAdapterRegistry()
        self.viewer_builder = viewer_builder or ViewerAssetBuilder()

    def run_preflight(
        self,
        request: AnalysisRequest,
        source_file_path: Path,
        *,
        install_status: InstallStatus,
        connection_mode: ConnectionMode,
    ) -> PreflightBundle:
        geometry_manifest = self.inspect_geometry(source_file_path, geometry_kind_hint=request.geometry_kind_hint)
        repair_result = self.repair_check(geometry_manifest)
        solver_selection = self.select_solver(
            request=request,
            geometry_manifest=geometry_manifest,
            repair_result=repair_result,
        )
        runtime_blockers = self._collect_runtime_blockers(
            request=request,
            geometry_manifest=geometry_manifest,
            repair_result=repair_result,
            solver_selection=solver_selection,
            install_status=install_status,
            connection_mode=connection_mode,
        )
        execution_mode = ExecutionMode.REAL if not runtime_blockers else ExecutionMode.SCAFFOLD
        return PreflightBundle(
            request=request,
            geometry_manifest=geometry_manifest,
            repair_result=repair_result,
            solver_selection=solver_selection,
            execution_mode=execution_mode,
            runtime_blockers=runtime_blockers,
            install_warnings=list(install_status.install_warnings),
            confidence=self._confidence_for(geometry_manifest, repair_result, runtime_blockers),
        )

    def build_preflight_plan(self, bundle: PreflightBundle) -> PreflightPlan:
        return PreflightPlan(
            request=bundle.request,
            geometry_manifest=bundle.geometry_manifest,
            repair=bundle.repair_result,
            solver_selection=bundle.solver_selection,
            warnings=list(bundle.geometry_manifest.warnings) + list(bundle.install_warnings),
            blockers=list(bundle.runtime_blockers),
            approval_required=True,
            estimated_runtime_minutes=bundle.solver_selection.runtime_estimate_minutes,
            estimated_memory_gb=bundle.solver_selection.memory_estimate_gb,
        )

    def build_preflight_response(
        self,
        bundle: PreflightBundle,
        *,
        snapshot_id: str,
        subagent_findings: SubagentFindings,
        ai_assist_mode: AIAssistMode,
        ai_warnings: list[str],
        policy_warnings: list[str],
        request_digest: str,
        source_hash: str,
        normalized_manifest_hash: str,
    ) -> PreflightResponse:
        return PreflightResponse(
            preflight_id=snapshot_id,
            selected_solver=bundle.solver_selection.selected_solver,
            execution_mode=bundle.execution_mode,
            ai_assist_mode=ai_assist_mode,
            runtime_blockers=list(bundle.runtime_blockers),
            install_warnings=list(bundle.install_warnings),
            ai_warnings=list(ai_warnings),
            policy_warnings=list(policy_warnings),
            subagent_findings=subagent_findings,
            request_digest=request_digest,
            source_hash=source_hash,
            normalized_manifest_hash=normalized_manifest_hash,
            runtime_estimate_minutes=bundle.solver_selection.runtime_estimate_minutes,
            memory_estimate_gb=bundle.solver_selection.memory_estimate_gb,
            confidence=bundle.confidence,
            rationale=bundle.solver_selection.rationale,
            candidate_solvers=[candidate.solver for candidate in bundle.solver_selection.candidates],
        )

    def build_subagent_payloads(
        self,
        bundle: PreflightBundle,
        *,
        provider_connected: bool,
        provider_ready: bool,
        connection_mode: ConnectionMode,
    ) -> dict[str, dict[str, object]]:
        manifest = bundle.geometry_manifest
        stats = manifest.stats
        return {
            "geometry-triage": {
                "file_name": Path(manifest.geometry_file).name,
                "format": manifest.format or Path(manifest.geometry_file).suffix.lstrip("."),
                "geometry_kind_hint": manifest.geometry_kind.value,
                "bbox": list(stats.bbox) if stats.bbox else None,
                "face_count": stats.face_count,
                "component_count": stats.component_count,
                "watertight": stats.watertight,
                "repair_actions": bundle.repair_result.repair_actions,
                "repair_blockers": bundle.repair_result.blockers,
                "unit": bundle.request.unit,
            },
            "solver-planner": {
                "geometry_kind": manifest.geometry_kind.value,
                "format": manifest.format,
                "solver_preference": bundle.request.solver_preference.value,
                "selected_solver": bundle.solver_selection.selected_solver.value,
                "runtime_estimate_minutes": bundle.solver_selection.runtime_estimate_minutes,
                "memory_estimate_gb": bundle.solver_selection.memory_estimate_gb,
                "runtime_blockers": bundle.runtime_blockers,
                "fidelity": bundle.request.fidelity,
            },
            "auth-and-policy-reviewer": {
                "connection_mode": connection_mode.value,
                "provider_connected": provider_connected,
                "provider_ready": provider_ready,
                "execution_mode": bundle.execution_mode.value,
                "runtime_blockers": bundle.runtime_blockers,
                "data_export_policy": "summary_only",
                "geometry_kind": manifest.geometry_kind.value,
            },
        }

    def normalized_manifest_payload(self, bundle: PreflightBundle) -> dict[str, object]:
        return {
            "geometry_manifest": bundle.geometry_manifest.model_dump(mode="json"),
            "repair_result": bundle.repair_result.model_dump(mode="json"),
            "selected_solver": bundle.solver_selection.selected_solver.value,
            "execution_mode": bundle.execution_mode.value,
        }

    def inspect_geometry(
        self,
        source_file_path: Path,
        *,
        geometry_kind_hint: GeometryKind | None = None,
    ) -> GeometryManifest:
        suffix = source_file_path.suffix.lower()
        source_hash = self.compute_sha256(source_file_path)
        warnings: list[str] = []
        blockers: list[str] = []
        geometry_kind = geometry_kind_hint or (GeometryKind.AIRCRAFT_VSP if suffix == ".vsp3" else GeometryKind.GENERAL_3D)
        format_name = suffix.lstrip(".")

        try:
            if suffix == ".stl":
                mesh = self._load_stl(source_file_path)
            elif suffix == ".obj":
                mesh = self._load_obj(source_file_path)
            elif suffix in {".step", ".stp"}:
                mesh = self._load_step_via_gmsh(source_file_path)
                format_name = "step"
            elif suffix == ".vsp3":
                mesh = TriangleMesh(vertices=[], faces=[])
                warnings.append(".vsp3 preflight is advisory only in this release.")
            else:
                mesh = TriangleMesh(vertices=[], faces=[])
                blockers.append(f"Unsupported geometry format: {suffix or 'unknown'}")
        except Exception as exc:
            mesh = TriangleMesh(vertices=[], faces=[])
            blockers.append(str(exc))

        stats = self._mesh_stats(source_file_path, mesh)
        if stats.face_count in {None, 0} and suffix != ".vsp3":
            blockers.append("No surface faces detected in geometry input.")

        return GeometryManifest(
            geometry_file=str(source_file_path),
            geometry_kind=geometry_kind,
            unit="unknown",
            format=format_name or None,
            stats=stats,
            source_hash=source_hash,
            warnings=self._unique_strings(warnings),
            blockers=self._unique_strings(blockers),
        )

    def repair_check(self, geometry_manifest: GeometryManifest) -> RepairCheckResult:
        blockers = list(geometry_manifest.blockers)
        repair_actions: list[str] = []
        if geometry_manifest.geometry_kind == GeometryKind.GENERAL_3D and geometry_manifest.stats.watertight is False:
            blockers.append("Geometry is not watertight.")
        if geometry_manifest.format in {"step", "stp"} and geometry_manifest.stats.face_count in {None, 0}:
            blockers.append("STEP tessellation did not produce a usable surface mesh.")
        if not blockers:
            repair_actions.append("Geometry inspection completed without mandatory repairs.")
        return RepairCheckResult(
            repairable=not blockers,
            repair_actions=repair_actions,
            blockers=self._unique_strings(blockers),
            preview_mesh_path=geometry_manifest.preview_path,
        )

    def select_solver(
        self,
        *,
        request: AnalysisRequest,
        geometry_manifest: GeometryManifest,
        repair_result: RepairCheckResult,
    ) -> SolverSelection:
        geometry_kind = geometry_manifest.geometry_kind
        preferred = request.solver_preference
        selected = preferred
        rationale = "User override selected the solver."
        if preferred == SolverKind.AUTO:
            if geometry_kind == GeometryKind.AIRCRAFT_VSP:
                selected = SolverKind.VSPAERO
                rationale = "Aircraft-style geometry maps to VSPAERO, but execution is deferred in this release."
            else:
                selected = SolverKind.SU2
                rationale = "General 3D geometry defaults to SU2 for the real vertical slice."

        candidates = [
            SolverCandidate(
                solver=SolverKind.SU2,
                score=0.92 if geometry_kind == GeometryKind.GENERAL_3D else 0.25,
                rationale="Supported real execution path for general_3d geometry.",
                runtime_estimate_minutes=35,
                memory_estimate_gb=4.0,
            ),
            SolverCandidate(
                solver=SolverKind.OPENFOAM,
                score=0.56,
                rationale="Deferred from this release.",
                runtime_estimate_minutes=120,
                memory_estimate_gb=8.0,
            ),
            SolverCandidate(
                solver=SolverKind.VSPAERO,
                score=0.82 if geometry_kind == GeometryKind.AIRCRAFT_VSP else 0.2,
                rationale="Advisory-only path for aircraft geometry in this release.",
                runtime_estimate_minutes=15,
                memory_estimate_gb=2.0,
            ),
        ]
        candidate_lookup = {candidate.solver: candidate for candidate in candidates}
        chosen = candidate_lookup.get(selected, candidate_lookup[SolverKind.SU2])
        fit_score = max(0.0, 1.0 - (0.25 * len(repair_result.blockers)))
        return SolverSelection(
            selected_solver=selected,
            rationale=rationale,
            candidates=candidates,
            user_override=None if preferred == SolverKind.AUTO else preferred,
            runtime_estimate_minutes=chosen.runtime_estimate_minutes,
            memory_estimate_gb=chosen.memory_estimate_gb,
            fit_score=fit_score,
        )

    def materialize_snapshot(
        self,
        snapshot_dir: Path,
        job_dir: Path,
        *,
        source_file_name: str,
    ) -> tuple[Path, Path]:
        source_snapshot = snapshot_dir / "input" / "original" / source_file_name
        normalized_snapshot = snapshot_dir / "normalized" / "normalized_manifest.json"
        target_source = job_dir / "input" / "original" / source_file_name
        target_normalized = job_dir / "normalized" / "normalized_manifest.json"
        target_source.parent.mkdir(parents=True, exist_ok=True)
        target_normalized.parent.mkdir(parents=True, exist_ok=True)
        self._materialize_file(source_snapshot, target_source)
        self._materialize_file(normalized_snapshot, target_normalized)
        (job_dir / "snapshot_ref.json").write_text(
            json_dumps(
                {
                    "snapshot_dir": str(snapshot_dir),
                    "source_file_name": source_file_name,
                    "materialized_at": str(target_source.stat().st_mtime_ns),
                }
            ),
            encoding="utf-8",
        )
        return target_source, target_normalized

    def prepare_case(
        self,
        *,
        job_id: str,
        job_dir: Path,
        request: AnalysisRequest,
        source_geometry_path: Path,
        normalized_manifest_path: Path,
        selected_solver: SolverKind,
    ) -> CaseManifest:
        if selected_solver != SolverKind.SU2:
            raise ValueError(f"Unsupported solver in this release: {selected_solver.value}")

        case_dir = job_dir / "case"
        mesh_dir = job_dir / "mesh"
        results_dir = job_dir / "results"
        logs_dir = job_dir / "logs"
        for directory in (case_dir, mesh_dir, results_dir, logs_dir):
            directory.mkdir(parents=True, exist_ok=True)

        case_geometry = case_dir / source_geometry_path.name
        manifest_copy = case_dir / "normalized_manifest.json"
        self._materialize_file(source_geometry_path, case_geometry)
        self._materialize_file(normalized_manifest_path, manifest_copy)

        cfg_path = case_dir / "case.cfg"
        mesh_path = mesh_dir / "mesh.su2"
        cfg_path.write_text(self._build_su2_config(request, mesh_path.name), encoding="utf-8")
        (case_dir / "case_manifest.json").write_text(
            json_dumps(
                {
                    "job_id": job_id,
                    "solver": selected_solver.value,
                    "geometry_path": str(case_geometry),
                    "mesh_path": str(mesh_path),
                    "cfg_path": str(cfg_path),
                }
            ),
            encoding="utf-8",
        )
        return CaseManifest(
            job_id=job_id,
            solver=selected_solver,
            case_dir=case_dir,
            cfg_path=cfg_path,
            geometry_path=case_geometry,
            mesh_path=mesh_path,
            results_dir=results_dir,
            logs_dir=logs_dir,
        )

    def generate_mesh(self, case_manifest: CaseManifest) -> Path:
        gmsh = shutil.which("gmsh") or os.environ.get("AERO_AGENT_GMSH_PATH")
        if not gmsh:
            raise RuntimeError("gmsh not detected.")

        command = [
            str(gmsh),
            str(case_manifest.geometry_path),
            "-3",
            "-format",
            "su2",
            "-o",
            str(case_manifest.mesh_path),
        ]
        mesh_log = case_manifest.logs_dir / "gmsh.log"
        with mesh_log.open("wb") as stream:
            completed = subprocess.run(
                command,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=300,
            )
        if completed.returncode != 0 or not case_manifest.mesh_path.exists():
            raise RuntimeError(f"gmsh mesh generation failed. See log: {mesh_log}")
        return case_manifest.mesh_path

    def launch_solver(self, *, job_id: str, case_manifest: CaseManifest) -> SolverRuntimeHandle:
        return self.solver_registry.launch(job_id, case_manifest.case_dir, case_manifest.cfg_path, case_manifest.solver)

    def wait_for_solver(self, handle: SolverRuntimeHandle) -> SolverRunManifest:
        return self.solver_registry.wait(handle)

    def terminate_solver(self, handle: SolverRuntimeHandle) -> None:
        self.solver_registry.terminate(handle)

    def extract_results(self, *, job_dir: Path, run_manifest: SolverRunManifest) -> CFDResults:
        solver_log_path = Path(run_manifest.logs_path or job_dir / "logs" / "solver.log")
        residual_source = self._find_first_existing(
            [
                job_dir / "results" / "residual_history.csv",
                job_dir / "results" / "history.csv",
                job_dir / "case" / "history.csv",
                job_dir / "case" / "history.dat",
            ]
        )
        if residual_source is None:
            raise RuntimeError("Residual history output not found after solver execution.")

        residual_history_path = job_dir / "results" / "residual_history.csv"
        if residual_source != residual_history_path:
            shutil.copy2(residual_source, residual_history_path)

        residual_history, coefficients = self._read_history(residual_history_path)
        coefficients_path = job_dir / "results" / "coefficients.json"
        coefficients_path.write_text(json_dumps(coefficients), encoding="utf-8")

        if not residual_history:
            raise RuntimeError("Residual history was empty.")
        if not all(math.isfinite(value) for value in coefficients.values()):
            raise RuntimeError("Coefficient extraction did not produce finite values.")

        metrics = [
            MetricRecord(name="CL", value=coefficients.get("CL", 0.0)),
            MetricRecord(name="CD", value=coefficients.get("CD", 0.0)),
            MetricRecord(name="Cm", value=coefficients.get("Cm", 0.0)),
            MetricRecord(name="iterations", value=float(residual_history[-1]["iteration"])),
            MetricRecord(name="final_residual", value=residual_history[-1]["residual"]),
        ]
        return CFDResults(
            solver_log_path=solver_log_path,
            residual_history_path=residual_history_path,
            coefficients_path=coefficients_path,
            residual_history=residual_history,
            coefficients=coefficients,
            metrics=metrics,
            fields=[],
            warnings=list(run_manifest.warnings),
        )

    def build_report(self, *, job_id: str, job_dir: Path, results: CFDResults) -> ReportManifest:
        report_dir = job_dir / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "report.html"
        summary_path = report_dir / "summary.json"
        summary_payload = {
            "job_id": job_id,
            "coefficients": results.coefficients,
            "residual_history_points": len(results.residual_history),
            "warnings": results.warnings,
            "solver_log_path": str(results.solver_log_path),
        }
        summary_path.write_text(json_dumps(summary_payload), encoding="utf-8")
        report_path.write_text(
            "\n".join(
                [
                    "<!doctype html>",
                    "<html lang=\"en\">",
                    "<head><meta charset=\"utf-8\" /><title>Aero Agent Report</title></head>",
                    "<body>",
                    f"<h1>Aero Agent Report for {job_id}</h1>",
                    "<p>This report is generated from actual pipeline artifacts and does not claim full field rendering.</p>",
                    "<h2>Coefficients</h2>",
                    "<ul>",
                    f"<li>CL: {results.coefficients.get('CL', 0.0):.6f}</li>",
                    f"<li>CD: {results.coefficients.get('CD', 0.0):.6f}</li>",
                    f"<li>Cm: {results.coefficients.get('Cm', 0.0):.6f}</li>",
                    "</ul>",
                    "<h2>Residual History</h2>",
                    f"<p>Points captured: {len(results.residual_history)}</p>",
                    "<h2>Warnings</h2>",
                    "<ul>",
                    *(f"<li>{warning}</li>" for warning in results.warnings),
                    "</ul>",
                    "</body>",
                    "</html>",
                ]
            ),
            encoding="utf-8",
        )
        return ReportManifest(
            title=f"Aero Agent Report {job_id}",
            summary="Residual history and aerodynamic coefficients extracted from the solver run.",
            html_path=str(report_path),
            json_path=str(summary_path),
            warnings=list(results.warnings),
        )

    def build_viewer(self, *, job_id: str, job_dir: Path, results: CFDResults) -> ViewerManifest:
        return self.viewer_builder.build(job_id, results.fields, output_dir=job_dir / "viewer")

    def package_case_bundle(self, *, job_dir: Path) -> Path:
        package_dir = job_dir / "package"
        package_dir.mkdir(parents=True, exist_ok=True)
        archive_path = package_dir / "case_bundle.zip"
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for root_name in ("case", "mesh", "results", "report", "viewer", "logs"):
                root = job_dir / root_name
                if not root.exists():
                    continue
                for path in root.rglob("*"):
                    if path.is_file():
                        bundle.write(path, arcname=str(path.relative_to(job_dir)))
        return archive_path

    def build_artifacts(
        self,
        *,
        results: CFDResults,
        report: ReportManifest,
        viewer: ViewerManifest,
        case_bundle: Path,
    ) -> list[ArtifactRecord]:
        artifacts = [
            ArtifactRecord(kind=ArtifactKind.SOLVER_LOG, path=str(results.solver_log_path), size_bytes=results.solver_log_path.stat().st_size),
            ArtifactRecord(
                kind=ArtifactKind.RESIDUAL_HISTORY,
                path=str(results.residual_history_path),
                size_bytes=results.residual_history_path.stat().st_size,
            ),
            ArtifactRecord(
                kind=ArtifactKind.COEFFICIENTS,
                path=str(results.coefficients_path),
                size_bytes=results.coefficients_path.stat().st_size,
            ),
            ArtifactRecord(kind=ArtifactKind.REPORT_HTML, path=report.html_path, size_bytes=Path(report.html_path).stat().st_size),
            ArtifactRecord(kind=ArtifactKind.VIEWER_BUNDLE, path=viewer.index_path, size_bytes=Path(viewer.index_path).stat().st_size),
            ArtifactRecord(kind=ArtifactKind.CASE_BUNDLE, path=str(case_bundle), size_bytes=case_bundle.stat().st_size),
        ]
        if report.json_path:
            artifacts.append(
                ArtifactRecord(kind=ArtifactKind.SUMMARY, path=str(report.json_path), size_bytes=Path(report.json_path).stat().st_size)
            )
        return artifacts

    def compute_sha256(self, path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _collect_runtime_blockers(
        self,
        *,
        request: AnalysisRequest,
        geometry_manifest: GeometryManifest,
        repair_result: RepairCheckResult,
        solver_selection: SolverSelection,
        install_status: InstallStatus,
        connection_mode: ConnectionMode,
    ) -> list[str]:
        blockers: list[str] = []
        blockers.extend(self._request_blockers(request))
        blockers.extend(geometry_manifest.blockers)
        blockers.extend(repair_result.blockers)
        if connection_mode != ConnectionMode.OPENAI_API:
            blockers.append("Only openai_api supports real execution in this release.")
        if geometry_manifest.geometry_kind != GeometryKind.GENERAL_3D:
            blockers.append("Only general_3d geometry supports real execution in this release.")
        if solver_selection.selected_solver != SolverKind.SU2:
            blockers.append("Only SU2 real execution is supported in this release.")
        if geometry_manifest.format not in {"stl", "obj", "step"}:
            blockers.append("Only STL/OBJ and successful STEP tessellation are supported in this release.")
        blockers.extend(install_status.runtime_blockers)
        return self._unique_strings(blockers)

    def _request_blockers(self, request: AnalysisRequest) -> list[str]:
        blockers: list[str] = []
        if request.reference_values is None or request.reference_values.area <= 0:
            blockers.append("Reference area must be provided and positive.")
        if request.frame is None:
            blockers.append("Frame specification is required.")
        if request.flow.velocity is None and request.flow.mach is None:
            blockers.append("Either velocity or Mach must be provided.")
        return blockers

    def _confidence_for(
        self,
        geometry_manifest: GeometryManifest,
        repair_result: RepairCheckResult,
        runtime_blockers: list[str],
    ) -> float:
        score = 0.9
        if geometry_manifest.stats.watertight is False:
            score -= 0.25
        score -= 0.1 * len(repair_result.blockers)
        score -= 0.08 * len(runtime_blockers)
        return max(0.0, min(1.0, score))

    def _build_su2_config(self, request: AnalysisRequest, mesh_filename: str) -> str:
        mach = request.flow.mach if request.flow.mach is not None else 0.18
        velocity = request.flow.velocity if request.flow.velocity is not None else 50.0
        aoa = request.flow.aoa
        sideslip = request.flow.sideslip
        ref_area = request.reference_values.area if request.reference_values else 1.0
        ref_length = request.reference_values.length if request.reference_values and request.reference_values.length else 1.0
        density = request.flow.density if request.flow.density is not None else 1.225
        viscosity = request.flow.viscosity if request.flow.viscosity is not None else 1.8e-5
        return "\n".join(
            [
                "SOLVER= RANS",
                "KIND_TURB_MODEL= SA",
                "MATH_PROBLEM= DIRECT",
                "RESTART_SOL= NO",
                f"MACH_NUMBER= {mach}",
                f"FREESTREAM_VELOCITY= {velocity}",
                f"AOA= {aoa}",
                f"SIDESLIP_ANGLE= {sideslip}",
                f"FREESTREAM_DENSITY= {density}",
                f"FREESTREAM_VISCOSITY= {viscosity}",
                f"REF_AREA= {ref_area}",
                f"REF_LENGTH= {ref_length}",
                f"MESH_FILENAME= {mesh_filename}",
                "CONV_NUM_METHOD_FLOW= JST",
                "TIME_DISCRE_FLOW= EULER_IMPLICIT",
                "INNER_ITER= 250",
                "CONV_FILENAME= history",
                "OUTPUT_FILES= (RESTART,PARAVIEW)",
            ]
        ) + "\n"

    def _mesh_stats(self, source_file_path: Path, mesh: TriangleMesh) -> GeometryStats:
        bbox = None
        if mesh.vertices:
            xs = [vertex[0] for vertex in mesh.vertices]
            ys = [vertex[1] for vertex in mesh.vertices]
            zs = [vertex[2] for vertex in mesh.vertices]
            bbox = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))
        estimated_scale = None
        if bbox is not None:
            estimated_scale = max(bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2])
        return GeometryStats(
            file_size_bytes=source_file_path.stat().st_size,
            bbox=bbox,
            face_count=len(mesh.faces),
            edge_count=len(mesh.faces) * 3 if mesh.faces else 0,
            component_count=1 if mesh.faces else 0,
            watertight=self._is_watertight(mesh) if mesh.faces else None,
            estimated_scale=estimated_scale,
        )

    def _load_stl(self, path: Path) -> TriangleMesh:
        data = path.read_bytes()
        mesh = self._try_parse_binary_stl(data)
        if mesh.faces:
            return mesh
        text = data.decode("utf-8", errors="ignore")
        return self._parse_ascii_stl(text)

    def _try_parse_binary_stl(self, data: bytes) -> TriangleMesh:
        if len(data) < 84:
            return TriangleMesh(vertices=[], faces=[])
        face_count = struct.unpack("<I", data[80:84])[0]
        expected_size = 84 + face_count * 50
        if expected_size != len(data):
            return TriangleMesh(vertices=[], faces=[])
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        index_map: dict[tuple[float, float, float], int] = {}
        offset = 84
        for _ in range(face_count):
            offset += 12
            face_indices: list[int] = []
            for _vertex in range(3):
                vertex = struct.unpack("<fff", data[offset : offset + 12])
                offset += 12
                rounded = self._round_vertex(vertex)
                if rounded not in index_map:
                    index_map[rounded] = len(vertices)
                    vertices.append(rounded)
                face_indices.append(index_map[rounded])
            faces.append((face_indices[0], face_indices[1], face_indices[2]))
            offset += 2
        return TriangleMesh(vertices=vertices, faces=faces)

    def _parse_ascii_stl(self, text: str) -> TriangleMesh:
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        index_map: dict[tuple[float, float, float], int] = {}
        current: list[int] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.lower().startswith("vertex "):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            rounded = self._round_vertex((float(parts[1]), float(parts[2]), float(parts[3])))
            if rounded not in index_map:
                index_map[rounded] = len(vertices)
                vertices.append(rounded)
            current.append(index_map[rounded])
            if len(current) == 3:
                faces.append((current[0], current[1], current[2]))
                current = []
        return TriangleMesh(vertices=vertices, faces=faces)

    def _load_obj(self, path: Path) -> TriangleMesh:
        vertices: list[tuple[float, float, float]] = []
        faces: list[tuple[int, int, int]] = []
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    vertices.append(self._round_vertex((float(parts[1]), float(parts[2]), float(parts[3]))))
            elif line.startswith("f "):
                indices: list[int] = []
                for token in line.split()[1:]:
                    head = token.split("/")[0]
                    if not head:
                        continue
                    index = int(head)
                    if index < 0:
                        index = len(vertices) + index
                    else:
                        index = index - 1
                    indices.append(index)
                if len(indices) >= 3:
                    for offset in range(1, len(indices) - 1):
                        faces.append((indices[0], indices[offset], indices[offset + 1]))
        return TriangleMesh(vertices=vertices, faces=faces)

    def _load_step_via_gmsh(self, path: Path) -> TriangleMesh:
        gmsh = shutil.which("gmsh") or os.environ.get("AERO_AGENT_GMSH_PATH")
        if not gmsh:
            raise RuntimeError("STEP tessellation requires gmsh.")
        with tempfile.TemporaryDirectory(prefix="aero-agent-step-") as temp_dir:
            temp_stl = Path(temp_dir) / "step_preview.stl"
            completed = subprocess.run(
                [str(gmsh), str(path), "-0", "-format", "stl", "-o", str(temp_stl)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=120,
            )
            if completed.returncode != 0 or not temp_stl.exists():
                raise RuntimeError("STEP tessellation failed.")
            return self._load_stl(temp_stl)

    def _is_watertight(self, mesh: TriangleMesh) -> bool:
        edge_counts: Counter[tuple[int, int]] = Counter()
        for face in mesh.faces:
            for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                edge_counts[tuple(sorted((start, end)))] += 1
        return bool(edge_counts) and all(count == 2 for count in edge_counts.values())

    def _read_history(self, history_path: Path) -> tuple[list[dict[str, float]], dict[str, float]]:
        residual_history: list[dict[str, float]] = []
        coefficients: dict[str, float] = {}
        with history_path.open("r", encoding="utf-8", errors="ignore", newline="") as stream:
            reader = csv.DictReader(stream)
            for index, row in enumerate(reader, start=1):
                normalized = {str(key).strip(): value for key, value in row.items() if key is not None}
                iteration = self._parse_float(normalized, ["iteration", "Iter", "INNER_ITER"], default=float(index))
                residual = self._parse_float(
                    normalized,
                    ["residual", "Residual", "RMS_RES", "Res_Flow[0]", "Res[0]"],
                    default=0.0,
                )
                point = {"iteration": float(iteration), "residual": float(residual)}
                cl = self._parse_float(normalized, ["CL", "cl"], default=math.nan)
                cd = self._parse_float(normalized, ["CD", "cd"], default=math.nan)
                cm = self._parse_float(normalized, ["CMz", "CM", "Cm", "cm"], default=math.nan)
                if math.isfinite(cl):
                    point["CL"] = cl
                    coefficients["CL"] = cl
                if math.isfinite(cd):
                    point["CD"] = cd
                    coefficients["CD"] = cd
                if math.isfinite(cm):
                    point["Cm"] = cm
                    coefficients["Cm"] = cm
                residual_history.append(point)
        if residual_history and not coefficients:
            last = residual_history[-1]
            for key in ("CL", "CD", "Cm"):
                value = last.get(key)
                if isinstance(value, float) and math.isfinite(value):
                    coefficients[key] = value
        if {"CL", "CD", "Cm"} - set(coefficients):
            missing = sorted({"CL", "CD", "Cm"} - set(coefficients))
            raise RuntimeError(f"Unable to extract coefficient summary from history file; missing {', '.join(missing)}.")
        return residual_history, coefficients

    def _parse_float(self, row: dict[str, str | None], candidates: list[str], *, default: float) -> float:
        for candidate in candidates:
            if candidate not in row:
                continue
            raw = row[candidate]
            if raw in (None, ""):
                continue
            try:
                return float(raw)
            except ValueError:
                continue
        return default

    def _find_first_existing(self, candidates: list[Path]) -> Path | None:
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _materialize_file(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        try:
            target.hardlink_to(source)
        except OSError:
            shutil.copy2(source, target)

    def _round_vertex(self, vertex: tuple[float, float, float]) -> tuple[float, float, float]:
        return (round(vertex[0], 8), round(vertex[1], 8), round(vertex[2], 8))

    def _unique_strings(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value and value not in seen:
                ordered.append(value)
                seen.add(value)
        return ordered
