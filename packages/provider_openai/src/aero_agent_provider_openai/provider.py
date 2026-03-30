from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from typing import Any

import httpx

from aero_agent_contracts import ConnectionMode, ProviderBackend, ProviderCapabilities, ProviderStatus


@dataclass(slots=True)
class StructuredPreflightResult:
    provider: str
    backend: str
    ai_assist_mode: str
    ok: bool
    agent_type: str
    payload: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    raw_text: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    error_reason: str | None = None


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
            warnings=[] if has_key else ["OpenAI API key not configured; AI review is unavailable."],
            details={"model": self.model, "api_base": self.api_base},
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            backend=ProviderBackend.OPENAI,
            supports_streaming=True,
            supports_subagents=True,
            supports_noninteractive=False,
            supports_mcp=False,
            notes=[
                "Structured JSON preflight helper is available.",
                "Provider unavailability is surfaced as explicit AI review unavailability.",
            ],
        )

    def run_subagent(self, agent_type: str, prompt_pack: str, input_json: dict[str, Any]) -> dict[str, Any]:
        result = self.run_structured_preflight(agent_type, input_json, prompt_pack=prompt_pack)
        return result.__dict__

    def run_structured_preflight(
        self,
        agent_type: str,
        input_json: dict[str, Any],
        *,
        prompt_pack: str | None = None,
        timeout_s: float = 30.0,
    ) -> StructuredPreflightResult:
        if not self.healthcheck().provider_ready:
            return self._unavailable_result(agent_type, "OPENAI_API_KEY not configured.")

        schema = self._schema_for(agent_type)
        system_prompt = prompt_pack or self._system_prompt_for(agent_type)
        body = {
            "model": self.model,
            "temperature": 0,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(input_json, ensure_ascii=False, sort_keys=True, default=str),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": f"{agent_type.replace('.', '_')}_preflight",
                    "schema": schema,
                    "strict": True,
                }
            },
        }

        try:
            with httpx.Client(base_url=self.api_base, timeout=timeout_s) as client:
                response = client.post(
                    "/responses",
                    headers={"Authorization": f"Bearer {os.environ[self.api_key_env]}"},
                    json=body,
                )
            response.raise_for_status()
            raw = response.json()
            text = self._extract_text(raw)
            parsed = self._safe_json_loads(text) if text else None
            if not isinstance(parsed, dict):
                return self._failed_result(agent_type, "OpenAI response did not contain valid JSON.", raw_text=text)
            return StructuredPreflightResult(
                provider="openai",
                backend="openai",
                ai_assist_mode="remote",
                ok=True,
                agent_type=agent_type,
                payload=self._normalize_payload(agent_type, input_json, parsed),
                warnings=[],
                raw_text=text,
                usage=self._usage_from_response(raw),
            )
        except Exception as exc:  # pragma: no cover - network/runtime guard
            return self._failed_result(agent_type, str(exc))

    def _unavailable_result(
        self,
        agent_type: str,
        reason: str,
    ) -> StructuredPreflightResult:
        return StructuredPreflightResult(
            provider="openai",
            backend="openai",
            ai_assist_mode="unavailable",
            ok=False,
            agent_type=agent_type,
            warnings=[f"OpenAI structured preflight unavailable: {reason}"],
            error_reason=reason,
        )

    def _failed_result(
        self,
        agent_type: str,
        reason: str,
        *,
        raw_text: str | None = None,
    ) -> StructuredPreflightResult:
        return StructuredPreflightResult(
            provider="openai",
            backend="openai",
            ai_assist_mode="failed",
            ok=False,
            agent_type=agent_type,
            warnings=[f"OpenAI structured preflight failed: {reason}"],
            raw_text=raw_text,
            error_reason=reason,
        )

    def _schema_for(self, agent_type: str) -> dict[str, Any]:
        if agent_type == "geometry-triage":
            return {
                "type": "object",
                "properties": {
                    "geometry_kind": {"type": "string", "enum": ["general_3d", "aircraft_vsp"]},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "missing_inputs": {"type": "array", "items": {"type": "string"}},
                    "repairability": {"type": "string", "enum": ["repairable", "blocked"]},
                    "notes": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["geometry_kind", "risks", "missing_inputs", "repairability", "notes"],
                "additionalProperties": True,
            }
        if agent_type == "solver-planner":
            return {
                "type": "object",
                "properties": {
                    "recommended_solver": {"type": "string"},
                    "rationale": {"type": "string"},
                    "execution_mode": {"type": "string", "enum": ["real", "scaffold"]},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "deferred_scope": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "recommended_solver",
                    "rationale",
                    "execution_mode",
                    "warnings",
                    "deferred_scope",
                ],
                "additionalProperties": True,
            }
        return {
            "type": "object",
            "properties": {
                "allowed": {"type": "boolean"},
                "ai_warnings": {"type": "array", "items": {"type": "string"}},
                "policy_warnings": {"type": "array", "items": {"type": "string"}},
                "export_scope": {"type": "string"},
                "notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["allowed", "ai_warnings", "policy_warnings", "export_scope", "notes"],
            "additionalProperties": True,
        }

    def _system_prompt_for(self, agent_type: str) -> str:
        if agent_type == "geometry-triage":
            return "Return concise geometry triage JSON only."
        if agent_type == "solver-planner":
            return "Return solver planning JSON only."
        return "Return policy review JSON only."

    def _normalize_payload(
        self,
        agent_type: str,
        input_json: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(payload)
        normalized.setdefault("agent_type", agent_type)
        normalized.setdefault("input_digest", self._input_digest(input_json))
        normalized.setdefault("provider", "openai")
        return normalized

    def _usage_from_response(self, response_json: dict[str, Any]) -> dict[str, Any]:
        usage = response_json.get("usage")
        if isinstance(usage, dict):
            return usage
        return {}

    def _extract_text(self, response_json: dict[str, Any]) -> str | None:
        if isinstance(response_json.get("output_text"), str):
            return response_json["output_text"]

        output = response_json.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for piece in content:
                        if isinstance(piece, dict):
                            text = piece.get("text")
                            if isinstance(text, str):
                                chunks.append(text)
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
            if chunks:
                return "\n".join(chunks)

        return None

    def _safe_json_loads(self, text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _input_digest(self, input_json: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(input_json, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
