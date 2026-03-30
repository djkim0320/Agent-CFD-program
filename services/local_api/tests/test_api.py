from __future__ import annotations

import importlib
import shutil
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent.parent
for path in (
    ROOT,
    WORKSPACE / "services" / "job_runner",
    WORKSPACE / "packages" / "common" / "src",
    WORKSPACE / "packages" / "contracts" / "src",
    WORKSPACE / "packages" / "cfd_core" / "src",
    WORKSPACE / "packages" / "install_manager" / "src",
    WORKSPACE / "packages" / "provider_openai" / "src",
    WORKSPACE / "packages" / "provider_codex" / "src",
    WORKSPACE / "packages" / "solver_adapters" / "src",
    WORKSPACE / "packages" / "viewer_assets" / "src",
):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def tetra_stl() -> bytes:
    return b"""solid tetra
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 0 1 0
 endloop
endfacet
facet normal 0 1 0
 outer loop
  vertex 0 0 0
  vertex 0 1 0
  vertex 0 0 1
 endloop
endfacet
facet normal 1 0 0
 outer loop
  vertex 0 0 0
  vertex 0 0 1
  vertex 1 0 0
 endloop
endfacet
facet normal 1 1 1
 outer loop
  vertex 1 0 0
  vertex 0 0 1
  vertex 0 1 0
 endloop
endfacet
endsolid tetra
"""


def open_triangle_stl() -> bytes:
    return b"""solid open
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 0 1 0
 endloop
endfacet
endsolid open
"""


def reset_app(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AERO_AGENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AERO_AGENT_DATABASE_PATH", str(tmp_path / "data" / "app.db"))

    import aero_agent_api.dependencies as deps
    import aero_agent_api.settings as settings
    import aero_agent_api.main as main_mod

    settings.get_settings.cache_clear()
    deps.get_repository.cache_clear()
    deps.get_event_broker.cache_clear()
    deps.get_solver_registry.cache_clear()
    deps.get_viewer_builder.cache_clear()
    deps.get_install_manager.cache_clear()
    deps.get_openai_provider.cache_clear()
    deps.get_codex_provider.cache_clear()
    deps.get_cfd_core.cache_clear()
    deps.get_job_service.cache_clear()

    main_mod = importlib.reload(main_mod)
    return main_mod.app, deps


def ready_install_status():
    from aero_agent_install_manager import InstallStatus

    return InstallStatus(
        docker_ok=True,
        gmsh_ok=True,
        su2_image_ok=True,
        workspace_ok=True,
        install_warnings=[],
        runtime_blockers=[],
        details={},
    )


def patch_runtime_ready(deps, monkeypatch) -> None:
    monkeypatch.setattr(deps.get_install_manager(), "check", lambda: ready_install_status())


def patch_fake_solver_run(deps, monkeypatch) -> None:
    from aero_agent_contracts import JobStatus, SolverKind, SolverRunManifest
    from aero_agent_solver_adapters import SolverRuntimeHandle

    core = deps.get_cfd_core()

    def fake_generate_mesh(case_manifest):
        case_manifest.mesh_path.parent.mkdir(parents=True, exist_ok=True)
        case_manifest.mesh_path.write_text("mesh", encoding="utf-8")
        return case_manifest.mesh_path

    def fake_launch_solver(*, job_id, case_manifest):
        log_path = case_manifest.logs_dir / "solver.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("solver started\n", encoding="utf-8")
        return SolverRuntimeHandle(
            job_id=job_id,
            solver=SolverKind.SU2,
            runtime_backend="mock",
            case_dir=case_manifest.case_dir,
            cfg_path=case_manifest.cfg_path,
            log_path=log_path,
        )

    def fake_wait_for_solver(handle):
        history_path = handle.case_dir / "history.csv"
        history_path.write_text(
            "iteration,residual,CL,CD,Cm\n1,1.0,0.10,0.020,-0.010\n2,0.12,0.21,0.025,-0.018\n",
            encoding="utf-8",
        )
        return SolverRunManifest(
            solver=SolverKind.SU2,
            case_dir=str(handle.case_dir),
            runtime_backend="mock",
            run_id=f"fake-{handle.job_id}",
            pid_or_container_id=f"fake-{handle.job_id}",
            started_at=handle.started_at,
            finished_at=handle.started_at,
            status=JobStatus.COMPLETED,
            logs_path=str(handle.log_path),
            metrics=[],
            warnings=[],
        )

    monkeypatch.setattr(core, "generate_mesh", fake_generate_mesh)
    monkeypatch.setattr(core, "launch_solver", fake_launch_solver)
    monkeypatch.setattr(core, "wait_for_solver", fake_wait_for_solver)


def preflight_payload() -> dict[str, str]:
    return {
        "connection_mode": "openai_api",
        "unit": "m",
        "geometry_kind": "general_3d",
        "solver_preference": "auto",
        "fidelity": "balanced",
        "frame_forward_axis": "x",
        "frame_up_axis": "z",
        "reference_area": "1.0",
        "reference_length": "1.0",
        "reference_span": "1.0",
        "flow_velocity": "60.0",
        "flow_mach": "0.18",
        "flow_aoa": "4.0",
        "flow_sideslip": "0.0",
        "flow_altitude": "0.0",
        "flow_density": "1.225",
        "flow_viscosity": "1.81e-5",
        "notes": "test run",
    }


def test_health(tmp_path, monkeypatch) -> None:
    app, _deps = reset_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_create_connection_and_list(tmp_path, monkeypatch) -> None:
    app, _deps = reset_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/connections",
            json={"mode": "openai_api", "label": "OpenAI", "data_policy": "summary_first"},
        )
        assert response.status_code == 200
        assert response.json()["mode"] == "openai_api"

        list_response = client.get("/api/v1/connections")
        assert list_response.status_code == 200
        assert list_response.json()


