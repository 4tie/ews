import glob
import json
import logging
import os
import subprocess
from datetime import datetime
from typing import Any

from app.services.config_service import ConfigService
from app.services.mutation_service import mutation_service
from app.utils.command_builder import build_backtest_command, build_download_command, command_to_string
from app.utils.paths import BASE_DIR, backtest_runs_dir, default_freqtrade_config_path, resolve_safe, strategy_results_dir

config_svc = ConfigService()
logger = logging.getLogger(__name__)


class FreqtradeCliService:
    _CONTROLLED_BACKTEST_FLAGS = {
        "--export",
        "--export-filename",
        "--backtest-filename",
        "--export-directory",
        "--backtest-directory",
        "--notes",
    }

    def _freqtrade_path(self) -> str:
        return config_svc.get_settings().get("freqtrade_path", "")

    def _user_data_path(self) -> str:
        return config_svc.get_settings().get("user_data_path", "")

    def _config_path(self) -> str:
        return config_svc.get_settings().get("config_path", "")

    def _settings(self) -> dict[str, Any]:
        return config_svc.get_settings()

    def resolve_backtest_config_path(self, payload: dict[str, Any] | None = None) -> str:
        settings = self._settings()
        configured = (payload or {}).get("config_path") or settings.get("config_path")
        if configured:
            return str(configured)
        return default_freqtrade_config_path(settings.get("user_data_path"))

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

    def _backtest_extra_flags(self, payload: dict[str, Any]) -> list[str]:
        extra_flags = list(payload.get("extra_flags", []))
        self._validate_backtest_extra_flags(extra_flags)

        has_cache_flag = any(token.split("=", 1)[0] == "--cache" for token in extra_flags)
        if not has_cache_flag:
            extra_flags.extend(["--cache", "none"])

        return extra_flags

    def _backtest_artifact_paths(self, strategy: str, run_id: str) -> dict:
        result_dir = strategy_results_dir(strategy)
        os.makedirs(result_dir, exist_ok=True)
        return {
            "log_file": os.path.join(result_dir, f"{run_id}.backtest.log"),
            "raw_result_dir": result_dir,
            "raw_result_path": None,
        }

    def _workspace_paths(self, run_id: str, strategy: str) -> dict[str, str]:
        workspace_dir = resolve_safe(backtest_runs_dir(), run_id, "workspace")
        strategies_dir = os.path.join(workspace_dir, "strategies")
        return {
            "workspace_dir": workspace_dir,
            "strategies_dir": strategies_dir,
            "strategy_file": os.path.join(strategies_dir, f"{strategy}.py"),
            "config_overlay_path": os.path.join(workspace_dir, "config.version.json"),
        }

    def _materialize_version_workspace(self, payload: dict[str, Any], base_config_path: str) -> dict[str, Any]:
        version_id = payload.get("version_id")
        strategy = payload.get("strategy", "") or "unknown"
        if not version_id:
            return {
                "config_paths": [base_config_path],
                "request_config_path": base_config_path,
                "strategy_path": None,
                "workspace_dir": None,
                "strategy_file": None,
                "config_overlay_path": None,
            }

        version = mutation_service.get_version_by_id(str(version_id))
        if version is None:
            raise ValueError(f"Version {version_id} not found")
        if version.strategy_name != strategy:
            raise ValueError(
                f"Version {version_id} belongs to {version.strategy_name}, not {strategy}"
            )

        resolved = mutation_service.resolve_effective_artifacts(str(version_id))
        code_snapshot = resolved.get("code_snapshot")
        if not isinstance(code_snapshot, str) or not code_snapshot.strip():
            raise ValueError(f"Version {version_id} does not resolve to a strategy code snapshot")

        parameters_snapshot = resolved.get("parameters_snapshot")
        if not isinstance(parameters_snapshot, dict):
            parameters_snapshot = {}

        workspace_paths = self._workspace_paths(str(payload.get("run_id") or ""), strategy)
        os.makedirs(workspace_paths["strategies_dir"], exist_ok=True)

        with open(workspace_paths["strategy_file"], "w", encoding="utf-8") as handle:
            handle.write(code_snapshot)
        with open(workspace_paths["config_overlay_path"], "w", encoding="utf-8") as handle:
            json.dump(parameters_snapshot, handle, indent=2)

        return {
            "config_paths": [base_config_path, workspace_paths["config_overlay_path"]],
            "request_config_path": base_config_path,
            "strategy_path": workspace_paths["strategies_dir"],
            "workspace_dir": workspace_paths["workspace_dir"],
            "strategy_file": workspace_paths["strategy_file"],
            "config_overlay_path": workspace_paths["config_overlay_path"],
        }

    def _backtest_meta_paths(self, strategy: str) -> list[str]:
        result_dir = strategy_results_dir(strategy)
        pattern = os.path.join(result_dir, "backtest-result-*.meta.json")
        return sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    def _zip_path_from_meta(self, meta_path: str) -> str:
        if meta_path.endswith(".meta.json"):
            return meta_path[: -len(".meta.json")] + ".zip"
        return meta_path

    def _read_json_file(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def resolve_backtest_raw_result(
        self,
        strategy: str,
        run_id: str,
        created_at: str | None = None,
    ) -> str | None:
        started_ts = None
        if created_at:
            try:
                started_ts = datetime.fromisoformat(created_at).timestamp()
            except ValueError:
                started_ts = None

        for meta_path in self._backtest_meta_paths(strategy):
            if started_ts is not None and os.path.getmtime(meta_path) + 1 < started_ts:
                continue

            try:
                meta = self._read_json_file(meta_path)
            except (OSError, json.JSONDecodeError):
                continue

            strategy_meta = meta.get(strategy)
            if not isinstance(strategy_meta, dict):
                continue
            if strategy_meta.get("notes") != run_id:
                continue

            zip_path = self._zip_path_from_meta(meta_path)
            if os.path.isfile(zip_path):
                return zip_path

        result_dir = strategy_results_dir(strategy)
        last_result_path = os.path.join(result_dir, ".last_result.json")
        if os.path.isfile(last_result_path):
            try:
                last_result = self._read_json_file(last_result_path)
            except (OSError, json.JSONDecodeError):
                last_result = {}

            latest_backtest = last_result.get("latest_backtest")
            if latest_backtest:
                zip_path = os.path.join(result_dir, latest_backtest)
                if os.path.isfile(zip_path):
                    if started_ts is None or os.path.getmtime(zip_path) + 1 >= started_ts:
                        return zip_path

        return None

    def prepare_backtest_run(self, payload: dict) -> dict:
        strategy = payload.get("strategy", "") or "unknown"
        run_id = payload.get("run_id") or datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        extra_flags = self._backtest_extra_flags(payload)
        config_path = self.resolve_backtest_config_path(payload)
        materialized = self._materialize_version_workspace(payload, config_path)

        artifacts = self._backtest_artifact_paths(strategy, run_id)
        cmd = build_backtest_command(
            freqtrade_path=self._freqtrade_path(),
            strategy=strategy,
            config_paths=materialized["config_paths"],
            strategy_path=materialized.get("strategy_path"),
            timerange=payload.get("timerange"),
            pairs=payload.get("pairs"),
            timeframe=payload.get("timeframe"),
            dry_run_wallet=payload.get("dry_run_wallet"),
            max_open_trades=payload.get("max_open_trades"),
            export_mode="trades",
            backtest_directory=artifacts["raw_result_dir"],
            notes=run_id,
            extra_flags=extra_flags,
        )
        return {
            "run_id": run_id,
            "cmd": cmd,
            "command": command_to_string(cmd),
            "config_path": config_path,
            **artifacts,
            **materialized,
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
            "raw_result_path": prepared.get("raw_result_path"),
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

        prepend = payload.get("prepend")
        if prepend is None:
            prepend = True

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

