from __future__ import annotations

import os
from typing import Any

from app.engines.base import BacktestEngine
from app.models.backtest_models import BacktestRunRecord
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.utils.paths import BASE_DIR


class FreqtradeEngine(BacktestEngine):
    engine_id = "freqtrade"

    def __init__(self, cli_service: FreqtradeCliService | None = None):
        self._cli = cli_service or FreqtradeCliService()

    def list_strategies(self) -> list[str]:
        return self._cli.list_strategies()

    def prepare_backtest_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._cli.prepare_backtest_run(payload)

    def run_backtest(self, payload: dict[str, Any], prepared: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._cli.run_backtest(payload, prepared=prepared)

    def resolve_backtest_raw_result_path(self, run_record: BacktestRunRecord) -> str | None:
        return self._cli.resolve_backtest_raw_result(
            run_record.strategy,
            run_record.run_id,
            run_record.created_at,
        )

    def prepare_download_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._cli.prepare_download_data(payload)

    def run_download_data(self, prepared: dict, log_path: str | None = None) -> dict:
        return self._cli.run_download_data(prepared, log_path=log_path)

    def validate_data(self, pairs: list[str], timeframe: str) -> list[dict[str, Any]]:
        data_dir = os.path.join(BASE_DIR, "user_data", "data")
        results: list[dict[str, Any]] = []

        for pair in pairs:
            pair_file = os.path.join(data_dir, pair.replace("/", "_"), f"{timeframe}.json")
            if os.path.exists(pair_file):
                results.append({"pair": pair, "status": "valid", "message": "Data available"})
            else:
                results.append({"pair": pair, "status": "missing", "message": "No data file found"})

        return results
