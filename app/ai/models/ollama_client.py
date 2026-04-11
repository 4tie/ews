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


def get_default_client() -> OllamaClient:
    return OllamaClient()


__all__ = ["OllamaClient", "DEFAULT_OLLAMA_HOST", "DEFAULT_OLLAMA_MODEL", "get_default_client"]
