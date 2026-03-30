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
from aero_agent_solver_adapters import GmshRunManifest, SolverAdapterRegistry, SolverRuntimeHandle
from aero_agent_viewer_assets import ViewerAssetBuilder


@dataclass(slots=True)
class TriangleMesh:
    vertices: list[tuple[float, float, float]]
    faces: list[tuple[int, int, int]]


@dataclass(slots=True)
class NormalizedGeometryArtifacts:
    normalization_manifest_path: Path
    geometry_path: Path
    geometry_hash: str
    summary: dict[str, object]


@dataclass(slots=True)
class MaterializedSnapshot:
    source_path: Path
    normalized_manifest_path: Path
    normalization_manifest_path: Path
    normalized_geometry_path: Path


@dataclass(slots=True)
class CaseManifest:
    job_id: str
    solver: SolverKind
    fidelity: str
    case_dir: Path
    cfg_path: Path
    geometry_path: Path
    normalized_manifest_path: Path
    normalization_manifest_path: Path
    mesh_script_path: Path
    mesh_manifest_path: Path
    mesh_log_path: Path
    case_manifest_path: Path
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
        normalized_geometry_hash: str,
        normalization_summary: dict[str, object],
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
            normalized_geometry_hash=normalized_geometry_hash,
            normalization_summary=normalization_summary,
            physics_grade="stable_trend_grade",
            mesh_strategy="box_farfield",
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

    def normalized_manifest_payload(
        self,
        bundle: PreflightBundle,
        *,
        normalization_summary: dict[str, object] | None = None,
        ai_assist_mode: AIAssistMode | None = None,
    ) -> dict[str, object]:
        payload = {
            "geometry_manifest": bundle.geometry_manifest.model_dump(mode="json"),
            "repair_result": bundle.repair_result.model_dump(mode="json"),
            "selected_solver": bundle.solver_selection.selected_solver.value,
            "execution_mode": bundle.execution_mode.value,
        }
        if ai_assist_mode is not None:
            payload["ai_assist_mode"] = ai_assist_mode.value
        if normalization_summary is not None:
            payload["normalization_summary"] = normalization_summary
        return payload

    def normalize_geometry_artifacts(
        self,
        *,
        request: AnalysisRequest,
        source_file_path: Path,
        geometry_manifest: GeometryManifest,
        repair_result: RepairCheckResult,
        output_dir: Path,
    ) -> NormalizedGeometryArtifacts:
        output_dir.mkdir(parents=True, exist_ok=True)
        geometry_dir = output_dir / "geometry"
        geometry_dir.mkdir(parents=True, exist_ok=True)

        mesh = self._load_triangle_mesh(source_file_path)
        if not mesh.faces:
            raise RuntimeError("Geometry normalization requires a triangulated surface mesh.")

        normalized_mesh, normalization_summary = self._normalize_mesh(mesh, request=request, source_file_path=source_file_path)
        geometry_path = geometry_dir / "body_normalized.stl"
        self._write_binary_stl(geometry_path, normalized_mesh)

        normalized_bbox = self._bbox_from_vertices(normalized_mesh.vertices)
        summary = {
            "source_format": geometry_manifest.format or source_file_path.suffix.lstrip("."),
            "declared_unit": request.unit,
            "canonical_unit": "m",
            "scale_factor_to_meter": normalization_summary["scale_factor"],
            "axis_mapping": normalization_summary["axis_mapping"],
            "source_bbox": list(geometry_manifest.stats.bbox) if geometry_manifest.stats.bbox else None,
            "normalized_bbox": list(normalized_bbox) if normalized_bbox else None,
            "face_count": geometry_manifest.stats.face_count,
            "component_count": geometry_manifest.stats.component_count,
            "watertight": geometry_manifest.stats.watertight,
            "repair_actions": list(repair_result.repair_actions),
            "caveats": list(normalization_summary["caveats"]),
        }
        normalization_manifest_path = output_dir / "normalization_manifest.json"
        normalization_manifest_path.write_text(json_dumps(summary), encoding="utf-8")
        geometry_hash = self.compute_sha256(geometry_path)
        return NormalizedGeometryArtifacts(
            normalization_manifest_path=normalization_manifest_path,
            geometry_path=geometry_path,
            geometry_hash=geometry_hash,
            summary=summary,
        )

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
    ) -> MaterializedSnapshot:
        source_snapshot = snapshot_dir / "input" / "original" / source_file_name
        normalized_snapshot = snapshot_dir / "normalized" / "normalized_manifest.json"
        normalization_snapshot = snapshot_dir / "normalized" / "normalization_manifest.json"
        normalized_geometry_snapshot = snapshot_dir / "normalized" / "geometry" / "body_normalized.stl"
        target_source = job_dir / "input" / "original" / source_file_name
        target_normalized = job_dir / "normalized" / "normalized_manifest.json"
        target_normalization_manifest = job_dir / "normalized" / "normalization_manifest.json"
        target_normalized_geometry = job_dir / "normalized" / "geometry" / "body_normalized.stl"
        target_source.parent.mkdir(parents=True, exist_ok=True)
        target_normalized.parent.mkdir(parents=True, exist_ok=True)
        target_normalization_manifest.parent.mkdir(parents=True, exist_ok=True)
        target_normalized_geometry.parent.mkdir(parents=True, exist_ok=True)
        self._materialize_file(source_snapshot, target_source)
        self._materialize_file(normalized_snapshot, target_normalized)
        self._materialize_file(normalization_snapshot, target_normalization_manifest)
        self._materialize_file(normalized_geometry_snapshot, target_normalized_geometry)
        (job_dir / "snapshot_ref.json").write_text(
            json_dumps(
                {
                    "preflight_id": snapshot_dir.name,
                    "snapshot_dir": str(snapshot_dir),
                    "source_file_name": source_file_name,
                    "normalized_geometry": str(target_normalized_geometry),
                    "materialized_at": str(target_source.stat().st_mtime_ns),
                }
            ),
            encoding="utf-8",
        )
        return MaterializedSnapshot(
            source_path=target_source,
            normalized_manifest_path=target_normalized,
            normalization_manifest_path=target_normalization_manifest,
            normalized_geometry_path=target_normalized_geometry,
        )

    def prepare_case(
        self,
        *,
        job_id: str,
        job_dir: Path,
        request: AnalysisRequest,
        normalized_geometry_path: Path,
        normalized_manifest_path: Path,
        normalization_manifest_path: Path,
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

        case_geometry = case_dir / "body_normalized.stl"
        manifest_copy = case_dir / "normalized_manifest.json"
        normalization_copy = case_dir / "normalization_manifest.json"
        self._materialize_file(normalized_geometry_path, case_geometry)
        self._materialize_file(normalized_manifest_path, manifest_copy)
        self._materialize_file(normalization_manifest_path, normalization_copy)

        cfg_path = case_dir / "case.cfg"
        mesh_script_path = mesh_dir / "farfield.geo"
        mesh_path = mesh_dir / "mesh.su2"
        mesh_log_path = mesh_dir / "gmsh.log"
        mesh_manifest_path = mesh_dir / "mesh_manifest.json"
        case_manifest_path = case_dir / "case_manifest.json"
        cfg_path.write_text(self._build_su2_config(request, mesh_path.name), encoding="utf-8")
        case_manifest_path.write_text(
            json_dumps(
                {
                    "job_id": job_id,
                    "solver": selected_solver.value,
                    "geometry_path": str(case_geometry),
                    "mesh_path": str(mesh_path),
                    "cfg_path": str(cfg_path),
                    "mesh_script_path": str(mesh_script_path),
                    "mesh_manifest_path": str(mesh_manifest_path),
                    "mesh_log_path": str(mesh_log_path),
                    "physics_grade": "stable_trend_grade",
                    "mesh_strategy": "box_farfield",
                }
            ),
            encoding="utf-8",
        )
        return CaseManifest(
            job_id=job_id,
            solver=selected_solver,
            fidelity=request.fidelity,
            case_dir=case_dir,
            cfg_path=cfg_path,
            geometry_path=case_geometry,
            normalized_manifest_path=manifest_copy,
            normalization_manifest_path=normalization_copy,
            mesh_script_path=mesh_script_path,
            mesh_manifest_path=mesh_manifest_path,
            mesh_log_path=mesh_log_path,
            case_manifest_path=case_manifest_path,
            mesh_path=mesh_path,
            results_dir=results_dir,
            logs_dir=logs_dir,
        )

    def generate_mesh(self, *, job_id: str, case_manifest: CaseManifest) -> Path:
        handle = self.launch_mesh(job_id=job_id, case_manifest=case_manifest)
        return self.wait_for_mesh(handle, case_manifest=case_manifest)

    def launch_mesh(self, *, job_id: str, case_manifest: CaseManifest) -> SolverRuntimeHandle:
        normalization_summary = self._read_json_file(case_manifest.normalization_manifest_path)
        bbox = normalization_summary.get("normalized_bbox")
        if not isinstance(bbox, list) or len(bbox) != 6:
            raise RuntimeError("Normalized bbox is missing; cannot build farfield mesh.")
        farfield_geo = self._build_farfield_geo(
            case_manifest=case_manifest,
            bbox=tuple(float(value) for value in bbox),
        )
        case_manifest.mesh_script_path.write_text(farfield_geo, encoding="utf-8")
        return self.solver_registry.launch_gmsh(
            job_id=job_id,
            input_path=case_manifest.mesh_script_path,
            output_path=case_manifest.mesh_path,
            work_dir=case_manifest.mesh_path.parent,
            log_path=case_manifest.mesh_log_path,
            manifest_path=case_manifest.mesh_path.parent / "gmsh_run_manifest.json",
        )

    def wait_for_mesh(self, handle: SolverRuntimeHandle, *, case_manifest: CaseManifest) -> Path:
        completed = self.solver_registry.wait_gmsh(handle)
        if completed.status != JobStatus.COMPLETED or not case_manifest.mesh_path.exists():
            raise RuntimeError(f"gmsh mesh generation failed. See log: {case_manifest.mesh_log_path}")
        normalization_summary = self._read_json_file(case_manifest.normalization_manifest_path)
        bbox = normalization_summary.get("normalized_bbox")
        bbox_tuple = tuple(float(value) for value in bbox) if isinstance(bbox, list) and len(bbox) == 6 else None
        case_manifest.mesh_manifest_path.write_text(
            json_dumps(
                {
                    "mesh_strategy": "box_farfield",
                    "normalized_geometry_hash": self.compute_sha256(case_manifest.geometry_path),
                    "farfield_extents": self._farfield_extents(bbox_tuple) if bbox_tuple is not None else {},
                    "marker_names": {"body": "body", "farfield": "farfield", "symmetry": "reserved"},
                    "mesh_size_controls": self._mesh_sizing_from_bbox(
                        bbox_tuple,
                        fidelity=case_manifest.fidelity,
                    ),
                    "gmsh_command": list(completed.command),
                    "gmsh_exit_status": completed.status.value,
                    "mesh_file_hash": self.compute_sha256(case_manifest.mesh_path),
                    "mesh_path": str(case_manifest.mesh_path),
                    "mesh_log_path": str(case_manifest.mesh_log_path),
                    "gmsh_run_manifest_path": str(case_manifest.mesh_path.parent / "gmsh_run_manifest.json"),
                }
            ),
            encoding="utf-8",
        )
        return case_manifest.mesh_path

    def launch_solver(self, *, job_id: str, case_manifest: CaseManifest) -> SolverRuntimeHandle:
        return self.solver_registry.launch(job_id, case_manifest.case_dir, case_manifest.cfg_path, case_manifest.solver)

    def wait_for_solver(self, handle: SolverRuntimeHandle) -> SolverRunManifest:
        return self.solver_registry.wait(handle)

    def terminate_solver(self, handle: SolverRuntimeHandle) -> None:
        if getattr(handle, "runtime_kind", None) and getattr(handle.runtime_kind, "value", "") == "gmsh":
            self.solver_registry.terminate_gmsh(handle)
            return
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
        normalization_manifest_path = job_dir / "normalized" / "normalization_manifest.json"
        normalized_manifest_path = job_dir / "normalized" / "normalized_manifest.json"
        mesh_manifest_path = job_dir / "mesh" / "mesh_manifest.json"
        solver_run_manifest_path = job_dir / "results" / "solver_run_manifest.json"
        snapshot_ref_path = job_dir / "snapshot_ref.json"
        normalization_summary = self._read_json_file(normalization_manifest_path)
        normalized_manifest = self._read_json_file(normalized_manifest_path)
        mesh_summary = self._read_json_file(mesh_manifest_path)
        solver_run_summary = self._read_json_file(solver_run_manifest_path)
        snapshot_ref = self._read_json_file(snapshot_ref_path)
        started_at = solver_run_summary.get("started_at")
        finished_at = solver_run_summary.get("finished_at")
        runtime_duration_seconds: float | None = None
        if isinstance(started_at, str) and isinstance(finished_at, str):
            try:
                start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                end = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                runtime_duration_seconds = max((end - start).total_seconds(), 0.0)
            except ValueError:
                runtime_duration_seconds = None
        summary_payload = {
            "job_id": job_id,
            "preflight_id": snapshot_ref.get("preflight_id"),
            "source_file_name": snapshot_ref.get("source_file_name"),
            "normalized_geometry_hash": self.compute_sha256(job_dir / "normalized" / "geometry" / "body_normalized.stl")
            if (job_dir / "normalized" / "geometry" / "body_normalized.stl").exists()
            else None,
            "selected_solver": normalized_manifest.get("selected_solver"),
            "execution_mode": normalized_manifest.get("execution_mode"),
            "ai_assist_mode": normalized_manifest.get("ai_assist_mode"),
            "physics_grade": "stable_trend_grade",
            "mesh_strategy": "box_farfield",
            "coefficients": results.coefficients,
            "residual_history_points": len(results.residual_history),
            "warnings": results.warnings,
            "solver_log_path": str(results.solver_log_path),
            "normalization_manifest": str(normalization_manifest_path) if normalization_manifest_path.exists() else None,
            "mesh_manifest": str(mesh_manifest_path) if mesh_manifest_path.exists() else None,
            "solver_run_manifest": str(solver_run_manifest_path) if solver_run_manifest_path.exists() else None,
            "residual_history": str(results.residual_history_path),
            "runtime_duration_seconds": runtime_duration_seconds,
            "normalization_summary": normalization_summary,
            "mesh_summary": mesh_summary,
            "solver_run_summary": solver_run_summary,
            "caveats": [
                "Stable trend-grade external SU2 path.",
                "Euler wall/farfield setup only in this release.",
                "Boundary layer resolution, viscous wall treatment, and full field rendering are deferred.",
            ],
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
                    "<p>This report is generated from actual pipeline artifacts. It is a stable trend-grade external SU2 path and does not claim full field rendering or engineering-grade viscous fidelity.</p>",
                    "<h2>Normalization</h2>",
                    f"<p>Canonical unit: {normalization_summary.get('canonical_unit', 'm')}</p>",
                    f"<p>Scale factor: {normalization_summary.get('scale_factor_to_meter', 'n/a')}</p>",
                    f"<p>Axis mapping: {json.dumps(normalization_summary.get('axis_mapping', {}), ensure_ascii=True)}</p>",
                    "<h2>External Mesh</h2>",
                    f"<p>Strategy: {mesh_summary.get('mesh_strategy', 'box_farfield')}</p>",
                    f"<p>Farfield extents: {json.dumps(mesh_summary.get('farfield_extents', {}), ensure_ascii=True)}</p>",
                    f"<p>Selected solver: {normalized_manifest.get('selected_solver', 'su2')}</p>",
                    f"<p>Execution mode: {normalized_manifest.get('execution_mode', 'real')}</p>",
                    f"<p>AI assist mode: {normalized_manifest.get('ai_assist_mode', 'unknown')}</p>",
                    "<h2>Coefficients</h2>",
                    "<ul>",
                    f"<li>CL: {results.coefficients.get('CL', 0.0):.6f}</li>",
                    f"<li>CD: {results.coefficients.get('CD', 0.0):.6f}</li>",
                    f"<li>Cm: {results.coefficients.get('Cm', 0.0):.6f}</li>",
                    "</ul>",
                    "<h2>Residual History</h2>",
                    f"<p>Points captured: {len(results.residual_history)}</p>",
                    f"<p>Solver runtime: {solver_run_summary.get('runtime_backend', 'unknown')}</p>",
                    "<h2>Warnings</h2>",
                    "<ul>",
                    *(f"<li>{warning}</li>" for warning in results.warnings),
                    "<li>Boundary layer resolution, viscous wall treatment, and RANS credibility are deferred in this release.</li>",
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
            for root_name in ("case", "mesh", "results", "report", "viewer", "logs", "normalized"):
                root = job_dir / root_name
                if not root.exists():
                    continue
                for path in root.rglob("*"):
                    if path.is_file():
                        bundle.write(path, arcname=str(path.relative_to(job_dir)))
            snapshot_ref = job_dir / "snapshot_ref.json"
            if snapshot_ref.exists():
                bundle.write(snapshot_ref, arcname="snapshot_ref.json")
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
        optional_artifacts = [
            (ArtifactKind.NORMALIZATION_MANIFEST, results.coefficients_path.parent.parent / "normalized" / "normalization_manifest.json"),
            (ArtifactKind.MESH_MANIFEST, results.coefficients_path.parent.parent / "mesh" / "mesh_manifest.json"),
            (ArtifactKind.MESH_LOG, results.coefficients_path.parent.parent / "mesh" / "gmsh.log"),
            (ArtifactKind.SOLVER_RUN_MANIFEST, results.coefficients_path.parent / "solver_run_manifest.json"),
        ]
        for kind, path in optional_artifacts:
            if path.exists():
                artifacts.append(ArtifactRecord(kind=kind, path=str(path), size_bytes=path.stat().st_size))
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
        elif request.frame.forward_axis == request.frame.up_axis:
            blockers.append("Forward axis and up axis must be different.")
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
        aoa = request.flow.aoa
        sideslip = request.flow.sideslip
        ref_area = request.reference_values.area if request.reference_values else 1.0
        ref_length = request.reference_values.length if request.reference_values and request.reference_values.length else 1.0
        iter_count = {"fast": 200, "balanced": 400, "high": 700}.get(request.fidelity, 400)
        cfl = {"fast": 1.5, "balanced": 1.0, "high": 0.7}.get(request.fidelity, 1.0)
        moment_center = request.frame.moment_center if request.frame and request.frame.moment_center else (0.0, 0.0, 0.0)
        return "\n".join(
            [
                "SOLVER= EULER",
                "MATH_PROBLEM= DIRECT",
                "RESTART_SOL= NO",
                "SYSTEM_MEASUREMENTS= SI",
                f"MACH_NUMBER= {mach}",
                f"AOA= {aoa}",
                f"SIDESLIP_ANGLE= {sideslip}",
                f"REF_AREA= {ref_area}",
                f"REF_LENGTH= {ref_length}",
                f"REF_ORIGIN_MOMENT_X= {moment_center[0]}",
                f"REF_ORIGIN_MOMENT_Y= {moment_center[1]}",
                f"REF_ORIGIN_MOMENT_Z= {moment_center[2]}",
                f"MESH_FILENAME= {mesh_filename}",
                "MARKER_EULER= ( body )",
                "MARKER_MONITORING= ( body )",
                "MARKER_PLOTTING= ( body )",
                "MARKER_FAR= ( farfield )",
                "CONV_NUM_METHOD_FLOW= JST",
                "TIME_DISCRE_FLOW= EULER_IMPLICIT",
                f"CFL_NUMBER= {cfl}",
                f"ITER= {iter_count}",
                "CONV_FIELD= RMS_DENSITY",
                "CONV_RESIDUAL_MINVAL= -6",
                "CONV_STARTITER= 10",
                "TABULAR_FORMAT= CSV",
                "CONV_FILENAME= history",
                "OUTPUT_FILES= (RESTART, PARAVIEW, SURFACE_CSV)",
            ]
        ) + "\n"

    def _load_triangle_mesh(self, path: Path) -> TriangleMesh:
        suffix = path.suffix.lower()
        if suffix == ".stl":
            return self._load_stl(path)
        if suffix == ".obj":
            return self._load_obj(path)
        if suffix in {".step", ".stp"}:
            return self._load_step_via_gmsh(path)
        raise RuntimeError(f"Unsupported geometry format for normalization: {suffix or 'unknown'}")

    def _normalize_mesh(
        self,
        mesh: TriangleMesh,
        *,
        request: AnalysisRequest,
        source_file_path: Path,
    ) -> tuple[TriangleMesh, dict[str, object]]:
        scale_factor = {
            "m": 1.0,
            "cm": 0.01,
            "mm": 0.001,
            "in": 0.0254,
            "ft": 0.3048,
        }[request.unit]
        frame = request.frame
        if frame is None:
            raise RuntimeError("Frame specification is required for normalization.")
        if frame.forward_axis == frame.up_axis:
            raise RuntimeError("Forward axis and up axis must be different for normalization.")

        side_axis = self._remaining_axis(frame.forward_axis, frame.up_axis)
        axis_indices = {"x": 0, "y": 1, "z": 2}
        order = (
            axis_indices[frame.forward_axis],
            axis_indices[side_axis],
            axis_indices[frame.up_axis],
        )

        normalized_vertices: list[tuple[float, float, float]] = []
        for vertex in mesh.vertices:
            components = (vertex[0], vertex[1], vertex[2])
            normalized_vertices.append(
                self._round_vertex(
                    (
                        components[order[0]] * scale_factor,
                        components[order[1]] * scale_factor,
                        components[order[2]] * scale_factor,
                    )
                )
            )

        summary = {
            "source_file": str(source_file_path),
            "scale_factor": scale_factor,
            "axis_mapping": {
                "forward_to": "+X",
                "up_to": "+Z",
                "side_to": "+Y",
                "source_forward_axis": frame.forward_axis,
                "source_up_axis": frame.up_axis,
                "source_side_axis": side_axis,
            },
            "caveats": [
                "Canonical solver geometry is meter-based and uses positive-axis permutations only.",
                "Symmetry-plane execution is deferred; this release always builds a full-domain farfield box.",
            ],
        }
        return TriangleMesh(vertices=normalized_vertices, faces=list(mesh.faces)), summary

    def _write_binary_stl(self, path: Path, mesh: TriangleMesh) -> None:
        header = b"AeroAgent normalized geometry".ljust(80, b" ")
        with path.open("wb") as stream:
            stream.write(header)
            stream.write(struct.pack("<I", len(mesh.faces)))
            for face in mesh.faces:
                normal = self._triangle_normal(
                    mesh.vertices[face[0]],
                    mesh.vertices[face[1]],
                    mesh.vertices[face[2]],
                )
                stream.write(struct.pack("<fff", *normal))
                for index in face:
                    stream.write(struct.pack("<fff", *mesh.vertices[index]))
                stream.write(struct.pack("<H", 0))

    def _triangle_normal(
        self,
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        c: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length == 0:
            return (0.0, 0.0, 0.0)
        return (nx / length, ny / length, nz / length)

    def _bbox_from_vertices(
        self,
        vertices: list[tuple[float, float, float]],
    ) -> tuple[float, float, float, float, float, float] | None:
        if not vertices:
            return None
        xs = [vertex[0] for vertex in vertices]
        ys = [vertex[1] for vertex in vertices]
        zs = [vertex[2] for vertex in vertices]
        return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

    def _remaining_axis(self, forward_axis: str, up_axis: str) -> str:
        for axis in ("x", "y", "z"):
            if axis not in {forward_axis, up_axis}:
                return axis
        raise RuntimeError("Unable to derive side axis from frame definition.")

    def _farfield_extents(
        self,
        bbox: tuple[float, float, float, float, float, float],
    ) -> dict[str, float]:
        xmin, ymin, zmin, xmax, ymax, zmax = bbox
        length = max(xmax - xmin, ymax - ymin, zmax - zmin, 1e-6)
        return {
            "xmin": xmin - 10.0 * length,
            "xmax": xmax + 20.0 * length,
            "ymin": ymin - 10.0 * length,
            "ymax": ymax + 10.0 * length,
            "zmin": zmin - 10.0 * length,
            "zmax": zmax + 10.0 * length,
            "characteristic_length": length,
        }

    def _mesh_sizing_from_bbox(
        self,
        bbox: tuple[float, float, float, float, float, float],
        *,
        fidelity: str = "balanced",
    ) -> dict[str, float]:
        length = self._farfield_extents(bbox)["characteristic_length"]
        if fidelity == "fast":
            body = max(length / 8.0, 1e-4)
            far = max(length / 2.0, body)
        elif fidelity == "high":
            body = max(length / 18.0, 1e-4)
            far = max(length / 1.2, body)
        else:
            body = max(length / 12.0, 1e-4)
            far = max(length / 1.8, body)
        return {
            "body_size": body,
            "farfield_size": far,
            "transition_distance": 4.0 * length,
        }

    def _build_farfield_geo(
        self,
        *,
        case_manifest: CaseManifest,
        bbox: tuple[float, float, float, float, float, float],
    ) -> str:
        extents = self._farfield_extents(bbox)
        sizes = self._mesh_sizing_from_bbox(bbox, fidelity=case_manifest.fidelity)
        geometry_name = case_manifest.geometry_path.name.replace("\\", "/")
        mesh_name = case_manifest.mesh_path.name.replace("\\", "/")
        return "\n".join(
            [
                'SetFactory("OpenCASCADE");',
                f'Merge "{geometry_name}";',
                "angle = 40*Pi/180;",
                "ClassifySurfaces{angle, 1, 1, Pi};",
                "CreateGeometry;",
                "body_surfaces[] = Surface{:};",
                "Surface Loop(1) = {body_surfaces[]};",
                "Volume(1) = {1};",
                f'Box(2) = {{{extents["xmin"]}, {extents["ymin"]}, {extents["zmin"]}, {extents["xmax"] - extents["xmin"]}, {extents["ymax"] - extents["ymin"]}, {extents["zmax"] - extents["zmin"]}}};',
                "farfield_surfaces[] = Boundary{ Volume{2}; };",
                "fluid[] = BooleanDifference{ Volume{2}; Delete; }{ Volume{1}; Delete; };",
                "Physical Surface(\"body\") = {body_surfaces[]};",
                "Physical Surface(\"farfield\") = {farfield_surfaces[]};",
                "Physical Volume(\"fluid\") = {fluid[]};",
                "Field[1] = Distance;",
                "Field[1].SurfacesList = {body_surfaces[]};",
                "Field[2] = Threshold;",
                "Field[2].IField = 1;",
                f'Field[2].LcMin = {sizes["body_size"]};',
                f'Field[2].LcMax = {sizes["farfield_size"]};',
                "Field[2].DistMin = 0.0;",
                f'Field[2].DistMax = {sizes["transition_distance"]};',
                "Background Field = 2;",
                "Mesh.Algorithm3D = 4;",
                f'Save "{mesh_name}";',
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
                cl = self._parse_float(normalized, ["CL", "cl", "LIFT", "Lift", "CLift", "C_l"], default=math.nan)
                cd = self._parse_float(normalized, ["CD", "cd", "DRAG", "Drag", "CDrag", "C_d"], default=math.nan)
                cm = self._parse_float(
                    normalized,
                    ["CMz", "CM", "Cm", "cm", "MOMENT_Z", "Moment_Z", "C_m"],
                    default=math.nan,
                )
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

    def _read_json_file(self, path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

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
