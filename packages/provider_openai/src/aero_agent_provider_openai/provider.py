from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from aero_agent_contracts import ConnectionMode, ProviderBackend, ProviderCapabilities, ProviderStatus


@dataclass(slots=True)
class OpenAIProviderAdapter:
    model: str = "gpt-5.4"
    api_base: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"

    def healthcheck(self) -> ProviderStatus:
        has_key = bool(os.getenv(self.api_key_env))
        return ProviderStatus(
            connected=has_key,
            mode=ConnectionMode.OPENAI_API,
            backend=ProviderBackend.OPENAI,
            provider_ready=has_key,
            warnings=[] if has_key else ["OpenAI API key not configured; running in local scaffold mode."],
            details={"model": self.model, "api_base": self.api_base},
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            backend=ProviderBackend.OPENAI,
            supports_streaming=True,
            supports_subagents=True,
            supports_noninteractive=False,
            supports_mcp=False,
            notes=["Mock adapter ready for future Responses API integration."],
        )

    def run_subagent(self, agent_type: str, prompt_pack: str, input_json: dict[str, Any]) -> dict[str, Any]:
        return {
            "provider": "openai",
            "model": self.model,
            "agent_type": agent_type,
            "summary": f"Mock OpenAI response for {agent_type}.",
            "input_keys": sorted(input_json.keys()),
            "prompt_pack": prompt_pack,
        }
