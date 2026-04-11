"""
Ollama provider client (local).
"""
from __future__ import annotations

from typing import Any

import httpx

from app.ai.models.registry import ModelResponse, register_provider


DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3"


@register_provider("ollama")
class OllamaClient:
    def __init__(self, host: str | None = None, model: str | None = None):
        self.host = host or DEFAULT_OLLAMA_HOST
        self.model = model or DEFAULT_OLLAMA_MODEL

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.host}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return ModelResponse(
            content=data["message"]["content"],
            model=data.get("model", model or self.model),
            usage={
                "done_reason": data.get("done_reason"),
                "eval_count": data.get("eval_count"),
                "prompt_eval_count": data.get("prompt_eval_count"),
            },
            finish_reason="stop" if data.get("done") else None,
            provider="ollama",
        )

    async def get_version(self) -> dict:
        """Get Ollama version info."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.host}/api/version")
            response.raise_for_status()
            return response.json()

    async def list_models(self) -> list[dict]:
        """List all available models on this Ollama instance."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.host}/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])

    async def show_model(self, model_name: str) -> dict:
        """Get details about a specific model."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.host}/api/show",
                json={"name": model_name},
            )
            response.raise_for_status()
            return response.json()

    async def discover(self) -> dict:
        """Probe this Ollama instance and return normalized model capability data."""
        errors: list[str] = []
        models: list[dict] = []

        try:
            version_data = await self.get_version()
            version = version_data.get("version")
        except Exception as exc:
            errors.append(f"Failed to get version: {exc}")
            version = None

        try:
            raw_models = await self.list_models()
        except Exception as exc:
            errors.append(f"Failed to list models: {exc}")
            raw_models = []

        for model_data in raw_models:
            model_name = model_data.get("name", "")
            is_cloud = bool(model_data.get("remote_host"))
            source = "cloud" if is_cloud else "local"

            try:
                show_data = await self.show_model(model_name)
            except Exception as exc:
                errors.append(f"Failed to show model {model_name}: {exc}")
                show_data = {}

            raw_capabilities = show_data.get("capabilities", [])
            tool_calling_supported = "tools" in raw_capabilities

            # Normalize cloud model capabilities
            app_not_recommended_for = []
            if is_cloud:
                app_not_recommended_for.append("strictly local-only execution")
                if not tool_calling_supported:
                    tool_calling_supported = False

            models.append({
                "name": model_name,
                "source": source,
                "details": model_data.get("details", {}),
                "raw_capabilities": raw_capabilities,
                "tool_calling_supported_by_model": tool_calling_supported,
                "app_not_recommended_for": app_not_recommended_for,
            })

        return {
            "host": self.host,
            "reachable": True,
            "version": version,
            "models": models,
            "errors": errors,
        }


def get_default_client() -> OllamaClient:
    return OllamaClient()


__all__ = ["OllamaClient", "DEFAULT_OLLAMA_HOST", "DEFAULT_OLLAMA_MODEL", "get_default_client"]
