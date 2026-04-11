import asyncio

from app.ai.models.model_routing_policy import get_routing_policy
from app.ai.models.ollama_client import OllamaClient
from app.ai.models.provider_dispatch import ProviderDispatch
from app.ai.models.registry import ModelResponse


def test_analysis_task_prefers_ollama_with_openrouter_fallback():
    route = get_routing_policy(
        "analysis",
        settings={
            "ollama_default_model": "llama3.1:latest",
            "ai_analysis_model": "",
        },
    )

    assert route.preferred_provider == "ollama"
    assert route.model == "llama3.1:latest"
    assert route.fallback_provider == "openrouter"
    assert route.stream_preferred is True


def test_candidate_task_prefers_openrouter_with_ollama_fallback():
    route = get_routing_policy(
        "candidate",
        settings={
            "ollama_default_model": "qwen2.5-coder:latest",
            "ai_candidate_model": "openrouter/custom-candidate-model",
        },
    )

    assert route.preferred_provider == "openrouter"
    assert route.model == "openrouter/custom-candidate-model"
    assert route.fallback_provider == "ollama"
    assert route.fallback_model == "qwen2.5-coder:latest"
    assert route.stream_preferred is False


def test_complete_for_task_falls_back_from_ollama_to_openrouter(monkeypatch):
    dispatch = ProviderDispatch()

    async def fake_complete(*, messages, provider=None, model=None, temperature=0.7, max_tokens=None, settings=None):
        if provider == "ollama":
            raise RuntimeError("ollama down")
        return ModelResponse(
            content="fallback answer",
            model=str(model or "meta-llama/llama-3.3-70b-instruct:free"),
            provider=str(provider or "openrouter"),
        )

    monkeypatch.setattr(dispatch, "complete", fake_complete)

    response = asyncio.run(
        dispatch.complete_for_task(
            task_type="analysis",
            messages=[{"role": "user", "content": "Explain the run."}],
            settings={
                "ollama_host": "http://127.0.0.1:11434",
                "ollama_default_model": "llama3:latest",
            },
        )
    )

    assert response.provider == "openrouter"
    assert response.content == "fallback answer"
    assert response.usage["fallback_used"] is True
    assert response.usage["routing_errors"][0].startswith("ollama:llama3:latest")


def test_ollama_discover_normalizes_cloud_and_show_failures(monkeypatch):
    client = OllamaClient(host="http://127.0.0.1:11434", model="llama3:latest")

    async def fake_get_version():
        return {"version": "0.20.2"}

    async def fake_list_models():
        return [
            {
                "name": "llama3:latest",
                "model": "llama3:latest",
                "details": {"family": "llama", "parameter_size": "8.0B", "quantization_level": "Q4_K_M"},
            },
            {
                "name": "deepseek-v3.2:cloud",
                "model": "deepseek-v3.2:cloud",
                "remote_host": "https://ollama.com:443",
                "details": {"family": "deepseek3.2", "parameter_size": "671B", "quantization_level": "fp8"},
            },
            {
                "name": "broken:latest",
                "model": "broken:latest",
                "details": {"family": "broken", "parameter_size": "7B", "quantization_level": "Q4_0"},
            },
        ]

    async def fake_show_model(model_name):
        if model_name == "broken:latest":
            raise RuntimeError("show failed")
        if model_name == "deepseek-v3.2:cloud":
            return {"capabilities": ["completion", "thinking"], "details": {"family": "deepseek3.2"}}
        return {"capabilities": ["completion", "tools"], "details": {"family": "llama"}}

    monkeypatch.setattr(client, "get_version", fake_get_version)
    monkeypatch.setattr(client, "list_models", fake_list_models)
    monkeypatch.setattr(client, "show_model", fake_show_model)

    payload = asyncio.run(client.discover())

    assert payload["reachable"] is True
    assert payload["version"] == "0.20.2"
    assert any("broken:latest" in error for error in payload["errors"])

    local_model = next(model for model in payload["models"] if model["name"] == "llama3:latest")
    cloud_model = next(model for model in payload["models"] if model["name"] == "deepseek-v3.2:cloud")
    broken_model = next(model for model in payload["models"] if model["name"] == "broken:latest")

    assert local_model["tool_calling_supported_by_model"] is True
    assert local_model["tool_calling_enabled_in_app"] is False
    assert cloud_model["source"] == "cloud"
    assert "strictly local-only execution" in cloud_model["app_not_recommended_for"]
    assert broken_model["raw_capabilities"] == []
    assert broken_model["tool_calling_supported_by_model"] is False
