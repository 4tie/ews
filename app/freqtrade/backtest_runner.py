"""
Backtest execution and launch orchestration.

Handles strategy loading, version resolution, and backtest subprocess launch.
"""
import json
import os
import uuid
from typing import Any

from fastapi import HTTPException

from app.engines.base import EngineFeatureNotSupported
from app.engines.resolver import resolve_engine
from app.freqtrade.backtest_process import _save_run_record, _start_backtest_watcher
from app.freqtrade.backtest_stream import _derive_backtest_progress
from app.freqtrade.paths import live_strategy_file, strategy_config_file
from app.freqtrade.settings import SUPPORTED_EXCHANGES, SUPPORTED_TIMEFRAMES
from app.models.backtest_models import BacktestRunRecord, BacktestRunRequest, BacktestRunStatus
from app.models.optimizer_models import ChangeType, MutationRequest
from app.services.config_service import ConfigService
from app.services.mutation_service import mutation_service
from app.utils.datetime_utils import now_iso

config_svc = ConfigService()


def _load_json_object(path: str, label: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"{label} could not be loaded: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail=f"{label} must be a JSON object: {path}")
    return payload


def load_live_strategy_code(
    strategy_name: str,
    user_data_path: str | None = None,
    *,
    strict: bool = False,
) -> str | None:
    try:
        strategy_path = live_strategy_file(strategy_name, user_data_path)
    except ValueError as exc:
        if strict:
            raise HTTPException(status_code=400, detail=f"Live strategy path could not be resolved: {exc}") from exc
        return None

    if not os.path.isfile(strategy_path):
        if strict:
            raise HTTPException(status_code=400, detail=f"Live strategy file not found for {strategy_name}")
        return None

    try:
        with open(strategy_path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        if strict:
            raise HTTPException(status_code=400, detail=f"Live strategy file could not be loaded: {exc}") from exc
        return None


def load_live_strategy_parameters(
    strategy_name: str,
    user_data_path: str | None = None,
    *,
    strict: bool = False,
) -> dict[str, Any] | None:
    try:
        config_path = strategy_config_file(strategy_name, user_data_path)
    except ValueError as exc:
        if strict:
            raise HTTPException(status_code=400, detail=f"Strategy config path could not be resolved: {exc}") from exc
        return None

    if not os.path.isfile(config_path):
        return None

    try:
        payload = _load_json_object(config_path, f"Strategy config snapshot for {strategy_name}")
    except HTTPException:
        if strict:
            raise
        return None

    return payload


def _bootstrap_initial_version(strategy_name: str):
    settings = config_svc.get_settings()
    user_data_path = settings.get("user_data_path")

    try:
        strategy_path = live_strategy_file(strategy_name, user_data_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Initial bootstrap failed: {exc}") from exc

    code_snapshot = load_live_strategy_code(strategy_name, user_data_path, strict=True)
    parameters_snapshot = load_live_strategy_parameters(strategy_name, user_data_path, strict=True)

    mutation_result = mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.INITIAL,
            summary="Initial live strategy bootstrap",
            created_by="system",
            code=code_snapshot,
            parameters=parameters_snapshot,
            source_ref=strategy_path,
        )
    )
    accept_result = mutation_service.accept_version(
        mutation_result.version_id,
        notes="Accepted initial live strategy bootstrap",
    )
    if accept_result.status == "error":
        raise HTTPException(status_code=500, detail=accept_result.message)

    version = mutation_service.get_version_by_id(mutation_result.version_id)
    if version is None:
        raise HTTPException(status_code=500, detail="Initial bootstrap version could not be loaded after creation")
    return version


def _resolve_version_for_launch(payload: BacktestRunRequest):
    if payload.version_id:
        version = mutation_service.get_version_by_id(payload.version_id)
        if not version:
            raise HTTPException(status_code=404, detail=f"Version {payload.version_id} not found")
        if version.strategy_name != payload.strategy:
            raise HTTPException(
                status_code=400,
                detail=f"Version {payload.version_id} belongs to {version.strategy_name}, not {payload.strategy}",
            )
        return version

    active_version = mutation_service.get_active_version(payload.strategy)
    if active_version is not None:
        return active_version

    return _bootstrap_initial_version(payload.strategy)


def _build_request_snapshot(launch_payload: dict, engine_id: str) -> dict:
    return {
        "strategy": launch_payload.get("strategy"),
        "timeframe": launch_payload.get("timeframe"),
        "timerange": launch_payload.get("timerange"),
        "pairs": list(launch_payload.get("pairs") or []),
        "exchange": launch_payload.get("exchange"),
        "max_open_trades": launch_payload.get("max_open_trades"),
        "dry_run_wallet": launch_payload.get("dry_run_wallet"),
        "extra_flags": list(launch_payload.get("extra_flags") or []),
        "trigger_source": launch_payload.get("trigger_source"),
        "config_path": launch_payload.get("config_path"),
        "engine": engine_id,
    }


def _resolve_engine():
    settings = config_svc.get_settings()
    try:
        return resolve_engine(settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def get_options():
    """Return available strategies, timeframes, and exchanges."""
    engine = _resolve_engine()
    try:
        strategies = engine.list_strategies()
    except EngineFeatureNotSupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return {
        "strategies": strategies,
        "timeframes": SUPPORTED_TIMEFRAMES,
        "exchanges": SUPPORTED_EXCHANGES,
    }


async def run_backtest(payload: BacktestRunRequest):
    """Trigger a backtest subprocess using the selected engine."""
    version = _resolve_version_for_launch(payload)
    engine = _resolve_engine()

    run_id = f"bt-{uuid.uuid4().hex[:8]}"
    payload_data = payload.model_dump(mode="json")
    payload_data["version_id"] = version.version_id
    launch_payload = {**payload_data, "run_id": run_id}

    try:
        prepared = engine.prepare_backtest_run(launch_payload)
    except EngineFeatureNotSupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    launch_payload["config_path"] = prepared.get("request_config_path") or prepared.get("config_path") or launch_payload.get("config_path")
    request_snapshot = _build_request_snapshot(launch_payload, engine.engine_id)

    created_at = now_iso()
    run_record = BacktestRunRecord(
        run_id=run_id,
        engine=engine.engine_id,
        strategy=payload.strategy,
        version_id=version.version_id,
        request_snapshot=request_snapshot,
        request_snapshot_schema_version=1,
        trigger_source=payload.trigger_source,
        created_at=created_at,
        updated_at=created_at,
        completed_at=None,
        stop_requested_at=None,
        status=BacktestRunStatus.QUEUED,
        command=prepared["command"],
        artifact_path=None,
        raw_result_path=prepared["raw_result_path"],
        result_path=None,
        summary_path=None,
        exit_code=None,
        pid=None,
        error=None,
    )
    _save_run_record(run_record)
    mutation_service.link_backtest(version.version_id, run_id, None)

    try:
        result = engine.run_backtest(launch_payload, prepared=prepared)
    except Exception as exc:
        run_record.artifact_path = None
        run_record.pid = None
        run_record.error = f"launch_failed: {exc}"
        run_record.completed_at = now_iso()
        run_record.updated_at = run_record.completed_at
        run_record.status = BacktestRunStatus.FAILED
        _save_run_record(run_record)
        return {
            "status": run_record.status.value,
            "run_id": run_id,
            "command": run_record.command,
            "version_id": run_record.version_id,
            "trigger_source": run_record.trigger_source.value,
            "artifact_path": run_record.artifact_path,
            "error": run_record.error,
            "progress": _derive_backtest_progress(run_record),
        }

    run_record.status = BacktestRunStatus.RUNNING
    run_record.updated_at = now_iso()
    run_record.command = result.get("command", run_record.command)
    run_record.artifact_path = result.get("run_record_log_path") or result.get("log_file")
    run_record.raw_result_path = result.get("raw_result_path", run_record.raw_result_path)
    run_record.pid = result.get("pid")
    run_record.error = None
    _save_run_record(run_record)

    process = result.get("process")
    if process is not None:
        _start_backtest_watcher(run_id, process)

    return {
        "status": run_record.status.value,
        "run_id": run_id,
        "command": run_record.command,
        "version_id": run_record.version_id,
        "trigger_source": run_record.trigger_source.value,
        "artifact_path": run_record.artifact_path,
        "progress": _derive_backtest_progress(run_record),
    }
