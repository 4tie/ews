import logging
import os
import subprocess
from datetime import datetime

from app.services.config_service import ConfigService
from app.utils.command_builder import build_backtest_command, build_download_command, command_to_string
from app.utils.paths import BASE_DIR, strategy_results_dir

config_svc = ConfigService()
logger = logging.getLogger(__name__)


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

    def _freqtrade_subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["FT_FORCE_THREADED_RESOLVER"] = "1"

        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = BASE_DIR if not existing else BASE_DIR + os.pathsep + existing
        return env


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
            dry_run_wallet=payload.get("dry_run_wallet"),
            max_open_trades=payload.get("max_open_trades"),
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
        env = self._freqtrade_subprocess_env()

        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"$ {command}\n\n")
            log_file.flush()
            process = subprocess.Popen(
                prepared["cmd"],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )

        return {
            "command": command,
            "status": "running",
            "pid": process.pid,
            "log_file": log_path,
            "raw_result_path": prepared["raw_result_path"],
            "process": process,
        }

    def _data_file_exists(self, pair: str, timeframe: str) -> bool:
        """Check if a data file exists for the given pair and timeframe."""
        user_data_path = self._user_data_path()
        if not user_data_path:
            return False
        pair_dir = pair.replace("/", "_")
        data_file = os.path.join(user_data_path, "data", pair_dir, f"{timeframe}.json")
        return os.path.exists(data_file)

    def _should_prepend(self, pairs: list, timeframes: list) -> bool:
        """Check if any data files exist - if so, use --prepend to extend existing data."""
        for pair in pairs:
            for tf in timeframes:
                if self._data_file_exists(pair, tf):
                    return True
        return False

    def prepare_download_data(self, payload: dict) -> dict:
        """Build freqtrade download-data command and inferred flags."""
        pairs = payload.get("pairs", [])
        timeframe = payload.get("timeframe") or "5m"
        timeframes = [timeframe]
        timerange = payload.get("timerange")

        prepend = self._should_prepend(pairs, timeframes) if pairs else False

        cmd = build_download_command(
            freqtrade_path=self._freqtrade_path(),
            config_path=self._config_path(),
            pairs=pairs,
            timeframes=timeframes,
            timerange=timerange,
            prepend=prepend,
        )
        return {
            "cmd": cmd,
            "command": command_to_string(cmd),
            "prepend": prepend,
        }

    def run_download_data(self, prepared: dict, log_path: str | None = None) -> dict:
        """Run freqtrade download-data subprocess."""
        cmd = prepared.get("cmd") or []
        command = prepared.get("command") or command_to_string(cmd)
        prepend = prepared.get("prepend", False)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = self._freqtrade_subprocess_env()

        try:
            if log_path:
                with open(log_path, "w", encoding="utf-8") as log_file:
                    log_file.write(f"$ {command}\n\n")
                    log_file.flush()
                    process = subprocess.Popen(
                        cmd,
                        stdin=subprocess.DEVNULL,
                        stdout=log_file,
                        stderr=subprocess.STDOUT,
                        creationflags=creationflags,
                        env=env,
                    )
            else:
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                    env=env,
                )
        except Exception:
            logger.exception("download-data subprocess failed: %s", command)
            raise

        result = {
            "command": command,
            "status": "running",
            "pid": process.pid,
            "prepend": prepend,
            "process": process,
        }
        if log_path:
            result["log_file"] = log_path
        return result

    def download_data(self, payload: dict) -> dict:
        """Run freqtrade download-data (legacy helper)."""
        prepared = self.prepare_download_data(payload)
        return self.run_download_data(prepared)


