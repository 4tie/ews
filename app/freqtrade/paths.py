from __future__ import annotations

import os

from app.utils.paths import BASE_DIR, resolve_safe

USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")


def user_data_dir(user_data_path: str | None = None) -> str:
    """Return the resolved freqtrade user_data root."""
    return os.path.realpath(user_data_path or USER_DATA_DIR)


def user_data_results_dir(user_data_path: str | None = None) -> str:
    """Return the resolved freqtrade backtest results directory."""
    return resolve_safe(user_data_dir(user_data_path), "backtest_results")


def strategy_results_dir(strategy: str, user_data_path: str | None = None) -> str:
    """Return the resolved strategy-specific backtest results directory."""
    return resolve_safe(user_data_results_dir(user_data_path), strategy)


def default_freqtrade_config_path(user_data_path: str | None = None) -> str:
    """Return the resolved default freqtrade config.json path."""
    return os.path.join(user_data_dir(user_data_path), "config.json")


def live_strategy_file(strategy_name: str, user_data_path: str | None = None) -> str:
    """Return the resolved live strategy source path."""
    return resolve_safe(user_data_dir(user_data_path), "strategies", f"{strategy_name}.py")


def strategy_config_file(strategy_name: str, user_data_path: str | None = None) -> str:
    """Return the resolved strategy-specific config overlay path."""
    return resolve_safe(user_data_dir(user_data_path), "config", f"config_{strategy_name}.json")
