"""
Model routing policy - determines which provider/model pair to use per AI task.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DEFAULT_AI_PROVIDER = "ollama"
SUPPORTED_AI_PROVIDERS = {"ollama", "openrouter", "huggingface", "openai"}
AI_TASK_TYPES = ("classifier", "analysis", "candidate", "overlay")

_TASK_SETTING_KEYS = {
    "classifier": "ai_classifier_model",
    "analysis": "ai_analysis_model",
    "candidate": "ai_candidate_model",
    "overlay": "ai_overlay_model",
}
_TASK_DEFAULTS = {
    "classifier": {"temperature": 0.2, "max_tokens": 800},
    "analysis": {"temperature": 0.3, "max_tokens": 4000},
    "candidate": {"temperature": 0.25, "max_tokens": 4000},
    "overlay": {"temperature": 0.2, "max_tokens": 1800},
}
_PROVIDER_DEFAULT_MODELS = {
    "ollama": {
        "classifier": "llama3",
        "analysis": "llama3",
        "candidate": "llama3",
        "overlay": "llama3",
    },
    "openrouter": {
        "classifier": "meta-llama/llama-3.3-70b-instruct:free",
        "analysis": "meta-llama/llama-3.3-70b-instruct:free",
        "candidate": "meta-llama/llama-3.3-70b-instruct:free",
        "overlay": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "huggingface": {
        "classifier": "openai/gpt-oss-20b",
        "analysis": "openai/gpt-oss-20b",
        "candidate": "openai/gpt-oss-20b",
        "overlay": "openai/gpt-oss-20b",
    },
    "openai": {
        "classifier": "gpt-4o-mini",
        "analysis": "gpt-4o",
        "candidate": "gpt-4o",
        "overlay": "gpt-4o-mini",
    },
}


@dataclass
class RoutingPolicy:
    task_type: str
    provider: str
    model: str
    temperature: float = 0.3
    max_tokens: int | None = None

    @property
    def preferred_provider(self) -> str:
        return self.provider


def normalize_provider(provider: str | None) -> str:
    normalized = str(provider or DEFAULT_AI_PROVIDER).strip().lower()
    if normalized not in SUPPORTED_AI_PROVIDERS:
        return DEFAULT_AI_PROVIDER
    return normalized


def _get_model_for_task(task_type: str, provider: str, settings: Mapping[str, Any]) -> str:
    setting_key = _TASK_SETTING_KEYS.get(task_type, "ai_analysis_model")
    configured = str(settings.get(setting_key) or "").strip()
    if configured:
        return configured
    provider_defaults = _PROVIDER_DEFAULT_MODELS.get(provider, _PROVIDER_DEFAULT_MODELS[DEFAULT_AI_PROVIDER])
    return provider_defaults.get(task_type, provider_defaults["analysis"])


def get_routing_policy(
    task_type: str,
    complexity: str = "medium",
    settings: Mapping[str, Any] | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> RoutingPolicy:
    del complexity
    normalized_task = task_type if task_type in AI_TASK_TYPES else "analysis"
    payload = dict(settings or {})
    provider = normalize_provider(provider_override or payload.get("ai_provider"))
    model = str(model_override or "").strip() or _get_model_for_task(normalized_task, provider, payload)
    defaults = _TASK_DEFAULTS.get(normalized_task, _TASK_DEFAULTS["analysis"])
    return RoutingPolicy(
        task_type=normalized_task,
        provider=provider,
        model=model,
        temperature=float(defaults["temperature"]),
        max_tokens=int(defaults["max_tokens"]) if defaults.get("max_tokens") is not None else None,
    )


ROUTING_POLICIES: list[RoutingPolicy] = [get_routing_policy(task_type) for task_type in AI_TASK_TYPES]


def get_fallback_policy(settings: Mapping[str, Any] | None = None) -> RoutingPolicy:
    return get_routing_policy("analysis", settings=settings)


__all__ = [
    "AI_TASK_TYPES",
    "DEFAULT_AI_PROVIDER",
    "SUPPORTED_AI_PROVIDERS",
    "RoutingPolicy",
    "ROUTING_POLICIES",
    "normalize_provider",
    "get_routing_policy",
    "get_fallback_policy",
]
