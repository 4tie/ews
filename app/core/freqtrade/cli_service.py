from __future__ import annotations

import glob
import json
import logging
import os
import re
import subprocess
from datetime import datetime
from typing import Any

from app.core.freqtrade.commands import build_backtest_command, build_download_command, command_to_string
from app.core.freqtrade.paths import default_freqtrade_config_path, strategy_results_dir
from app.core.freqtrade.settings import get_config_path, get_freqtrade_path, get_freqtrade_runtime_settings, get_user_data_path
from app.core.services.config_service import ConfigService
from app.core.utils.paths import backtest_runs_dir, resolve_safe

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
        "--config",
        "-c",
        "--strategy-path",
    }

    def _settings(self) -> dict[str, Any]:
        return get_freqtrade_runtime_settings(config_svc.get_settings())

    def _freqtrade_path(self) -> str:
        return get_freqtrade_path(self._settings())

    def _user_data_path(self) -> str:
        return get_user_data_path(self._settings())

    def _config_path(self) -> str:
        return get_config_path(self._settings())

    def resolve_backtest_config_path(self, payload: dict[str, Any] | None = None) -> str:
        settings = self._settings()
        configured = (payload or {}).get("config_path") or settings.get("config_path")
        if configured:
            return str(configured)
        return default_freqtrade_config_path(settings.get("user_data_path"))

    def _freqtrade_subprocess_env(self) -> dict[str, str]:
        """Return environment variables for freqtrade subprocess, ensuring FT_FORCE_THREADED_RESOLVER is not set."""
        env = os.environ.copy()
        env.pop("FT_FORCE_THREADED_RESOLVER", None)
        return env

    def _subprocess_creationflags(self, *, isolate_console_signals: bool = False) -> int:
        """Return Windows-safe subprocess flags; no-op on non-Windows platforms."""
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if isolate_console_signals:
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return creationflags

    def _validate_backtest_extra_flags(self, extra_flags: list[str]) -> None:
        conflicting = []
        for token in extra_flags:
            flag_name = token.split("=", 1)[0]
            if flag_name in self._CONTROLLED_BACKTEST_FLAGS:
                conflicting.append(flag_name)

        if conflicting:
            conflict_list = ", ".join(sorted(set(conflicting)))
            raise ValueError(
                f"extra_flags may not override run-scoped flags: {conflict_list}"
            )

    def _backtest_extra_flags(self, payload: dict[str, Any]) -> list[str]:
        extra_flags = list(payload.get("extra_flags", []))
        self._validate_backtest_extra_flags(extra_flags)

        has_cache_flag = any(token.split("=", 1)[0] == "--cache" for token in extra_flags)
        if not has_cache_flag:
            extra_flags.extend(["--cache", "none"])

        return extra_flags

    def _rewrite_first_class_declaration(self, code_snapshot: str, strategy: str) -> str:
        """Ensure the strategy class name matches the `--strategy` value for this run.

        This rewrite is run-scoped only (workspace materialization), never a live file mutation.
        """
        if not isinstance(code_snapshot, str) or not code_snapshot.strip():
            return code_snapshot
        strategy_name = str(strategy or "").strip()
        if not strategy_name:
            return code_snapshot

        pattern = re.compile(r"^(\s*class\s+)([A-Za-z_][A-Za-z0-9_]*)(\s*)(\(|:)", flags=re.MULTILINE)
        match = pattern.search(code_snapshot)
        if not match:
            return code_snapshot

        existing = match.group(2)
        if existing == strategy_name:
            return code_snapshot

        def _replace(m):
            return f"{m.group(1)}{strategy_name}{m.group(3)}{m.group(4)}"

        return pattern.sub(_replace, code_snapshot, count=1)

    def _backtest_artifact_paths(self, strategy: str, run_id: str) -> dict[str, Any]:
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

    def _materialize_version_workspace(
        self,
        payload: dict[str, Any],
        base_config_path: str,
        resolved_artifacts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create run-scoped temporary workspace for backtest execution.
        
        IMPORTANT CONTRACT:
        - Writes ONLY to data/backtest_runs/{run_id}/workspace/ (NEVER to live user_data paths)
        - Each run gets independent isolated copy of strategy code and config
        - Workspace is temporary, implementation detail of this run
        - Engine runs with workspace paths, NOT live paths
        - Does NOT modify user_data/strategies/ or user_data/config/ in any way
        
        This path is NON-INVASIVE to live files. All live writes go through
        external mutation/version management (e.g., mutation_service.accept_version()).
        
        Args:
            payload: Backtest request payload
            base_config_path: Base config path to use
            resolved_artifacts: Pre-resolved artifacts dict with 'code_snapshot' and 'parameters_snapshot'.
                               If None and version_id is present, raises ValueError.
        
        Returns:
            Dict with config_paths, strategy_path, workspace_dir, etc.
        """
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

        if resolved_artifacts is None:
            raise ValueError(
                f"resolved_artifacts required for version_id {version_id}. "
                "Caller must resolve version artifacts externally (e.g., via mutation_service)."
            )

        code_snapshot = resolved_artifacts.get("code_snapshot")
        if not isinstance(code_snapshot, str) or not code_snapshot.strip():
            raise ValueError(f"Version {version_id} does not resolve to a strategy code snapshot")

        code_snapshot = self._rewrite_first_class_declaration(code_snapshot, strategy)

        parameters_snapshot = resolved_artifacts.get("parameters_snapshot")
        if not isinstance(parameters_snapshot, dict):
            parameters_snapshot = {}

        workspace_paths = self._workspace_paths(str(payload.get("run_id") or ""), strategy)
        os.makedirs(workspace_paths["strategies_dir"], exist_ok=True)

        # Mark workspace as in-progress (for error cleanup)
        from pathlib import Path
        import shutil
        workspace_dir_path = Path(workspace_paths["workspace_dir"])
        partial_marker = workspace_dir_path / ".materializing"

        try:
            partial_marker.touch()  # Signal: materialization started

            with open(workspace_paths["strategy_file"], "w", encoding="utf-8") as handle:
                handle.write(code_snapshot)

            config_overlay_path = None
            config_paths = [base_config_path]
            if parameters_snapshot:
                with open(workspace_paths["config_overlay_path"], "w", encoding="utf-8") as handle:
                    json.dump(parameters_snapshot, handle, indent=2)
                config_overlay_path = workspace_paths["config_overlay_path"]
                config_paths.append(config_overlay_path)

            partial_marker.unlink()  # Signal: materialization complete

        except Exception as e:
            # ONLY clean if marker still exists (proving failure mid-process)
            if partial_marker.exists():
                shutil.rmtree(workspace_dir_path, ignore_errors=True)
                logger.info(f"Cleaned partial workspace {workspace_dir_path} after materialization error: {e}")
            raise

        return {
            "config_paths": config_paths,
            "request_config_path": base_config_path,
            "strategy_path": workspace_paths["strategies_dir"],
            "workspace_dir": workspace_paths["workspace_dir"],
            "strategy_file": workspace_paths["strategy_file"],
            "config_overlay_path": config_overlay_path,
        }

    def _backtest_meta_paths(self, strategy: str) -> list[str]:
        result_dir = strategy_results_dir(strategy)
        pattern = os.path.join(result_dir, "backtest-result-*.meta.json")
        return sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    def _zip_path_from_meta(self, meta_path: str) -> str:
        if meta_path.endswith(".meta.json"):
            return meta_path[:-len(".meta.json")] + ".zip"
        return meta_path

    def _read_json_file(self, path: str) -> dict[str, Any]:
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

    def prepare_backtest_run(
        self,
        payload: dict[str, Any],
        resolved_artifacts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Prepare backtest run with optional pre-resolved artifacts.
        
        Args:
            payload: Backtest request payload
            resolved_artifacts: Optional pre-resolved artifacts for version_id.
                               If version_id is present but resolved_artifacts is None,
                               will raise ValueError.
        """
        strategy = payload.get("strategy", "") or "unknown"
        run_id = payload.get("run_id") or datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        extra_flags = self._backtest_extra_flags(payload)
        config_path = self.resolve_backtest_config_path(payload)
        materialized = self._materialize_version_workspace(
            payload,
            config_path,
            resolved_artifacts=resolved_artifacts,
        )

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

    def build_backtest_command_preview(self, payload: dict[str, Any]) -> str:
        """Return the shell command string that would be executed."""
        prepared = self.prepare_backtest_run(payload)
        return prepared["command"]

    def run_backtest(self, payload: dict[str, Any], prepared: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run freqtrade backtesting subprocess."""
        prepared = prepared or self.prepare_backtest_run(payload)
        command = prepared["command"]
        log_path = prepared["log_file"]
        env = self._freqtrade_subprocess_env()
        creationflags = self._subprocess_creationflags(isolate_console_signals=True)

        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"$ {command}\n\n")
            log_file.flush()
            process = subprocess.Popen(
                prepared["cmd"],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=creationflags,
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

    def _should_prepend(self, pairs: list[str], timeframes: list[str]) -> bool:
        """Check if any data files exist - if so, use --prepend to extend existing data."""
        for pair in pairs:
            for tf in timeframes:
                if self._data_file_exists(pair, tf):
                    return True
        return False

    def prepare_download_data(self, payload: dict[str, Any]) -> dict[str, Any]:
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

    def run_download_data(self, prepared: dict[str, Any], log_path: str | None = None) -> dict[str, Any]:
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

    def download_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run freqtrade download-data (legacy helper)."""
        prepared = self.prepare_download_data(payload)
        return self.run_download_data(prepared)


FreqtradeCLIService = FreqtradeCliService


__all__ = ["FreqtradeCliService", "FreqtradeCLIService"]
