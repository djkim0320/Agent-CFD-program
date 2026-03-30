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
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None
    fallback_reason: str | None = None


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
                "Read-only preflight bridge only.",
                "SDK is the default backend.",
                "app-server is experimental.",
                "noninteractive and MCP are fallback routes.",
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
            return self._fallback_result(agent_type, input_json, "No Codex runtime detected.")

        payload = self._bridge_payload(agent_type, input_json, prompt_pack=prompt_pack, backend=backend)
        return ReadonlyPreflightResult(
            provider="codex",
            backend=backend.value,
            ai_assist_mode="remote",
            ok=True,
            agent_type=agent_type,
            payload=payload,
            warnings=self._warnings(backend),
        )

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

    def _fallback_result(
        self,
        agent_type: str,
        input_json: dict[str, Any],
        reason: str,
    ) -> ReadonlyPreflightResult:
        payload = self._bridge_payload(agent_type, input_json, backend=CodexBackendChoice.MOCK)
        payload["fallback_reason"] = reason
        return ReadonlyPreflightResult(
            provider="codex",
            backend="mock",
            ai_assist_mode="local_fallback",
            ok=False,
            agent_type=agent_type,
            payload=payload,
            warnings=[f"Codex read-only bridge unavailable: {reason}"],
            fallback_reason=reason,
        )

    def _bridge_payload(
        self,
        agent_type: str,
        input_json: dict[str, Any],
        *,
        backend: CodexBackendChoice,
        prompt_pack: str | None = None,
    ) -> dict[str, Any]:
        input_digest = hashlib.sha256(
            str(sorted((key, self._canonicalize(value)) for key, value in input_json.items())).encode("utf-8")
        ).hexdigest()
        payload = self._deterministic_payload(agent_type, input_json)
        payload.update(
            {
                "provider": "codex",
                "backend": backend.value,
                "bridge_mode": "read_only_preflight",
                "ai_assist_mode": "remote" if backend != CodexBackendChoice.MOCK else "local_fallback",
                "input_digest": input_digest,
                "input_keys": sorted(input_json.keys()),
                "prompt_pack": prompt_pack,
                "beta_note": "Windows codex_oauth support is Beta and WSL-preferred.",
            }
        )
        return payload

    def _deterministic_payload(self, agent_type: str, input_json: dict[str, Any]) -> dict[str, Any]:
        digest = hashlib.sha256(
            repr(sorted((key, self._canonicalize(value)) for key, value in input_json.items())).encode("utf-8")
        ).hexdigest()
        if agent_type == "geometry-triage":
            return {
                "geometry_kind": input_json.get("geometry_kind_hint", "general_3d"),
                "risks": [
                    "Codex bridge is read-only; geometry summary is derived from local manifest.",
                ],
                "missing_inputs": [],
                "repairability": "repairable",
                "notes": [f"input_digest={digest}"],
            }
        if agent_type == "solver-planner":
            return {
                "recommended_solver": input_json.get("solver_preference", "su2"),
                "rationale": "Codex bridge returned a read-only solver plan.",
                "execution_mode": "real",
                "warnings": ["Provider-only signal; runtime readiness still governs execution."],
                "deferred_scope": ["OpenFOAM", ".vsp3", "post-run agents"],
            }
        return {
            "allowed": True,
            "ai_warnings": ["Codex bridge is read-only and advisory only."],
            "policy_warnings": ["Summary-only export recommended."],
            "export_scope": "summary_only",
            "notes": [f"input_digest={digest}"],
        }

    def _canonicalize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._canonicalize(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [self._canonicalize(item) for item in value]
        return value
