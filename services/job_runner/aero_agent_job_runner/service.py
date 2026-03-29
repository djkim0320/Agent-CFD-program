from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .contracts import JobExecutionContext


class RunnerResult(BaseModel):
    selected_solver: str
    rationale: str
    metrics: dict[str, Any]
    warnings: list[str] = []
    artifacts: list[dict[str, Any]] = []
    report_path: str
    summary_path: str


class JobExecutionService:
    def __init__(self, cfd_core: Any, provider_router: Any, artifact_builder: Any):
        self.cfd_core = cfd_core
        self.provider_router = provider_router
        self.artifact_builder = artifact_builder

    def run_preflight(self, context: JobExecutionContext) -> dict[str, Any]:
        inspection = self.cfd_core.inspect_geometry(context.source_file_path)
        plan = self.provider_router.select_solver(context.request, inspection)
        plan["geometry"] = inspection
        return plan

    def run_execution(self, context: JobExecutionContext, approval: bool = True) -> RunnerResult:
        if not approval:
            raise ValueError("approval required before execution")
        self._ensure_dirs(context.job_dir)
        mesh_result = self.cfd_core.generate_case(context.job_dir, context.request)
        solver_result = self.cfd_core.run_solver(context.job_dir, mesh_result["selected_solver"])
        postprocess = self.cfd_core.postprocess(context.job_dir, solver_result)
        artifacts = self.artifact_builder.package(context.job_dir, postprocess)
        return RunnerResult(
            selected_solver=mesh_result["selected_solver"],
            rationale=mesh_result["rationale"],
            metrics=postprocess["metrics"],
            warnings=postprocess.get("warnings", []),
            artifacts=artifacts.get("artifacts", []),
            report_path=postprocess["report_path"],
            summary_path=postprocess["summary_path"],
        )

    def retry_once(self, context: JobExecutionContext) -> dict[str, Any]:
        return {
            "retry": True,
            "timestamp": datetime.now(UTC).isoformat(),
            "job_id": context.job_id,
        }

    def _ensure_dirs(self, job_dir: Path) -> None:
        for relative in ["case", "mesh", "results", "report", "viewer", "logs", "package"]:
            (job_dir / relative).mkdir(parents=True, exist_ok=True)


class DefaultProviderRouter:
    def select_solver(self, request: dict[str, Any], inspection: dict[str, Any]) -> dict[str, Any]:
        geometry_kind = request.get("geometry_kind", "general_3d")
        solver_preference = request.get("solver_preference", "auto")
        if solver_preference != "auto":
            selected = solver_preference
            rationale = f"User override selected {selected}."
        elif geometry_kind == "aircraft_vsp":
            selected = "vspaero"
            rationale = "Aircraft .vsp3 geometry fits VSPAERO best."
        else:
            selected = "su2"
            rationale = "General 3D geometry defaults to SU2 for balanced external aerodynamics."
        return {
            "selected_solver": selected,
            "rationale": rationale,
            "runtime_estimate_minutes": 20 if selected == "su2" else 10,
            "memory_estimate_gb": 4.0 if selected == "su2" else 2.0,
            "warnings": inspection.get("warnings", []),
        }


class DefaultCfdCore:
    def inspect_geometry(self, source_file_path: Path) -> dict[str, Any]:
        suffix = source_file_path.suffix.lower()
        geometry_kind = "aircraft_vsp" if suffix == ".vsp3" else "general_3d"
        return {
            "file_name": source_file_path.name,
            "suffix": suffix,
            "geometry_kind": geometry_kind,
            "warnings": [],
            "repairable": True,
        }

    def generate_case(self, job_dir: Path, request: dict[str, Any]) -> dict[str, Any]:
        selected_solver = request.get("solver_preference", "auto")
        if selected_solver == "auto":
            selected_solver = "vspaero" if request.get("geometry_kind") == "aircraft_vsp" else "su2"
        case_manifest = {
            "selected_solver": selected_solver,
            "request": request,
            "created_at": datetime.now(UTC).isoformat(),
        }
        (job_dir / "case" / "case_manifest.json").write_text(
            json.dumps(case_manifest, indent=2),
            encoding="utf-8",
        )
        return {
            "selected_solver": selected_solver,
            "rationale": f"Selected {selected_solver} from request and geometry hints.",
        }

    def run_solver(self, job_dir: Path, solver_kind: str) -> dict[str, Any]:
        time.sleep(0.05)
        run_manifest = {
            "solver_kind": solver_kind,
            "status": "completed",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        (job_dir / "results" / "solver_run.json").write_text(
            json.dumps(run_manifest, indent=2),
            encoding="utf-8",
        )
        return run_manifest

    def postprocess(self, job_dir: Path, solver_result: dict[str, Any]) -> dict[str, Any]:
        report_path = job_dir / "report" / "report.html"
        summary_path = job_dir / "report" / "summary.json"
        viewer_index_path = job_dir / "viewer" / "index.html"
        viewer_manifest_path = job_dir / "viewer" / "viewer_manifest.json"
        report_path.write_text(
            (
                "<html><body><h1>Aero Analysis Report</h1>"
                "<p>Mock deterministic pipeline output.</p>"
                f"<p>Solver: {solver_result['solver_kind']}</p>"
                "</body></html>"
            ),
            encoding="utf-8",
        )
        summary = {
            "solver": solver_result["solver_kind"],
            "status": solver_result["status"],
            "generated_at": datetime.now(UTC).isoformat(),
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        viewer_index_path.write_text(
            "<html><body><h1>Viewer Placeholder</h1><p>Deterministic viewer scaffold.</p></body></html>",
            encoding="utf-8",
        )
        viewer_manifest_path.write_text(
            json.dumps(
                {
                    "index_path": str(viewer_index_path),
                    "assets": [str(viewer_index_path)],
                    "scalars": ["pressure_coefficient", "velocity_magnitude"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return {
            "metrics": {"lift_coefficient": 0.0, "drag_coefficient": 0.0},
            "warnings": ["Deterministic scaffold output. Replace with real CFD pipeline."],
            "report_path": str(report_path),
            "summary_path": str(summary_path),
            "viewer_index_path": str(viewer_index_path),
            "viewer_manifest_path": str(viewer_manifest_path),
        }


class DefaultArtifactBuilder:
    def package(self, job_dir: Path, postprocess: dict[str, Any]) -> dict[str, Any]:
        artifacts = [
            {
                "kind": "report",
                "path": postprocess["report_path"],
                "size_bytes": Path(postprocess["report_path"]).stat().st_size,
            },
            {
                "kind": "summary",
                "path": postprocess["summary_path"],
                "size_bytes": Path(postprocess["summary_path"]).stat().st_size,
            },
            {
                "kind": "viewer",
                "path": postprocess["viewer_index_path"],
                "size_bytes": Path(postprocess["viewer_index_path"]).stat().st_size,
            },
        ]
        return {"artifacts": artifacts}
