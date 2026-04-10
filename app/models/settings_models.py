from pydantic import BaseModel, ConfigDict, field_validator


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    engine: str = "freqtrade"
    freqtrade_path: str = ""
    user_data_path: str = ""
    default_exchange: str = "binance"
    default_timeframe: str = "5m"
    default_max_open_trades: int = 3
    theme: str = "dark"
    results_base_path: str = ""
    config_path: str = ""

    @field_validator("engine")
    @classmethod
    def _validate_engine(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"freqtrade", "backtrader"}:
            raise ValueError("engine must be one of: freqtrade, backtrader")
        return normalized
