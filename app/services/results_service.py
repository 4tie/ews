import glob
import os
from typing import Optional

from app.engines.resolver import result_parser_from_id
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

    def ingest_backtest_run(self, run_record: BacktestRunRecord) -> dict:
        parser = result_parser_from_id(getattr(run_record, "engine", None))
        parsed = parser.parse_backtest_run(run_record)

        paths = self._run_result_paths(run_record.strategy, run_record.run_id)

        normalized_result = {
            "run_id": run_record.run_id,
            "strategy": run_record.strategy,
            "profit_total_pct": parsed.profit_pct,
            "result": parsed.strategy_result,
        }
        if parsed.strategy_comparison is not None:
            normalized_result["strategy_comparison"] = parsed.strategy_comparison

        summary_payload = {run_record.strategy: parsed.strategy_result}
        if parsed.strategy_comparison is not None:
            summary_payload["strategy_comparison"] = parsed.strategy_comparison

        write_json(paths["result_path"], normalized_result)
        write_json(paths["summary_path"], summary_payload)
        write_json(paths["latest_summary_path"], summary_payload)

        return {
            "raw_result_path": run_record.raw_result_path,
            "result_path": paths["result_path"],
            "summary_path": paths["summary_path"],
            "profit_pct": parsed.profit_pct,
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
