"""
Ollama provider client (local).
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator

import httpx

from app.ai.models.registry import ModelResponse, register_provider


DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")


@register_provider("ollama")
class OllamaClient:
    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = str(host or DEFAULT_OLLAMA_HOST).rstrip("/")
        self.model = str(model or DEFAULT_OLLAMA_MODEL).strip()

    def _build_payload(
        self,
        *,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}
        return payload

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        payload = self._build_payload(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()

        return ModelResponse(
            content=str(data.get("message", {}).get("content") or ""),
            model=str(data.get("model") or model or self.model),
            usage=data.get("done_reason"),
            finish_reason="stop" if data.get("done") else None,
        )

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        payload = self._build_payload(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{self.host}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    yield json.loads(line)

    async def get_version(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.host}/api/version")
            response.raise_for_status()
            return response.json()

    async def list_models(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.host}/api/tags")
            response.raise_for_status()
            payload = response.json()
        models = payload.get("models")
        return models if isinstance(models, list) else []

    async def show_model(self, model_name: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.host}/api/show", json={"model": model_name})
            response.raise_for_status()
            return response.json()

    async def discover(self, concurrency: int = 4) -> dict[str, Any]:
        version_payload = await self.get_version()
        models = await self.list_models()
        semaphore = asyncio.Semaphore(max(1, concurrency))
        errors: list[str] = []

        async def _describe(entry: dict[str, Any]) -> dict[str, Any]:
            model_name = str(entry.get("model") or entry.get("name") or "").strip()
            details_payload: dict[str, Any] = {}
            if model_name:
                try:
                    async with semaphore:
                        details_payload = await self.show_model(model_name)
                except Exception as exc:
                    errors.append(f"{model_name}: {exc}")
            return self._normalize_model_entry(entry, details_payload)

        described = await asyncio.gather(*[_describe(entry) for entry in models if isinstance(entry, dict)])
        described.sort(key=lambda item: (item.get("source") != "local", str(item.get("name") or "")))
        return {
            "host": self.host,
            "reachable": True,
            "version": version_payload.get("version"),
            "models": described,
            "errors": errors,
        }

    def _normalize_model_entry(self, entry: dict[str, Any], show_payload: dict[str, Any]) -> dict[str, Any]:
        base_details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
        show_details = show_payload.get("details") if isinstance(show_payload.get("details"), dict) else {}
        details = {**base_details, **show_details}
        capabilities = show_payload.get("capabilities") if isinstance(show_payload.get("capabilities"), list) else []
        source = "cloud" if entry.get("remote_host") else "local"
        recommended_for, not_recommended_for = self._infer_capability_guidance(
            name=str(entry.get("name") or entry.get("model") or ""),
            family=str(details.get("family") or ""),
            capabilities=[str(item) for item in capabilities if str(item).strip()],
            source=source,
        )
        return {
            "name": str(entry.get("name") or entry.get("model") or "").strip(),
            "model": str(entry.get("model") or entry.get("name") or "").strip(),
            "source": source,
            "source_label": "Cloud via Ollama" if source == "cloud" else "Local",
            "family": str(details.get("family") or "").strip(),
            "parameter_size": str(details.get("parameter_size") or "").strip(),
            "quantization_level": str(details.get("quantization_level") or "").strip(),
            "raw_capabilities": [str(item) for item in capabilities if str(item).strip()],
            "tool_calling_supported_by_model": "tools" in capabilities,
            "tool_calling_enabled_in_app": False,
            "app_recommended_for": recommended_for,
            "app_not_recommended_for": not_recommended_for,
            "modified_at": entry.get("modified_at"),
            "size": entry.get("size"),
            "remote_host": entry.get("remote_host"),
        }

    def _infer_capability_guidance(
        self,
        *,
        name: str,
        family: str,
        capabilities: list[str],
        source: str,
    ) -> tuple[list[str], list[str]]:
        lowered_name = name.lower()
        lowered_family = family.lower()
        capability_set = {item.lower() for item in capabilities}
        recommended: list[str] = []
        not_recommended: list[str] = []

        if source == "local":
            recommended.append("live result explanation")
            recommended.append("low-latency streaming replies")
        else:
            not_recommended.append("strictly local-only execution")

        if "completion" in capability_set:
            recommended.append("general analysis and explanation")
        if "thinking" in capability_set:
            recommended.append("deeper local reasoning")
        else:
            not_recommended.append("long multi-step reasoning")
        if "tools" in capability_set:
            recommended.append("tool-aware planning prompts")
        else:
            not_recommended.append("tool calling")
        if "insert" in capability_set or "coder" in lowered_name or "coder" in lowered_family:
            recommended.append("code review and patch drafting")
        else:
            not_recommended.append("large code rewrites")
        if "vision" in capability_set:
            recommended.append("vision prompts")
        if "audio" in capability_set:
            recommended.append("audio prompts")

        return _dedupe_strings(recommended), _dedupe_strings(not_recommended)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def get_default_client() -> OllamaClient:
    return OllamaClient()


__all__ = ["OllamaClient", "get_default_client", "DEFAULT_OLLAMA_HOST", "DEFAULT_OLLAMA_MODEL"]
