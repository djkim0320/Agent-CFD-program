from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil

from aero_agent_solver_adapters import SolverAdapterRegistry


@dataclass(slots=True)
class InstallStatus:
    docker_ok: bool
    gmsh_ok: bool
    su2_image_ok: bool
    workspace_ok: bool
    install_warnings: list[str]
    runtime_blockers: list[str]
    details: dict[str, object]


@dataclass(slots=True)
class ProviderReadiness:
    openai_ready: bool
    codex_ready: bool
    wsl_ok: bool
    provider_ready: bool
    provider_warnings: list[str]
    details: dict[str, object]


class InstallManager:
    def __init__(self, solver_registry: SolverAdapterRegistry | None = None) -> None:
        self.solver_registry = solver_registry or SolverAdapterRegistry()

    def check(self) -> InstallStatus:
        probe = self.solver_registry.probe_runtime()
        install_warnings = list(probe.issues)
        runtime_blockers = []
        if not probe.docker_ok:
            runtime_blockers.append("Docker not detected.")
        if not probe.gmsh_ok:
            runtime_blockers.append("gmsh not detected.")
        if not probe.su2_image_ok:
            runtime_blockers.append("Pinned SU2 Docker image not detected.")
        if not probe.workspace_ok:
            runtime_blockers.append("Workspace is not writable.")
        return InstallStatus(
            docker_ok=probe.docker_ok,
            gmsh_ok=probe.gmsh_ok,
            su2_image_ok=probe.su2_image_ok,
            workspace_ok=probe.workspace_ok,
            install_warnings=install_warnings,
            runtime_blockers=runtime_blockers,
            details={
                "workspace_root": str(Path(os.getenv("AERO_AGENT_WORKSPACE_ROOT", Path.cwd()))),
            },
        )

    def provider_readiness(self) -> ProviderReadiness:
        wsl_ok = bool(os.getenv("WSL_DISTRO_NAME")) or shutil.which("wsl") is not None
        openai_ready = bool(os.getenv("OPENAI_API_KEY"))
        codex_ready = shutil.which("codex") is not None or bool(os.getenv("AERO_AGENT_CODEX_BACKEND"))
        provider_warnings = []
        if not openai_ready:
            provider_warnings.append("OpenAI API key not configured.")
        if not codex_ready:
            provider_warnings.append("Codex CLI/bridge not detected.")
        if not wsl_ok:
            provider_warnings.append("WSL not detected; codex_oauth remains beta and WSL-preferred on Windows.")
        return ProviderReadiness(
            openai_ready=openai_ready,
            codex_ready=codex_ready,
            wsl_ok=wsl_ok,
            provider_ready=openai_ready or codex_ready,
            provider_warnings=provider_warnings,
            details={
                "openai_api_key_present": openai_ready,
                "codex_backend_hint": os.getenv("AERO_AGENT_CODEX_BACKEND"),
                "wsl_distro": os.getenv("WSL_DISTRO_NAME"),
            },
        )
