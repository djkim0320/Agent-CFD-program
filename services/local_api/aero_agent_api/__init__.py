"""Local API package for the aerodynamic analysis app."""

from __future__ import annotations

import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _SERVICE_ROOT.parent
_JOB_RUNNER_ROOT = _SERVICES_ROOT / "job_runner"

for candidate in (_SERVICE_ROOT, _JOB_RUNNER_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)
