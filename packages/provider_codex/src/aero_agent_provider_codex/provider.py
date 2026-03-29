from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Any

from aero_agent_contracts import ConnectionMode, ProviderBackend, ProviderCapabilities, ProviderStatus


class CodexBackendChoice(str, Enum):
    SDK = "sdk"
    APP_SERVER = "app_server"
    NONINTERACTIVE = "noninteractive"
    MCP = "mcp"
    MOCK = "mock"


@dataclass(slots=True)
class CodexProviderAdapter:
    """
    Backend precedence:
    1. SDK
    2. app-server experimental
    3. noninteractive fallback
    4. MCP fallback
    5. mock fallback
    """

    backend_choice: CodexBackendChoice | None = None
    codex_cli: str = "codex"

    def detect_backend(self) -> CodexBackendChoice:
        if self.backend_choice is not None:
            return self.backend_choice
        if importlib.util.find_spec("codex") is not None or os.getenv("AERO_AGENT_CODEX_BACKEND") == "sdk":
            return CodexBackendChoice.SDK
        if os.getenv("AERO_AGENT_CODEX_APP_SERVER_URL"):
            return CodexBackendChoice.APP_SERVER
        if shutil.which(self.codex_cli):
            return CodexBackendChoice.NONINTERACTIVE
        if os.getenv("AERO_AGENT_CODEX_MCP_SERVER"):
            return CodexBackendChoice.MCP
        return CodexBackendChoice.MOCK

    def healthcheck(self) -> ProviderStatus:
        backend = self.detect_backend()
        wsl_preferred = True
        return ProviderStatus(
            connected=backend != CodexBackendChoice.MOCK,
            mode=ConnectionMode.CODEX_OAUTH,
            backend=self._to_contract_backend(backend),
            provider_ready=backend != CodexBackendChoice.MOCK,
            warnings=self._warnings(backend),
            details={"backend_choice": backend.value, "wsl_preferred": wsl_preferred},
        )

    def capabilities(self) -> ProviderCapabilities:
        backend = self.detect_backend()
        return ProviderCapabilities(
            backend=self._to_contract_backend(backend),
            supports_streaming=backend in {CodexBackendChoice.SDK, CodexBackendChoice.APP_SERVER},
            supports_subagents=True,
            supports_noninteractive=True,
            supports_mcp=True,
            notes=[
                "SDK is the default backend.",
                "app-server is experimental.",
                "noninteractive and MCP are fallback routes.",
            ],
        )

    def run_subagent(self, agent_type: str, prompt_pack: str, input_json: dict[str, Any]) -> dict[str, Any]:
        backend = self.detect_backend()
        return {
            "provider": "codex",
            "backend": backend.value,
            "agent_type": agent_type,
            "summary": f"Mock Codex backend ({backend.value}) response for {agent_type}.",
            "input_keys": sorted(input_json.keys()),
            "prompt_pack": prompt_pack,
        }

    def _to_contract_backend(self, backend: CodexBackendChoice) -> ProviderBackend:
        mapping = {
            CodexBackendChoice.SDK: ProviderBackend.CODEX_SDK,
            CodexBackendChoice.APP_SERVER: ProviderBackend.CODEX_APP_SERVER,
            CodexBackendChoice.NONINTERACTIVE: ProviderBackend.CODEX_NONINTERACTIVE,
            CodexBackendChoice.MCP: ProviderBackend.CODEX_MCP,
            CodexBackendChoice.MOCK: ProviderBackend.MOCK,
        }
        return mapping[backend]

    def _warnings(self, backend: CodexBackendChoice) -> list[str]:
        warnings = ["Windows codex_oauth support is Beta and WSL-preferred."]
        if backend == CodexBackendChoice.APP_SERVER:
            warnings.append("Codex app-server backend is experimental.")
        if backend == CodexBackendChoice.NONINTERACTIVE:
            warnings.append("Using codex exec noninteractive fallback backend.")
        if backend == CodexBackendChoice.MCP:
            warnings.append("Using Codex MCP fallback backend.")
        if backend == CodexBackendChoice.MOCK:
            warnings.append("No Codex runtime detected; using mock backend.")
        return warnings
