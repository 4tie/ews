import pytest
from fastapi.testclient import TestClient

from app.engines.resolver import resolve_engine, resolve_engine_id
from app.freqtrade.engine import FreqtradeEngine
from app.freqtrade.settings import get_freqtrade_runtime_settings
from app.main import app
from app.routers import settings as settings_router


client = TestClient(app)


def test_resolve_engine_uses_consolidated_freqtrade_engine():
    assert resolve_engine_id({"engine": ""}) == "freqtrade"
    assert isinstance(resolve_engine({"engine": "freqtrade"}), FreqtradeEngine)

    with pytest.raises(ValueError):
        resolve_engine_id({"engine": "unknown"})


def test_settings_route_returns_freqtrade_runtime_defaults(monkeypatch):
    monkeypatch.setattr(
        settings_router.config_svc,
        "get_settings",
        lambda: get_freqtrade_runtime_settings({"freqtrade_path": "T:/freqtrade"}),
    )

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine"] == "freqtrade"
    assert payload["freqtrade_path"] == "T:/freqtrade"
    assert "config_path" in payload
    assert "results_base_path" in payload

def test_runtime_settings_backfill_ai_defaults():
    payload = get_freqtrade_runtime_settings({"freqtrade_path": "T:/freqtrade"})

    assert payload["ai_provider"] == "ollama"
    assert payload["ai_classifier_model"] == ""
    assert payload["ai_analysis_model"] == ""
    assert payload["ai_candidate_model"] == ""
    assert payload["ai_overlay_model"] == ""
    assert payload["ollama_host"] == "http://localhost:11434"
    assert payload["openrouter_api_key_env"] == "OPENROUTER_API_KEY"
    assert payload["hf_token_env"] == "HF_TOKEN"
