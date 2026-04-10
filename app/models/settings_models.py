from pydantic import BaseModel
from typing import Optional


class AppSettings(BaseModel):
    freqtrade_path: str = ""
    user_data_path: str = ""
    default_exchange: str = "binance"
    default_timeframe: str = "5m"
    default_stake_amount: float = 100.0
    default_max_open_trades: int = 3
    theme: str = "dark"
    results_base_path: str = ""
    config_path: str = ""
