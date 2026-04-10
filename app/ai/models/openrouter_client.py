"""
OpenRouter provider client.
"""
from __future__ import annotations

import os
import httpx
from typing import Any

from app.ai.models.registry import ModelResponse, register_provider


OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@register_provider("openrouter")
class OpenRouterClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> ModelResponse:
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")
    
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": model or "openai/gpt-4o",
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        return ModelResponse(
            content=choice["message"]["content"],
            model=data.get("model", model or "openai/gpt-4o"),
            usage=data.get("usage"),
            finish_reason=choice.get("finish_reason"),
        )


def get_default_client() -> OpenRouterClient:
    return OpenRouterClient()


__all__ = ["OpenRouterClient", "get_default_client"]
