"""
Provider dispatch - selects and instantiates the appropriate LLM client.
"""
from __future__ import annotations

import os
from typing import Literal

from app.ai.models.registry import get_provider, ModelResponse
from app.ai.models.openrouter_client import OpenRouterClient
from app.ai.models.ollama_client import OllamaClient


ProviderType = Literal["openrouter", "ollama", "openai"]


class ProviderDispatch:
    def __init__(self, default_provider: str = "openrouter"):
        self.default_provider = default_provider
        self._clients: dict[str, object] = {}
    
    def get_client(self, provider: str | None = None) -> object:
        provider = provider or self.default_provider
        
        if provider in self._clients:
            return self._clients[provider]
        
        if provider == "openrouter":
            client = OpenRouterClient()
        elif provider == "ollama":
            client = OllamaClient()
        elif provider == "openai":
            from openai import AsyncOpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set")
            client = AsyncOpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unknown provider: {provider}")
        
        self._clients[provider] = client
        return client
    
    async def complete(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        client = self.get_client(provider)
        
        if hasattr(client, "complete"):
            return await client.complete(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif hasattr(client, "chat"):
            response = await client.chat.completions.create(
                model=model or "gpt-4o",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return ModelResponse(
                content=response.choices[0].message.content,
                model=response.model,
                usage=dict(response.usage) if response.usage else None,
                finish_reason=response.choices[0].finish_reason,
            )
        else:
            raise ValueError(f"Client {provider} has no complete or chat method")


_default_dispatch: ProviderDispatch | None = None


def get_dispatch() -> ProviderDispatch:
    global _default_dispatch
    if _default_dispatch is None:
        default = os.environ.get("DEFAULT_AI_PROVIDER", "openrouter")
        _default_dispatch = ProviderDispatch(default_provider=str(default))
    return _default_dispatch


__all__ = ["ProviderDispatch", "get_dispatch", "ProviderType"]
