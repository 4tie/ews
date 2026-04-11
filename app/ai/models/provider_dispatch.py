"""
Provider dispatch - selects and instantiates the appropriate LLM client.
"""
from __future__ import annotations

import os
from typing import Any, Literal, Mapping

from app.ai.models.huggingface_client import HuggingFaceClient
from app.ai.models.model_routing_policy import DEFAULT_AI_PROVIDER, get_routing_policy, normalize_provider
from app.ai.models.ollama_client import OllamaClient
from app.ai.models.openrouter_client import OpenRouterClient
from app.ai.models.registry import ModelResponse
from app.services.config_service import ConfigService


ProviderType = Literal["openrouter", "ollama", "huggingface", "openai"]


class ProviderDispatch:
    def __init__(self, default_provider: str = DEFAULT_AI_PROVIDER):
        self.default_provider = normalize_provider(default_provider)
        self._clients: dict[tuple[Any, ...], object] = {}
        self._config_service = ConfigService()

    def _load_settings(self, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if settings is not None:
            return dict(settings)
        try:
            return dict(self._config_service.get_settings())
        except Exception:
            return {}

    def _resolve_cache_key(self, provider: str, settings: Mapping[str, Any]) -> tuple[Any, ...]:
        if provider == "ollama":
            return (provider, str(settings.get("ollama_host") or "http://localhost:11434").strip())
        if provider == "openrouter":
            return (provider, str(settings.get("openrouter_api_key_env") or "OPENROUTER_API_KEY").strip())
        if provider == "huggingface":
            return (provider, str(settings.get("hf_token_env") or "HF_TOKEN").strip())
        if provider == "openai":
            return (provider, "OPENAI_API_KEY")
        return (provider,)

    def get_client(
        self,
        provider: str | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> object:
        payload = self._load_settings(settings)
        resolved_provider = normalize_provider(provider or payload.get("ai_provider") or self.default_provider)
        cache_key = self._resolve_cache_key(resolved_provider, payload)
        if cache_key in self._clients:
            return self._clients[cache_key]

        if resolved_provider == "openrouter":
            env_name = str(payload.get("openrouter_api_key_env") or "OPENROUTER_API_KEY").strip()
            api_key = os.environ.get(env_name, "")
            if not api_key:
                raise ValueError(f"OpenRouter API key environment variable {env_name} is not set")
            client = OpenRouterClient(api_key=api_key, api_key_env=env_name)
        elif resolved_provider == "ollama":
            client = OllamaClient(
                host=str(payload.get("ollama_host") or "http://localhost:11434").strip() or None,
            )
        elif resolved_provider == "huggingface":
            env_name = str(payload.get("hf_token_env") or "HF_TOKEN").strip()
            token = os.environ.get(env_name, "")
            if not token:
                raise ValueError(f"Hugging Face token environment variable {env_name} is not set")
            client = HuggingFaceClient(api_key=token, api_key_env=env_name)
        elif resolved_provider == "openai":
            from openai import AsyncOpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set")
            client = AsyncOpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unknown provider: {resolved_provider}")

        self._clients[cache_key] = client
        return client

    async def complete(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> ModelResponse:
        payload = self._load_settings(settings)
        resolved_provider = normalize_provider(provider or payload.get("ai_provider") or self.default_provider)
        client = self.get_client(resolved_provider, settings=payload)

        if hasattr(client, "complete"):
            response = await client.complete(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response.provider = response.provider or resolved_provider
            return response
        if hasattr(client, "chat"):
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
                provider=resolved_provider,
            )
        raise ValueError(f"Client {resolved_provider} has no complete or chat method")

    async def complete_for_task(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        *,
        settings: Mapping[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelResponse:
        payload = self._load_settings(settings)
        policy = get_routing_policy(
            task_type=task_type,
            settings=payload,
            provider_override=provider,
            model_override=model,
        )
        response = await self.complete(
            messages=messages,
            provider=policy.provider,
            model=policy.model,
            temperature=policy.temperature if temperature is None else temperature,
            max_tokens=policy.max_tokens if max_tokens is None else max_tokens,
            settings=payload,
        )
        response.task_type = task_type
        response.provider = response.provider or policy.provider
        return response


_default_dispatch: ProviderDispatch | None = None


def get_dispatch() -> ProviderDispatch:
    global _default_dispatch
    if _default_dispatch is None:
        default = os.environ.get("DEFAULT_AI_PROVIDER", DEFAULT_AI_PROVIDER)
        _default_dispatch = ProviderDispatch(default_provider=str(default))
    return _default_dispatch


__all__ = ["ProviderDispatch", "get_dispatch", "ProviderType"]
