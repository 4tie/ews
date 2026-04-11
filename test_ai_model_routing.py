import asyncio

import pytest

from app.ai.models.model_routing_policy import get_routing_policy
from app.ai.models.provider_dispatch import ProviderDispatch
from app.ai.models.registry import ModelResponse


def test_routing_policy_uses_task_specific_settings_models():
    settings = {
        "ai_provider": "huggingface",
        "ai_analysis_model": "analysis-model",
        "ai_candidate_model": "candidate-model",
    }

    analysis_policy = get_routing_policy("analysis", settings=settings)
    candidate_policy = get_routing_policy("candidate", settings=settings)

    assert analysis_policy.provider == "huggingface"
    assert analysis_policy.model == "analysis-model"
    assert candidate_policy.provider == "huggingface"
    assert candidate_policy.model == "candidate-model"


def test_routing_policy_falls_back_to_provider_defaults():
    classifier_policy = get_routing_policy("classifier", settings={"ai_provider": "ollama"})
    overlay_policy = get_routing_policy("overlay", settings={"ai_provider": "openrouter"})

    assert classifier_policy.model == "llama3"
    assert overlay_policy.model.endswith(":free")


def test_complete_for_task_uses_resolved_provider_and_model(monkeypatch):
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
        return ModelResponse(content="{}", model=model or "analysis-model", provider=provider)

    monkeypatch.setattr(ProviderDispatch, "complete", _fake_complete, raising=True)

    response = asyncio.run(
        dispatch.complete_for_task(
            "analysis",
            [{"role": "user", "content": "hello"}],
            settings={
                "ai_provider": "huggingface",
                "ai_analysis_model": "analysis-model",
                "hf_token_env": "HF_TOKEN",
            },
        )
    )

    assert captured["provider"] == "huggingface"
    assert captured["model"] == "analysis-model"
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 4000
    assert response.provider == "huggingface"
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
