import os
import glob
from typing import Optional
from utils.paths import strategy_results_dir, resolve_safe
from utils.json_io import read_json


class ResultsService:
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
        from utils.paths import user_data_results_dir
        base = user_data_results_dir()
        if not os.path.isdir(base):
            return []
        return [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
