import subprocess
import os
from utils.paths import strategy_results_dir
from utils.command_builder import command_to_string, build_backtest_command, build_download_command
from services.config_service import ConfigService

config_svc = ConfigService()


class FreqtradeCliService:
    def _freqtrade_path(self) -> str:
        return config_svc.get_settings().get("freqtrade_path", "")

    def _config_path(self) -> str:
        return config_svc.get_settings().get("config_path", "")

    def list_strategies(self) -> list[str]:
        """List strategy files from the freqtrade user_data/strategies directory."""
        ft_path = self._freqtrade_path()
        strat_dir = os.path.join(ft_path, "user_data", "strategies") if ft_path else ""
        if not os.path.isdir(strat_dir):
            # TODO: wire to real freqtrade path once configured in settings
            return []
        return [f[:-3] for f in os.listdir(strat_dir) if f.endswith(".py") and not f.startswith("_")]

    def build_backtest_command_preview(self, payload: dict) -> str:
        """Return the shell command string that would be executed."""
        cmd = build_backtest_command(
            freqtrade_path=self._freqtrade_path(),
            strategy=payload.get("strategy", ""),
            config_path=self._config_path(),
            timerange=payload.get("timerange"),
            pairs=payload.get("pairs"),
            timeframe=payload.get("timeframe"),
            extra_flags=payload.get("extra_flags", []),
        )
        return command_to_string(cmd)

    def run_backtest(self, payload: dict) -> dict:
        """Run freqtrade backtesting subprocess."""
        cmd = build_backtest_command(
            freqtrade_path=self._freqtrade_path(),
            strategy=payload.get("strategy", ""),
            config_path=self._config_path(),
            timerange=payload.get("timerange"),
            pairs=payload.get("pairs"),
            timeframe=payload.get("timeframe"),
            extra_flags=payload.get("extra_flags", []),
        )
        # TODO: run as async subprocess, stream output to log file
        return {"command": command_to_string(cmd), "status": "pending"}

    def download_data(self, payload: dict) -> dict:
        """Run freqtrade download-data."""
        cmd = build_download_command(
            freqtrade_path=self._freqtrade_path(),
            config_path=self._config_path(),
            pairs=payload.get("pairs", []),
            timeframes=[payload.get("timeframe", "5m")],
            timerange=payload.get("timerange"),
        )
        # TODO: run as async subprocess
        return {"command": command_to_string(cmd), "status": "pending"}
