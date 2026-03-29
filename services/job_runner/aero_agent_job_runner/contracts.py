from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class JobExecutionContext:
    job_id: str
    connection_mode: str
    job_dir: Path
    request: dict[str, Any]
    source_file_path: Path
    source_file_name: str

