from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AppPaths:
    root: Path
    data: Path
    jobs: Path
    artifacts: Path
    logs: Path


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_app_paths(root: Path) -> AppPaths:
    data = ensure_directory(root / "data")
    jobs = ensure_directory(data / "jobs")
    artifacts = ensure_directory(data / "artifacts")
    logs = ensure_directory(data / "logs")
    return AppPaths(root=root, data=data, jobs=jobs, artifacts=artifacts, logs=logs)


def job_root_dir(app_paths: AppPaths, job_id: str) -> Path:
    return ensure_directory(app_paths.jobs / job_id)


def job_artifact_dir(app_paths: AppPaths, job_id: str) -> Path:
    return ensure_directory(job_root_dir(app_paths, job_id) / "artifacts")
