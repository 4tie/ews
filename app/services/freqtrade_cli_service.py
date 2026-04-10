import os
import subprocess
from datetime import datetime

from app.services.config_service import ConfigService
from app.utils.command_builder import build_backtest_command, build_download_command, command_to_string
from app.utils.paths import strategy_results_dir

config_svc = ConfigService()


class FreqtradeCliService:
    def _freqtrade_path(self) -> str:
        return config_svc.get_settings().get("freqtrade_path", "")

    def _user_data_path(self) -> str:
        return config_svc.get_settings().get("user_data_path", "")

    def _config_path(self) -> str:
        return config_svc.get_settings().get("config_path", "")

    def list_strategies(self) -> list[str]:
        """List strategy files from the freqtrade user_data/strategies directory."""
        user_data_path = self._user_data_path()
        strat_dir = os.path.join(user_data_path, "strategies") if user_data_path else ""
        if not os.path.isdir(strat_dir):
            ft_path = self._freqtrade_path()
            strat_dir = os.path.join(ft_path, "user_data", "strategies") if ft_path else ""
            if not os.path.isdir(strat_dir):
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
        command = command_to_string(cmd)
        strategy = payload.get("strategy", "") or "unknown"
        run_id = payload.get("run_id") or datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        log_dir = strategy_results_dir(strategy)
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{run_id}.backtest.log")

        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"$ {command}\n\n")
            log_file.flush()
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

        return {
            "command": command,
            "status": "running",
            "pid": process.pid,
            "log_file": log_path,
        }

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
