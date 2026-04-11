"""
Model routing policy - determines which provider/model to use for a task.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.freqtrade.settings import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL
from app.services.config_service import ConfigService


@dataclass
class RoutingPolicy:
    task_type: str
    complexity: Literal["low", "medium", "high"]
    preferred_provider: str
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    fallback_provider: str | None = None
    fallback_model: str | None = None
    stream_preferred: bool = False
    ollama_host: str | None = None
    settings_snapshot: dict[str, Any] = field(default_factory=dict)


ROUTING_POLICIES: list[RoutingPolicy] = [
    RoutingPolicy(task_type="casual_chat", complexity="low", preferred_provider="ollama", model=DEFAULT_OLLAMA_MODEL, fallback_provider="openrouter", fallback_model="openai/gpt-4o-mini", stream_preferred=True),
    RoutingPolicy(task_type="classification", complexity="low", preferred_provider="ollama", model=DEFAULT_OLLAMA_MODEL, fallback_provider="openrouter", fallback_model="openai/gpt-4o-mini", stream_preferred=False),
    RoutingPolicy(task_type="analysis", complexity="medium", preferred_provider="ollama", model=DEFAULT_OLLAMA_MODEL, fallback_provider="openrouter", fallback_model="openai/gpt-4o-mini", stream_preferred=True),
    RoutingPolicy(task_type="candidate_generation", complexity="high", preferred_provider="openrouter", model="openai/gpt-4o", fallback_provider="ollama", fallback_model=DEFAULT_OLLAMA_MODEL, stream_preferred=False),
    RoutingPolicy(task_type="comparison", complexity="high", preferred_provider="openrouter", model="openai/gpt-4o", fallback_provider="ollama", fallback_model=DEFAULT_OLLAMA_MODEL, stream_preferred=False),
]


def _load_ai_settings() -> dict[str, Any]:
    try:
        settings = ConfigService().get_settings()
        return settings if isinstance(settings, dict) else {}
    except Exception:
        return {}


def _ollama_host(settings: dict[str, Any]) -> str:
    return str(settings.get("ollama_host") or DEFAULT_OLLAMA_HOST).strip() or DEFAULT_OLLAMA_HOST


def _ollama_model(settings: dict[str, Any]) -> str:
    return str(settings.get("ollama_default_model") or DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL


def _openrouter_model(task_type: str, complexity: str) -> str:
    normalized_task = str(task_type or "").strip().lower()
    normalized_complexity = str(complexity or "medium").strip().lower()
    if normalized_task in {"casual_chat", "classification"} or normalized_complexity == "low":
        return "openai/gpt-4o-mini"
    return "openai/gpt-4o"


def _default_temperature(task_type: str, complexity: str) -> float:
    normalized_task = str(task_type or "").strip().lower()
    if normalized_task in {"candidate_generation", "code_generation", "structured_output"}:
        return 0.2
    if normalized_task in {"classification", "diagnosis_overlay"}:
        return 0.2
    if normalized_task in {"comparison", "deep_reasoning"} or str(complexity or "").strip().lower() == "high":
        return 0.3
    if normalized_task in {"analysis", "explanation"}:
        return 0.4
    return 0.7


def _default_max_tokens(task_type: str, complexity: str) -> int | None:
    normalized_task = str(task_type or "").strip().lower()
    normalized_complexity = str(complexity or "medium").strip().lower()
    if normalized_task in {"candidate_generation", "code_generation", "structured_output"}:
        return 4000 if normalized_complexity != "high" else 8000
    if normalized_task in {"analysis", "comparison", "deep_reasoning"}:
        return 4000
    if normalized_task == "classification":
        return 500
    if normalized_task == "diagnosis_overlay":
        return 1800
    return None


def get_routing_policy(task_type: str, complexity: str = "medium", model_override: str | None = None) -> RoutingPolicy:
    normalized_task = str(task_type or "analysis").strip().lower() or "analysis"
    normalized_complexity = str(complexity or "medium").strip().lower() or "medium"
    settings = _load_ai_settings()
    ollama_host = _ollama_host(settings)
    ollama_model = model_override or _ollama_model(settings)
    openrouter_model = model_override or _openrouter_model(normalized_task, normalized_complexity)

    local_first_tasks = {"casual_chat", "classification", "analysis", "explanation", "simple", "diagnosis_overlay"}
    deep_tasks = {"candidate_generation", "code_generation", "structured_output", "comparison", "deep_reasoning", "tool_calling"}

    if normalized_task in deep_tasks:
        preferred_provider = "openrouter"
        preferred_model = openrouter_model
        fallback_provider = "ollama"
        fallback_model = ollama_model
        stream_preferred = False
    else:
        preferred_provider = "ollama"
        preferred_model = ollama_model
        fallback_provider = "openrouter"
        fallback_model = _openrouter_model(normalized_task, normalized_complexity)
        stream_preferred = normalized_task in local_first_tasks

    return RoutingPolicy(
        task_type=normalized_task,
        complexity=normalized_complexity if normalized_complexity in {"low", "medium", "high"} else "medium",
        preferred_provider=preferred_provider,
        model=preferred_model,
        temperature=_default_temperature(normalized_task, normalized_complexity),
        max_tokens=_default_max_tokens(normalized_task, normalized_complexity),
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        stream_preferred=stream_preferred and preferred_provider == "ollama",
        ollama_host=ollama_host,
        settings_snapshot={
            "ollama_host": ollama_host,
            "ollama_default_model": ollama_model,
        },
    )


def get_fallback_policy() -> RoutingPolicy:
    return get_routing_policy("analysis", "medium")


__all__ = [
    "RoutingPolicy",
    "ROUTING_POLICIES",
    "get_routing_policy",
    "get_fallback_policy",
]
