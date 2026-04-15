from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.core.models.backtest_models import BacktestRunRecord


class EngineError(RuntimeError):
    pass


class EngineFeatureNotSupported(NotImplementedError):
    def __init__(self, engine_id: str, feature: str, detail: str | None = None):
        message = f"Engine '{engine_id}' does not support {feature}"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)
        self.engine_id = engine_id
        self.feature = feature
        self.detail = detail


@dataclass(frozen=True)
class ParsedBacktestResult:
    strategy_result: dict[str, Any]
    profit_pct: float | None
    strategy_comparison: Any | None = None


class ResultParser(ABC):
    @abstractmethod
    def parse_backtest_run(self, run_record: BacktestRunRecord) -> ParsedBacktestResult:
        raise NotImplementedError


class BacktestEngine(ABC):
    engine_id: str

    @abstractmethod
    def list_strategies(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def prepare_backtest_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def run_backtest(
        self, payload: dict[str, Any], prepared: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError

    def resolve_backtest_raw_result_path(
        self, run_record: BacktestRunRecord
    ) -> str | None:
        return run_record.raw_result_path

    def prepare_download_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise EngineFeatureNotSupported(self.engine_id, "download-data")

    def run_download_data(
        self, prepared: dict[str, Any], log_path: str | None = None
    ) -> dict[str, Any]:
        raise EngineFeatureNotSupported(self.engine_id, "download-data")

    def validate_data(
        self,
        pairs: list[str],
        timeframe: str,
        exchange: str | None = None,
        timerange: str | None = None,
    ) -> list[dict[str, Any]]:
        raise EngineFeatureNotSupported(self.engine_id, "validate-data")
