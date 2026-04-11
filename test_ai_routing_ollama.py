"""
Tests for Ollama model routing.
"""
from app.ai.models.model_routing_policy import get_routing_policy


def test_light_task_prefers_ollama():
    """Test that analysis tasks prefer Ollama when configured."""
    settings = {
        "ollama_host": "http://127.0.0.1:11434",
        "ollama_default_model": "llama3:latest",
    }

    route = get_routing_policy("analysis", settings=settings)

    assert route.preferred_provider == "ollama"
    assert route.task_type == "analysis"
    assert route.fallback_provider == "openrouter"


def test_candidate_task_routing():
    """Test candidate task routing."""
    settings = {
        "ollama_host": "http://127.0.0.1:11434",
        "ollama_default_model": "qwen2.5-coder:latest",
    }

    route = get_routing_policy("candidate", settings=settings)

    assert route.task_type == "candidate"
    assert route.provider is not None
    assert route.fallback_provider is not None


def test_overlay_task_routing():
    """Test overlay task routing."""
    settings = {
        "ollama_host": "http://127.0.0.1:11434",
        "ollama_default_model": "llama3:latest",
    }

    route = get_routing_policy("overlay", settings=settings)

    assert route.task_type == "overlay"
    assert route.provider is not None
