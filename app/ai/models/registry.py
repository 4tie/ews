"""
AI Models - Provider registry and dispatch.
"""
from __future__ import annotations

from typing import Protocol, Any, Callable
from dataclasses import dataclass


@dataclass
class ModelResponse:
    content: str
    model: str
    usage: dict[str, int] | None = None
    finish_reason: str | None = None


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any
    ) -> ModelResponse:
        ...


PROVIDER_REGISTRY: dict[str, type[LLMClient]] = {}


def register_provider(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        PROVIDER_REGISTRY[name] = cls
        return cls
    return decorator


def get_provider(name: str) -> type[LLMClient] | None:
    return PROVIDER_REGISTRY.get(name)


def list_providers() -> list[str]:
    return list(PROVIDER_REGISTRY.keys())


__all__ = [
    "ModelResponse",
    "LLMClient",
    "PROVIDER_REGISTRY",
    "register_provider",
    "get_provider",
    "list_providers",
]
