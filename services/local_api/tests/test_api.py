from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "job_runner"))

from fastapi.testclient import TestClient

from aero_agent_api.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_connection_and_list() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/connections",
        json={"mode": "openai_api", "label": "OpenAI", "data_policy": "summary_first"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "openai_api"

    list_response = client.get("/api/v1/connections")
    assert list_response.status_code == 200
    assert list_response.json()


def test_connection_status_route() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/connections/status", params={"mode": "codex_oauth"})
    assert response.status_code == 200
    assert response.json()["mode"] == "codex_oauth"


def test_preflight_route() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/jobs/preflight",
        data={
            "connection_mode": "openai_api",
            "unit": "m",
            "geometry_kind": "general_3d",
            "solver_preference": "auto",
            "fidelity": "balanced",
            "aoa": "4.0",
            "sideslip": "0.0",
            "velocity": "60.0",
        },
        files={"geometry_file": ("sample.stl", b"solid sample\nendsolid sample\n", "application/sla")},
    )
    assert response.status_code == 200
    assert response.json()["selectedSolver"] in {"su2", "openfoam", "vspaero"}


def test_job_lifecycle_to_completion() -> None:
    client = TestClient(app)
    payload = {
        "connection_mode": "openai_api",
        "unit": "m",
        "geometry_kind": "general_3d",
        "solver_preference": "auto",
        "fidelity": "balanced",
        "aoa": "4.0",
        "sideslip": "0.0",
        "velocity": "60.0",
        "mach": "0.18",
    }
    geometry = {"geometry_file": ("sample.stl", b"solid sample\nendsolid sample\n", "application/sla")}

    create = client.post("/api/v1/jobs", data=payload, files=geometry)
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
    assert final_state["artifacts"]

    history = client.get(f"/api/v1/jobs/{job['id']}/history")
    assert history.status_code == 200
    event_types = [item["event_type"] for item in history.json()]
    assert "approval.required" in event_types
    assert "job.completed" in event_types
