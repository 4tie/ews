from pydantic import BaseModel, ConfigDict, field_validator


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
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_default_model: str = ""

    @field_validator("engine")
    @classmethod
    def _validate_engine(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"freqtrade"}:
            raise ValueError("engine must be: freqtrade")
        return normalized
