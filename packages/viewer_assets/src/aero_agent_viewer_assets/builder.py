from __future__ import annotations

import html
import json
from pathlib import Path

from aero_agent_common import json_dumps
from aero_agent_contracts import ResultField, ViewerManifest


class ViewerAssetBuilder:
    def build(self, job_id: str, fields: list[ResultField], *, output_dir: Path | None = None) -> ViewerManifest:
        viewer_dir = output_dir or (Path.cwd() / "data" / "jobs" / job_id / "viewer")
        viewer_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = viewer_dir / "viewer_manifest.json"
        index_path = viewer_dir / "index.html"
        field_names = [field.name for field in fields]
        field_list_html = "".join(f"<li>{html.escape(name)}</li>" for name in field_names) or "<li>None</li>"
        manifest_payload = {
            "kind": "artifact_shell",
            "job_id": job_id,
            "scalars": field_names,
            "note": "This viewer is an artifact shell. Full field rendering is deferred to a later stage.",
        }
        index_path.write_text(
            "\n".join(
                [
                    "<!doctype html>",
                    "<html lang=\"en\">",
                    "<head>",
                    "  <meta charset=\"utf-8\" />",
                    "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />",
                    "  <title>Artifact Shell</title>",
                    "  <style>",
                    "    :root { color-scheme: light; }",
                    "    body { font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #f6f7fb; color: #1f2937; }",
                    "    .shell { max-width: 960px; margin: 0 auto; background: white; border: 1px solid #d6dbe6; border-radius: 16px; padding: 24px; box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08); }",
                    "    .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; background: #eef2ff; color: #3730a3; font-size: 12px; font-weight: 600; letter-spacing: .02em; }",
                    "    .muted { color: #6b7280; }",
                    "    ul { padding-left: 20px; }",
                    "    code, pre { background: #f3f4f6; border-radius: 8px; }",
                    "    pre { padding: 16px; overflow: auto; }",
                    "  </style>",
                    "</head>",
                    "<body>",
                    "  <div class=\"shell\">",
                    "    <div class=\"badge\">Artifact Shell</div>",
                    f"    <h1>Job {html.escape(job_id)} results</h1>",
                    "    <p class=\"muted\">This page intentionally stops at a trustworthy result shell: report links, summaries, and artifacts are exposed here, but full scalar field rendering is deferred.</p>",
                    "    <h2>Available Scalars</h2>",
                    f"    <ul>{field_list_html}</ul>",
                    "    <h2>Scope</h2>",
                    "    <ul>",
                    "      <li>Residual history and coefficient summaries are surfaced elsewhere in the report.</li>",
                    "      <li>Full volume/field rendering is not claimed in this stage.</li>",
                    "      <li>This bundle is meant for artifact navigation and preview only.</li>",
                    "    </ul>",
                    "    <h2>Viewer Manifest</h2>",
                    f"    <pre id=\"manifest\"></pre>",
                    "  </div>",
                    "  <script>",
                    f"    const manifest = {json.dumps(manifest_payload, ensure_ascii=False)};",
                    "    document.getElementById('manifest').textContent = JSON.stringify(manifest, null, 2);",
                    "  </script>",
                    "</body>",
                    "</html>",
                ]
            ),
            encoding="utf-8",
        )
        manifest = ViewerManifest(
            bundle_dir=str(viewer_dir),
            index_path=str(index_path),
            assets=[str(manifest_path), str(index_path)],
            scalars=field_names,
            note="Artifact shell viewer bundle. Full field rendering is deferred.",
        )
        manifest_path.write_text(json_dumps(manifest.model_dump(mode="json")), encoding="utf-8")
        return manifest
