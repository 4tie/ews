from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.ai.models.ollama_client import OllamaClient
from app.models.settings_models import AppSettings
from app.services.config_service import ConfigService
from app.services.validation_service import ValidationService

router = APIRouter()
config_svc = ConfigService()
validation_svc = ValidationService()


class PathValidateRequest(BaseModel):
    path: str
    kind: str | None = None


class OllamaDiscoverRequest(BaseModel):
    host: str | None = None


@router.get("")
async def get_settings():
    """Return current application settings."""
    return config_svc.get_settings()


@router.post("")
async def save_settings(payload: AppSettings):
    """Persist application settings."""
    config_svc.save_settings(payload.model_dump())
    return {"status": "saved"}


@router.post("/validate-path")
async def validate_path(payload: PathValidateRequest):
    """Validate a settings path, with Freqtrade-aware executable resolution when requested."""
    kind = (payload.kind or "").strip().lower()

    if kind == "freqtrade":
        result = validation_svc.validate_freqtrade_path(payload.path)
        response = {"valid": bool(result.get("valid")), "path": payload.path}
        if result.get("valid"):
            response["resolved_path"] = result.get("resolved_path")
        else:
            response["error"] = result.get("error")
        return response

    valid = validation_svc.validate_path(payload.path)
    return {"valid": valid, "path": payload.path}


@router.post("/ai/ollama/discover")
async def discover_ollama(payload: OllamaDiscoverRequest):
    """Probe an Ollama host and return normalized model capability data."""
    settings = config_svc.get_settings()
    host = str(payload.host or settings.get("ollama_host") or "http://127.0.0.1:11434").strip()

    client = OllamaClient(host=host, model=str(settings.get("ollama_default_model") or "").strip() or None)
    try:
        return await client.discover()
    except Exception as exc:
        return {
            "host": host,
            "reachable": False,
            "version": None,
            "models": [],
            "errors": [str(exc)],
        }