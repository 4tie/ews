import asyncio

import pytest

from app.ai.models.model_routing_policy import get_routing_policy
from app.ai.models.provider_dispatch import ProviderDispatch
from app.ai.models.registry import ModelResponse


def test_routing_policy_uses_task_specific_settings_models():
    """Test that task-specific model settings are used when configured."""
    settings = {
        "ai_analysis_model": "custom-analysis-model",
        "ai_candidate_model": "custom-candidate-model",
    }

    analysis_policy = get_routing_policy("analysis", settings=settings)
    candidate_policy = get_routing_policy("candidate", settings=settings)

    # Provider selection is determined by task type, not settings
    assert analysis_policy.provider == "ollama"  # Default for analysis
    assert analysis_policy.model == "custom-analysis-model"  # From settings
    
    assert candidate_policy.provider == "openrouter"  # Candidates always prefer openrouter
    assert candidate_policy.model == "custom-candidate-model"  # From settings


def test_routing_policy_falls_back_to_provider_defaults():
    """Test that provider defaults are used when no specific model is configured."""
    classifier_policy = get_routing_policy("classifier")
    overlay_policy = get_routing_policy("overlay")

    # Both default to ollama provider
    assert classifier_policy.provider == "ollama"
    assert classifier_policy.model == "llama3"  # Default ollama model for classifier
    
    assert overlay_policy.provider == "ollama"
    assert overlay_policy.fallback_provider == "openrouter"
    assert overlay_policy.fallback_model is not None  # Fallback has a model


def test_complete_for_task_uses_resolved_provider_and_model(monkeypatch):
    """Test that complete_for_task respects ai_provider setting."""
    dispatch = ProviderDispatch()
    captured = {}

    async def _fake_complete(self, messages, provider=None, model=None, temperature=0.7, max_tokens=None, settings=None):
        captured.update({
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "settings": settings,
        })
        return ModelResponse(content="{}", model=model or "analysis-model", provider=provider or "ollama")

    monkeypatch.setattr(ProviderDispatch, "complete", _fake_complete, raising=True)

    response = asyncio.run(
        dispatch.complete_for_task(
            "analysis",
            [{"role": "user", "content": "hello"}],
            settings={
                "ai_provider": "ollama",  # Now respects the ai_provider setting
                "ai_analysis_model": "analysis-model",
                "hf_token_env": "HF_TOKEN",
            },
        )
    )

    assert captured["provider"] == "ollama"  # Uses the setting
    assert captured["model"] == "analysis-model"
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 4000
    assert response.provider == "ollama"
    assert response.task_type == "analysis"


def test_huggingface_client_requires_configured_env_reference(monkeypatch):
    monkeypatch.delenv("MISSING_HF_TOKEN", raising=False)
    dispatch = ProviderDispatch()

    with pytest.raises(ValueError) as excinfo:
        dispatch.get_client("huggingface", settings={"hf_token_env": "MISSING_HF_TOKEN"})

    assert "MISSING_HF_TOKEN" in str(excinfo.value)


def test_openrouter_client_requires_configured_env_reference(monkeypatch):
    monkeypatch.delenv("MISSING_OPENROUTER_KEY", raising=False)
    dispatch = ProviderDispatch()

    with pytest.raises(ValueError) as excinfo:
        dispatch.get_client("openrouter", settings={"openrouter_api_key_env": "MISSING_OPENROUTER_KEY"})

    assert "MISSING_OPENROUTER_KEY" in str(excinfo.value)
