from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import hashlib
import os
import shutil
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
class ReadonlyPreflightResult:
    provider: str
    backend: str
    ai_assist_mode: str
    ok: bool
    agent_type: str
    payload: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None
    error_reason: str | None = None


@dataclass(slots=True)
class CodexProviderAdapter:
    """
    Backend precedence:
    1. SDK
    2. app-server experimental
    3. noninteractive detection
    4. MCP detection
    5. mock/unavailable
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
        provider_ready = False
        return ProviderStatus(
            connected=backend != CodexBackendChoice.MOCK,
            mode=ConnectionMode.CODEX_OAUTH,
            backend=self._to_contract_backend(backend),
            provider_ready=provider_ready,
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
                "Read-only preflight bridge only.",
                "This build does not expose a production Codex advisory bridge.",
                "Windows codex_oauth remains beta and WSL-preferred by product policy.",
            ],
        )

    def run_subagent(self, agent_type: str, prompt_pack: str, input_json: dict[str, Any]) -> dict[str, Any]:
        return self.run_readonly_preflight(agent_type, input_json, prompt_pack=prompt_pack).__dict__

    def run_readonly_preflight(
        self,
        agent_type: str,
        input_json: dict[str, Any],
        *,
        prompt_pack: str | None = None,
    ) -> ReadonlyPreflightResult:
        backend = self.detect_backend()
        if backend == CodexBackendChoice.MOCK:
            return self._unavailable_result(agent_type, "No Codex runtime detected.")

        return self._disabled_result(agent_type, backend)

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
            warnings.append("Codex noninteractive backend is detected, but the read-only bridge is disabled.")
        if backend == CodexBackendChoice.MCP:
            warnings.append("Codex MCP backend is detected, but the read-only bridge is disabled.")
        if backend == CodexBackendChoice.MOCK:
            warnings.append("No Codex runtime detected; AI review is unavailable.")
        return warnings

    def _unavailable_result(
        self,
        agent_type: str,
        reason: str,
    ) -> ReadonlyPreflightResult:
        return ReadonlyPreflightResult(
            provider="codex",
            backend="mock",
            ai_assist_mode="unavailable",
            ok=False,
            agent_type=agent_type,
            warnings=[f"Codex read-only bridge unavailable: {reason}"],
            error_reason=reason,
        )

    def _disabled_result(
        self,
        agent_type: str,
        *,
        backend: CodexBackendChoice,
    ) -> ReadonlyPreflightResult:
        reason = "Codex read-only advisory is disabled in this production build."
        return ReadonlyPreflightResult(
            provider="codex",
            backend=backend.value,
            ai_assist_mode="disabled",
            ok=False,
            agent_type=agent_type,
            warnings=self._warnings(backend) + [reason],
            error_reason=reason,
        )
