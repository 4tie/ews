from fastapi import APIRouter
from pydantic import BaseModel
from models.settings_models import AppSettings
from services.config_service import ConfigService
from services.validation_service import ValidationService
import os

router = APIRouter()
config_svc = ConfigService()
validation_svc = ValidationService()


@router.get("")
async def get_settings():
    """Return current application settings."""
    return config_svc.get_settings()


@router.post("")
async def save_settings(payload: AppSettings):
    """Persist application settings."""
    config_svc.save_settings(payload.model_dump())
    return {"status": "saved"}


class PathValidateRequest(BaseModel):
    path: str


@router.post("/validate-path")
async def validate_path(payload: PathValidateRequest):
    """Check if a filesystem path exists."""
    valid = os.path.exists(payload.path)
    return {"valid": valid, "path": payload.path}
