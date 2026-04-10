from __future__ import annotations

from typing import Any

from app.engines.backtrader.engine import BacktraderEngine
from app.engines.backtrader.result_parser import BacktraderResultParser
from app.engines.base import BacktestEngine, ResultParser
from app.engines.freqtrade.engine import FreqtradeEngine
from app.engines.freqtrade.result_parser import FreqtradeResultParser
from app.services.config_service import ConfigService

_DEFAULT_ENGINE_ID = "freqtrade"

_ENGINE_REGISTRY: dict[str, type[BacktestEngine]] = {
    "freqtrade": FreqtradeEngine,
    "backtrader": BacktraderEngine,
}

_PARSER_REGISTRY: dict[str, type[ResultParser]] = {
    "freqtrade": FreqtradeResultParser,
    "backtrader": BacktraderResultParser,
}


def normalize_engine_id(engine: str | None) -> str:
    if engine is None or str(engine).strip() == "":
        return _DEFAULT_ENGINE_ID

    normalized = str(engine).strip().lower()
    if normalized not in _ENGINE_REGISTRY:
        supported = ", ".join(sorted(_ENGINE_REGISTRY))
        raise ValueError(f"Unknown engine '{engine}'. Supported engines: {supported}")

    return normalized


def resolve_engine_id(settings: dict[str, Any] | None = None) -> str:
    settings = settings or ConfigService().get_settings()
    return normalize_engine_id(settings.get("engine"))


def engine_from_id(engine_id: str | None) -> BacktestEngine:
    normalized = normalize_engine_id(engine_id)
    return _ENGINE_REGISTRY[normalized]()


def resolve_engine(settings: dict[str, Any] | None = None) -> BacktestEngine:
    return engine_from_id(resolve_engine_id(settings))


def result_parser_from_id(engine_id: str | None) -> ResultParser:
    normalized = normalize_engine_id(engine_id)
    return _PARSER_REGISTRY[normalized]()
