import os
import subprocess
from datetime import datetime

from app.services.config_service import ConfigService
from app.utils.command_builder import build_backtest_command, build_download_command, command_to_string
from app.utils.paths import strategy_results_dir

config_svc = ConfigService()


class FreqtradeCliService:
    _CONTROLLED_BACKTEST_FLAGS = {
        "--export",
        "--export-filename",
        "--backtest-filename",
        "--export-directory",
        "--backtest-directory",
    }

    def _freqtrade_path(self) -> str:
        return config_svc.get_settings().get("freqtrade_path", "")

    def _user_data_path(self) -> str:
        return config_svc.get_settings().get("user_data_path", "")

    def _config_path(self) -> str:
        return config_svc.get_settings().get("config_path", "")

    def _validate_backtest_extra_flags(self, extra_flags: list[str]) -> None:
        conflicting = []
        for token in extra_flags:
            flag_name = token.split("=", 1)[0]
            if flag_name in self._CONTROLLED_BACKTEST_FLAGS:
                conflicting.append(flag_name)

        if conflicting:
            conflict_list = ", ".join(sorted(set(conflicting)))
            raise ValueError(
                f"extra_flags may not override run-scoped export settings: {conflict_list}"
            )

    def _backtest_artifact_paths(self, strategy: str, run_id: str) -> dict:
        result_dir = strategy_results_dir(strategy)
        os.makedirs(result_dir, exist_ok=True)
        return {
            "log_file": os.path.join(result_dir, f"{run_id}.backtest.log"),
            "raw_result_path": os.path.join(result_dir, f"{run_id}.backtest.zip"),
        }

    def prepare_backtest_run(self, payload: dict) -> dict:
        strategy = payload.get("strategy", "") or "unknown"
        run_id = payload.get("run_id") or datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        extra_flags = list(payload.get("extra_flags", []))
        self._validate_backtest_extra_flags(extra_flags)

        artifacts = self._backtest_artifact_paths(strategy, run_id)
        cmd = build_backtest_command(
            freqtrade_path=self._freqtrade_path(),
            strategy=strategy,
            config_path=self._config_path(),
            timerange=payload.get("timerange"),
            pairs=payload.get("pairs"),
            timeframe=payload.get("timeframe"),
            extra_flags=[
                "--export",
                "trades",
                "--export-filename",
                artifacts["raw_result_path"],
                *extra_flags,
            ],
        )
        return {
            "run_id": run_id,
            "cmd": cmd,
            "command": command_to_string(cmd),
            **artifacts,
        }

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
        prepared = self.prepare_backtest_run(payload)
        return prepared["command"]

    def run_backtest(self, payload: dict, prepared: dict | None = None) -> dict:
        """Run freqtrade backtesting subprocess."""
        prepared = prepared or self.prepare_backtest_run(payload)
        command = prepared["command"]
        log_path = prepared["log_file"]

        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"$ {command}\n\n")
            log_file.flush()
            process = subprocess.Popen(
                prepared["cmd"],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )

        return {
            "command": command,
            "status": "running",
            "pid": process.pid,
            "log_file": log_path,
            "raw_result_path": prepared["raw_result_path"],
            "process": process,
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
