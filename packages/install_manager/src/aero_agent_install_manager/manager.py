from __future__ import annotations

from dataclasses import dataclass
import os
import shutil

from aero_agent_solver_adapters import SolverAdapterRegistry


@dataclass(slots=True)
class InstallStatus:
    docker_ok: bool
    su2_ok: bool
    openfoam_ok: bool
    vspaero_ok: bool
    codex_ok: bool
    wsl_ok: bool
    issues: list[str]


class InstallManager:
    def __init__(self, solver_registry: SolverAdapterRegistry | None = None) -> None:
        self.solver_registry = solver_registry or SolverAdapterRegistry()

    def check(self) -> InstallStatus:
        probe = self.solver_registry.probe()
        wsl_ok = bool(os.getenv("WSL_DISTRO_NAME")) or shutil.which("wsl") is not None
        codex_ok = shutil.which("codex") is not None
        issues = list(probe.issues)
        if not codex_ok:
            issues.append("Codex CLI/bridge not detected.")
        if not wsl_ok:
            issues.append("WSL not detected; codex_oauth remains beta and WSL-preferred on Windows.")
        return InstallStatus(
            docker_ok=probe.docker_ok,
            su2_ok=probe.su2_ok,
            openfoam_ok=probe.openfoam_ok,
            vspaero_ok=probe.vspaero_ok,
            codex_ok=codex_ok,
            wsl_ok=wsl_ok,
            issues=issues,
        )
