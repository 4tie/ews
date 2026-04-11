"""
OpenRouter provider client.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.ai.models.registry import ModelResponse, register_provider


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


@register_provider("openrouter")
class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_key_env = api_key_env or "OPENROUTER_API_KEY"
        self.base_url = base_url or OPENROUTER_BASE_URL

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ModelResponse:
        if not self.api_key:
            raise ValueError(
                f"OpenRouter API key environment variable {self.api_key_env} is not set"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": model or DEFAULT_OPENROUTER_MODEL,
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
            model=data.get("model", model or DEFAULT_OPENROUTER_MODEL),
            usage=data.get("usage"),
            finish_reason=choice.get("finish_reason"),
            provider="openrouter",
        )


async def chat_complete(
    messages: list[dict[str, str]],
    model: str = DEFAULT_OPENROUTER_MODEL,
    api_key: str | None = None,
) -> str:
    if not api_key:
        raise ValueError("OpenRouter API key is required")
    response = await OpenRouterClient(api_key=api_key).complete(messages=messages, model=model)
    return response.content


def has_api_keys(api_key: str | None = None) -> bool:
    return bool(api_key)


def get_default_client(api_key: str, api_key_env: str | None = None) -> OpenRouterClient:
    return OpenRouterClient(api_key=api_key, api_key_env=api_key_env)


__all__ = [
    "OpenRouterClient",
    "OPENROUTER_BASE_URL",
    "DEFAULT_OPENROUTER_MODEL",
    "chat_complete",
    "has_api_keys",
    "get_default_client",
]
