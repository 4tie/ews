from __future__ import annotations

from typing import Any

from app.engines.base import BacktestEngine, EngineFeatureNotSupported


class BacktraderEngine(BacktestEngine):
    engine_id = "backtrader"

    def list_strategies(self) -> list[str]:
        raise EngineFeatureNotSupported(
            self.engine_id,
            "list-strategies",
            "Backtrader engine is not implemented yet.",
        )

    def prepare_backtest_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise EngineFeatureNotSupported(
            self.engine_id,
            "backtest-run",
            "Backtrader backtest execution is not implemented yet.",
        )

    def run_backtest(self, payload: dict[str, Any], prepared: dict[str, Any] | None = None) -> dict[str, Any]:
        raise EngineFeatureNotSupported(
            self.engine_id,
            "backtest-run",
            "Backtrader backtest execution is not implemented yet.",
        )
