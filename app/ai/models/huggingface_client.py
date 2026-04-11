"""
Hugging Face router provider client.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.ai.models.registry import ModelResponse, register_provider


HUGGINGFACE_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_HUGGINGFACE_MODEL = "openai/gpt-oss-20b"


@register_provider("huggingface")
class HuggingFaceClient:
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        api_key_env: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url or HUGGINGFACE_BASE_URL
        self.api_key_env = api_key_env or "HF_TOKEN"

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
                f"Hugging Face token environment variable {self.api_key_env} is not set"
            )

        payload: dict[str, Any] = {
            "model": model or DEFAULT_HUGGINGFACE_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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
            model=data.get("model", payload["model"]),
            usage=data.get("usage"),
            finish_reason=choice.get("finish_reason"),
            provider="huggingface",
        )


def get_default_client(api_key: str, api_key_env: str | None = None) -> HuggingFaceClient:
    return HuggingFaceClient(api_key=api_key, api_key_env=api_key_env)


__all__ = ["HuggingFaceClient", "DEFAULT_HUGGINGFACE_MODEL", "get_default_client"]
