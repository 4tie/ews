from fastapi.testclient import TestClient

from app.freqtrade.settings import get_freqtrade_runtime_settings
from app.main import app
from app.routers import settings as settings_router


client = TestClient(app)


def test_settings_route_includes_ollama_defaults(monkeypatch):
    monkeypatch.setattr(
        settings_router.config_svc,
        "get_settings",
        lambda: get_freqtrade_runtime_settings({"freqtrade_path": "T:/freqtrade"}),
    )

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine"] == "freqtrade"
    assert payload["ollama_host"] == "http://127.0.0.1:11434"
    assert payload["ollama_default_model"] == "llama3"


def test_ollama_discovery_route_returns_normalized_payload(monkeypatch):
    class FakeOllamaClient:
        def __init__(self, host=None, model=None):
            self.host = host
            self.model = model

        async def discover(self):
            return {
                "host": self.host,
                "reachable": True,
                "version": "0.20.2",
                "errors": [],
                "models": [
                    {
                        "name": "qwen2.5-coder:latest",
                        "source": "local",
                        "source_label": "Local",
                        "raw_capabilities": ["completion", "tools", "insert"],
                        "app_recommended_for": ["code review and patch drafting"],
                        "app_not_recommended_for": ["tool calling"],
                        "tool_calling_supported_by_model": True,
                        "tool_calling_enabled_in_app": False,
                    },
                    {
                        "name": "deepseek-v3.2:cloud",
                        "source": "cloud",
                        "source_label": "Cloud via Ollama",
                        "raw_capabilities": ["completion"],
                        "app_recommended_for": ["general analysis and explanation"],
                        "app_not_recommended_for": ["strictly local-only execution"],
                        "tool_calling_supported_by_model": False,
                        "tool_calling_enabled_in_app": False,
                    },
                ],
            }

    monkeypatch.setattr(settings_router, "OllamaClient", FakeOllamaClient)

    response = client.post("/api/settings/ai/ollama/discover", json={"host": "http://127.0.0.1:11434"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["reachable"] is True
    assert payload["version"] == "0.20.2"
    assert payload["models"][0]["source"] == "local"
    assert payload["models"][1]["source"] == "cloud"
    assert payload["models"][0]["tool_calling_enabled_in_app"] is False


def test_ollama_discovery_route_handles_unreachable_host(monkeypatch):
    class FakeOllamaClient:
        def __init__(self, host=None, model=None):
            self.host = host
            self.model = model

        async def discover(self):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(settings_router, "OllamaClient", FakeOllamaClient)

    response = client.post("/api/settings/ai/ollama/discover", json={"host": "http://127.0.0.1:11434"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["reachable"] is False
    assert payload["models"] == []
    assert payload["errors"] == ["connection refused"]
