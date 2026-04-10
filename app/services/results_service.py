import glob
import json
import os
import zipfile
from typing import Optional

from app.models.backtest_models import BacktestRunRecord
from app.utils.json_io import read_json, write_json
from app.utils.paths import strategy_results_dir, user_data_results_dir


class ResultsService:
    def _run_result_paths(self, strategy: str, run_id: str) -> dict:
        base = strategy_results_dir(strategy)
        os.makedirs(base, exist_ok=True)
        return {
            "result_path": os.path.join(base, f"{run_id}.result.json"),
            "summary_path": os.path.join(base, f"{run_id}.summary.json"),
            "latest_summary_path": os.path.join(base, "latest.summary.json"),
        }

    def _load_raw_result_payload(self, raw_result_path: str) -> dict:
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

    def _extract_profit_pct(self, strategy_result: dict) -> Optional[float]:
        for row in strategy_result.get("results_per_pair", []):
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

    def ingest_backtest_run(self, run_record: BacktestRunRecord) -> dict:
        raw_payload = self._load_raw_result_payload(run_record.raw_result_path or "")
        strategies = raw_payload.get("strategy") or {}
        strategy_result = strategies.get(run_record.strategy)
        if not isinstance(strategy_result, dict):
            raise KeyError(
                f"strategy {run_record.strategy} not found in raw artifact {run_record.raw_result_path}"
            )

        paths = self._run_result_paths(run_record.strategy, run_record.run_id)
        summary_payload = {run_record.strategy: strategy_result}
        if raw_payload.get("strategy_comparison") is not None:
            summary_payload["strategy_comparison"] = raw_payload["strategy_comparison"]

        write_json(paths["result_path"], raw_payload)
        write_json(paths["summary_path"], summary_payload)
        write_json(paths["latest_summary_path"], summary_payload)

        return {
            "raw_result_path": run_record.raw_result_path,
            "result_path": paths["result_path"],
            "summary_path": paths["summary_path"],
            "profit_pct": self._extract_profit_pct(strategy_result),
        }

    def load_latest_summary(self, strategy: str) -> Optional[dict]:
        """Load the latest backtest summary JSON for a strategy."""
        base = strategy_results_dir(strategy)
        latest_path = os.path.join(base, "latest.summary.json")
        if os.path.isfile(latest_path):
            return read_json(latest_path)

        # Fall back to the most recent timestamped summary
        pattern = os.path.join(base, "*.summary.json")
        files = sorted(glob.glob(pattern), reverse=True)
        if files:
            return read_json(files[0])

        return None

    def load_trades(self, strategy: str) -> list:
        """Extract trades array from the latest summary."""
        summary = self.load_latest_summary(strategy)
        if not summary:
            return []
        # Freqtrade summary format: strategy key contains trades
        for key, val in summary.items():
            if isinstance(val, dict) and "trades" in val:
                return val["trades"]
        return summary.get("trades", [])

    def load_results_per_pair(self, strategy: str) -> list:
        """Extract per-pair results from the latest summary."""
        summary = self.load_latest_summary(strategy)
        if not summary:
            return []
        for key, val in summary.items():
            if isinstance(val, dict) and "results_per_pair" in val:
                return val["results_per_pair"]
        return summary.get("results_per_pair", [])

    def list_summaries(self, strategy: str) -> list[str]:
        """List all summary files for a strategy."""
        base = strategy_results_dir(strategy)
        if not os.path.isdir(base):
            return []
        return sorted(
            [f for f in os.listdir(base) if f.endswith(".summary.json")],
            reverse=True,
        )

    def list_strategies_with_results(self) -> list[str]:
        """Return all strategies that have at least one result directory."""
        base = user_data_results_dir()
        if not os.path.isdir(base):
            return []
        return [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
