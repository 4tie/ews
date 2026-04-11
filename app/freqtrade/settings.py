from __future__ import annotations

import os
from typing import Any, Mapping

from app.freqtrade.paths import default_freqtrade_config_path, user_data_dir, user_data_results_dir

SUPPORTED_TIMEFRAMES = [
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
]

SUPPORTED_EXCHANGES = [
    "binance",
    "kucoin",
    "bybit",
    "okx",
    "gate",
]

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")

DEFAULT_FREQTRADE_SETTINGS: dict[str, Any] = {
    "engine": "freqtrade",
    "freqtrade_path": "",
    "user_data_path": user_data_dir(),
    "default_exchange": "binance",
    "default_timeframe": "5m",
    "default_max_open_trades": 3,
    "default_timerange": "",
    "default_dry_run_wallet": 100,
    "theme": "dark",
    "results_base_path": user_data_results_dir(),
    "config_path": default_freqtrade_config_path(),
    "ollama_host": DEFAULT_OLLAMA_HOST,
    "ollama_default_model": DEFAULT_OLLAMA_MODEL,
}


def get_freqtrade_runtime_settings(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Merge persisted settings with freqtrade runtime defaults and derived paths."""
    merged = dict(DEFAULT_FREQTRADE_SETTINGS)
    if settings:
        merged.update(dict(settings))

    resolved_user_data_path = str(merged.get("user_data_path") or user_data_dir())
    merged["user_data_path"] = user_data_dir(resolved_user_data_path)

    if not merged.get("config_path"):
        merged["config_path"] = default_freqtrade_config_path(merged["user_data_path"])
    if not merged.get("results_base_path"):
        merged["results_base_path"] = user_data_results_dir(merged["user_data_path"])
    if not merged.get("ollama_host"):
        merged["ollama_host"] = DEFAULT_OLLAMA_HOST

    return merged


def get_freqtrade_path(settings: Mapping[str, Any] | None = None) -> str:
    return str(get_freqtrade_runtime_settings(settings).get("freqtrade_path") or "")


def get_user_data_path(settings: Mapping[str, Any] | None = None) -> str:
    return str(get_freqtrade_runtime_settings(settings).get("user_data_path") or "")


def get_config_path(settings: Mapping[str, Any] | None = None) -> str:
    return str(get_freqtrade_runtime_settings(settings).get("config_path") or "")


def get_results_base_path(settings: Mapping[str, Any] | None = None) -> str:
    return str(get_freqtrade_runtime_settings(settings).get("results_base_path") or "")
