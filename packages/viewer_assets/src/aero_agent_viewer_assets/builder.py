from __future__ import annotations

from pathlib import Path

from aero_agent_common import create_app_paths, json_dumps
from aero_agent_contracts import ResultField, ViewerManifest


class ViewerAssetBuilder:
    def build(self, job_id: str, fields: list[ResultField]) -> ViewerManifest:
        app_paths = create_app_paths(Path.cwd())
        viewer_dir = app_paths.jobs / job_id / "viewer"
        viewer_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = viewer_dir / "viewer_manifest.json"
        index_path = viewer_dir / "index.html"
        index_path.write_text(
            "<html><body><h1>Viewer Placeholder</h1><p>vtk.js bundle placeholder.</p></body></html>",
            encoding="utf-8",
        )
        manifest = ViewerManifest(
            bundle_dir=str(viewer_dir),
            index_path=str(index_path),
            assets=[str(manifest_path), str(index_path)],
            scalars=[field.name for field in fields],
            note="Scaffold viewer asset bundle.",
        )
        manifest_path.write_text(json_dumps(manifest.model_dump(mode="json")), encoding="utf-8")
        return manifest
