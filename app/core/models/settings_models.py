import os
import re

from pydantic import BaseModel, ConfigDict, field_validator


_SUPPORTED_AI_PROVIDERS = {"ollama", "openrouter", "huggingface", "openai"}
_ENV_REF_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    engine: str = "freqtrade"
    freqtrade_path: str = ""
    user_data_path: str = ""
    default_exchange: str = "binance"
    default_timeframe: str = "5m"
    default_max_open_trades: int = 1
    default_timerange: str = ""
    default_dry_run_wallet: float = 100
    theme: str = "dark"
    results_base_path: str = ""
    config_path: str = ""

    ai_provider: str = "ollama"
    ai_classifier_model: str = ""
    ai_analysis_model: str = ""
    ai_candidate_model: str = ""
    ai_overlay_model: str = ""
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_default_model: str = ""
    openrouter_api_key_env: str = "OPENROUTER_API_KEY"
    hf_token_env: str = "HF_TOKEN"

    @field_validator("engine")
    @classmethod
    def _validate_engine(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"freqtrade"}:
            raise ValueError("engine must be: freqtrade")
        return normalized

    @field_validator("ai_provider")
    @classmethod
    def _validate_ai_provider(cls, value: str) -> str:
        normalized = (value or "ollama").strip().lower()
        if normalized not in _SUPPORTED_AI_PROVIDERS:
            raise ValueError("ai_provider must be one of: ollama, openrouter, huggingface, openai")
        return normalized

    @field_validator(
        "freqtrade_path",
        "user_data_path",
        "config_path",
        "results_base_path",
        mode="before",
    )
    @classmethod
    def _normalize_path_fields(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {'"', "'"}:
            normalized = normalized[1:-1].strip()
        if not normalized:
            return ""
        return os.path.normpath(normalized)

    @field_validator(
        "ai_classifier_model",
        "ai_analysis_model",
        "ai_candidate_model",
        "ai_overlay_model",
        "ollama_host",
        "ollama_default_model",
        mode="before",
    )
    @classmethod
    def _normalize_string_fields(cls, value: str | None) -> str:
        return str(value or "").strip()

    @field_validator("openrouter_api_key_env", "hf_token_env")
    @classmethod
    def _validate_env_ref(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if normalized and not _ENV_REF_PATTERN.fullmatch(normalized):
            raise ValueError("environment variable references must use letters, digits, and underscores only")
        return normalized
