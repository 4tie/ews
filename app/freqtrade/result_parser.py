from __future__ import annotations

import json
import os
import zipfile
from typing import Any

from app.engines.base import ParsedBacktestResult, ResultParser
from app.models.backtest_models import BacktestRunRecord


def _load_raw_result_payload(raw_result_path: str) -> dict[str, Any]:
    if not raw_result_path or not os.path.isfile(raw_result_path):
        raise FileNotFoundError(f"raw result artifact not found: {raw_result_path}")

    with zipfile.ZipFile(raw_result_path, "r") as archive:
        entries = [
            name
            for name in archive.namelist()
            if name.endswith(".json") and not name.endswith("_config.json")
        ]
        if not entries:
            raise ValueError(f"no result json found in raw artifact: {raw_result_path}")

        expected_entry = f"{os.path.splitext(os.path.basename(raw_result_path))[0]}.json"
        if expected_entry in entries:
            result_entry = expected_entry
        elif len(entries) == 1:
            result_entry = entries[0]
        else:
            raise ValueError(
                f"ambiguous result json entries in raw artifact {raw_result_path}: {entries}"
            )

        with archive.open(result_entry, "r") as handle:
            return json.load(handle)


def _extract_profit_pct(strategy_result: dict[str, Any]) -> float | None:
    for row in strategy_result.get("results_per_pair", []) or []:
        if not isinstance(row, dict):
            continue
        key = row.get("key") or row.get("pair")
        if key == "TOTAL":
            profit_total_pct = row.get("profit_total_pct")
            if profit_total_pct is not None:
                return float(profit_total_pct)

    profit_total_pct = strategy_result.get("profit_total_pct")
    if profit_total_pct is not None:
        return float(profit_total_pct)

    profit_total_ratio = strategy_result.get("profit_total")
    if profit_total_ratio is not None:
        return float(profit_total_ratio) * 100.0

    return None


class FreqtradeResultParser(ResultParser):
    def parse_backtest_run(self, run_record: BacktestRunRecord) -> ParsedBacktestResult:
        raw_payload = _load_raw_result_payload(run_record.raw_result_path or "")
        strategies = raw_payload.get("strategy") or {}
        strategy_result = strategies.get(run_record.strategy)
        if not isinstance(strategy_result, dict):
            raise KeyError(
                f"strategy {run_record.strategy} not found in raw artifact {run_record.raw_result_path}"
            )

        profit_pct = _extract_profit_pct(strategy_result)
        strategy_comparison = raw_payload.get("strategy_comparison")

        return ParsedBacktestResult(
            strategy_result=strategy_result,
            profit_pct=profit_pct,
            strategy_comparison=strategy_comparison,
        )