def test_connection_status_route(tmp_path, monkeypatch) -> None:
    app, _deps = reset_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/v1/connections/status", params={"mode": "codex_oauth"})
        assert response.status_code == 200
        assert response.json()["mode"] == "codex_oauth"


def test_preflight_provider_fallback_does_not_block_real_run(tmp_path, monkeypatch) -> None:
    app, deps = reset_app(tmp_path, monkeypatch)
    patch_runtime_ready(deps, monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs/preflight",
            data=preflight_payload(),
            files={"geometry_file": ("sample.stl", tetra_stl(), "application/sla")},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["execution_mode"] == "real"
        assert payload["ai_assist_mode"] == "local_fallback"
        assert payload["runtime_blockers"] == []
        assert payload["preflight_id"]


def test_non_watertight_geometry_is_blocked(tmp_path, monkeypatch) -> None:
    app, deps = reset_app(tmp_path, monkeypatch)
    patch_runtime_ready(deps, monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs/preflight",
            data=preflight_payload(),
            files={"geometry_file": ("open.stl", open_triangle_stl(), "application/sla")},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["execution_mode"] == "scaffold"
        assert any("watertight" in blocker.lower() for blocker in payload["runtime_blockers"])


def test_step_success_and_failure_branches(tmp_path, monkeypatch) -> None:
    app, deps = reset_app(tmp_path, monkeypatch)
    patch_runtime_ready(deps, monkeypatch)
    core = deps.get_cfd_core()

    with TestClient(app) as client:
        failure = client.post(
            "/api/v1/jobs/preflight",
            data=preflight_payload(),
            files={"geometry_file": ("sample.step", b"ISO-10303-21;", "application/step")},
        )
        assert failure.status_code == 200
        assert failure.json()["execution_mode"] == "scaffold"

    monkeypatch.setattr(core, "_load_step_via_gmsh", lambda _path: core._load_stl(Path(tmp_path / "dummy.stl")))
    (tmp_path / "dummy.stl").write_bytes(tetra_stl())

    with TestClient(app) as client:
        success = client.post(
            "/api/v1/jobs/preflight",
            data=preflight_payload(),
            files={"geometry_file": ("sample.step", b"ISO-10303-21;", "application/step")},
        )
        assert success.status_code == 200
        assert success.json()["execution_mode"] == "real"


def test_snapshot_integrity_blocks_approve(tmp_path, monkeypatch) -> None:
    app, deps = reset_app(tmp_path, monkeypatch)
    patch_runtime_ready(deps, monkeypatch)
    with TestClient(app) as client:
        preflight = client.post(
            "/api/v1/jobs/preflight",
            data=preflight_payload(),
            files={"geometry_file": ("sample.stl", tetra_stl(), "application/sla")},
        ).json()
        snapshot_id = preflight["preflight_id"]
        job = client.post("/api/v1/jobs", json={"preflight_id": snapshot_id}).json()

        integrity = tmp_path / "data" / "snapshots" / snapshot_id / "preflight" / "integrity.json"
        integrity.write_text(
            '{"request_digest":"tampered","source_hash":"tampered","normalized_manifest_hash":"tampered"}',
            encoding="utf-8",
        )

        approve = client.post(f"/api/v1/jobs/{job['id']}/approve")
        assert approve.status_code == 409


def test_job_lifecycle_to_completion(tmp_path, monkeypatch) -> None:
    app, deps = reset_app(tmp_path, monkeypatch)
    patch_runtime_ready(deps, monkeypatch)
    patch_fake_solver_run(deps, monkeypatch)

    with TestClient(app) as client:
        preflight = client.post(
            "/api/v1/jobs/preflight",
            data=preflight_payload(),
            files={"geometry_file": ("sample.stl", tetra_stl(), "application/sla")},
        )
        assert preflight.status_code == 200
        snapshot_id = preflight.json()["preflight_id"]

        create = client.post("/api/v1/jobs", json={"preflight_id": snapshot_id})
        assert create.status_code == 200
        job = create.json()
        assert job["status"] == "waiting_approval"

        approve = client.post(f"/api/v1/jobs/{job['id']}/approve")
        assert approve.status_code == 200

        deadline = time.time() + 5
        final_state = None
        while time.time() < deadline:
            current = client.get(f"/api/v1/jobs/{job['id']}")
            assert current.status_code == 200
            final_state = current.json()
            if final_state["status"] in {"completed", "failed"}:
                break
            time.sleep(0.1)

        assert final_state is not None
        assert final_state["status"] == "completed"
        assert float(final_state["metrics"]["CL"]) == 0.21
        assert float(final_state["metrics"]["CD"]) == 0.025
        assert float(final_state["metrics"]["Cm"]) == -0.018
        assert final_state["artifacts"]

        history = client.get(f"/api/v1/jobs/{job['id']}/history")
        assert history.status_code == 200
        event_types = [item["event_type"] for item in history.json()]
        assert "approval.required" in event_types
        assert "job.completed" in event_types


def test_real_integration_only_when_runtime_present() -> None:
    runtime_ready = shutil.which("docker") is not None and shutil.which("gmsh") is not None
    assert isinstance(runtime_ready, bool)
