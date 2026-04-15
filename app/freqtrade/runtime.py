"""
Backtest runtime orchestration - compatibility facade.

This module re-exports backtest-related functions from decomposed submodules
while maintaining backward compatibility with existing imports.

Backtest-specific logic has been split into:
- backtest_process.py: Run lifecycle, process monitoring, watcher registry
- backtest_runner.py: Strategy loading, version resolution, launch
- backtest_stream.py: Log streaming, progress tracking
- backtest_results.py: Results orchestration and retrieval
- backtest_diagnosis.py: Diagnosis and AI analysis
- proposal_service.py: Proposal candidate creation

Non-backtest functions (download_data, config CRUD, validate_data) remain here.
"""
import json
import os
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.freqtrade.backtest_diagnosis import (
    _default_ai_payload,
    _derive_diagnosis_status,
    _resolve_linked_version_for_run,
    get_backtest_run_diagnosis,
)
from app.freqtrade.backtest_process import (
    _is_terminal_status,
    _load_run_record,
    _reconcile_stale_backtest_run,
    _start_backtest_watcher,
    _watch_backtest_process,
    stop_backtest_run,
)
from app.freqtrade.backtest_results import (
    _summarize_run_record,
    compare_backtest_runs,
    get_backtest_run,
    get_summary,
    get_trades,
    list_backtest_runs,
)
from app.freqtrade.backtest_runner import (
    get_options,
    load_live_strategy_code,
    load_live_strategy_parameters,
    run_backtest,
)
from app.freqtrade.backtest_stream import stream_backtest_logs
from app.freqtrade.paths import user_data_results_dir
from app.models.backtest_models import ConfigSaveRequest
from app.services.config_service import ConfigService
from app.services.persistence_service import PersistenceService
from app.services.results.strategy_intelligence_service import analyze_run_diagnosis_overlay
from app.services.results_service import ResultsService
from app.services.validation_service import ValidationService
from app.utils.datetime_utils import now_iso
from app.utils.paths import download_runs_dir

config_svc = ConfigService()
persistence = PersistenceService()
validation_svc = ValidationService()
results_svc = ResultsService()

# Lazy import to avoid circular dependency
create_proposal_candidate_from_diagnosis = None


def _get_create_proposal_candidate_fn():
    global create_proposal_candidate_from_diagnosis
    if create_proposal_candidate_from_diagnosis is None:
        try:
            from app.services.results.strategy_intelligence_apply_service import (
                create_proposal_candidate_from_diagnosis as _fn,
            )
            create_proposal_candidate_from_diagnosis = _fn
        except ImportError:
            pass
    return create_proposal_candidate_from_diagnosis


async def create_backtest_run_proposal_candidate(run_id: str, payload: Any):
    """Proposal candidate creation - delegates to proposal_service."""
    from app.freqtrade.proposal_service import create_backtest_run_proposal_candidate as _create
    return await _create(run_id, payload)


_TERMINAL_DOWNLOAD_STATUSES = {
    "completed",
    "failed",
}
_download_watcher_lock = None
_active_download_watchers: set[str] = set()


def _is_terminal_download_status(status: str | None) -> bool:
    return str(status) in _TERMINAL_DOWNLOAD_STATUSES


def _load_download_record(download_id: str) -> dict:
    return persistence.load_download_run(download_id)


def _save_download_record(download_id: str, data: dict) -> None:
    persistence.save_download_run(download_id, data)


def _watch_download_process(download_id: str, process) -> None:
    try:
        current = _load_download_record(download_id)
        if not current or _is_terminal_download_status(current.get("status")):
            return

        try:
            exit_code = process.wait()
        except Exception as exc:
            current = _load_download_record(download_id)
            if current and not _is_terminal_download_status(current.get("status")):
                failed_at = now_iso()
                current["status"] = "failed"
                current["updated_at"] = failed_at
                current["completed_at"] = failed_at
                current["exit_code"] = None
                current["error"] = f"process_failed: {exc}"
                _save_download_record(download_id, current)
            return

        current = _load_download_record(download_id)
        if not current or _is_terminal_download_status(current.get("status")):
            return

        completed_at = now_iso()
        current["updated_at"] = completed_at
        current["completed_at"] = completed_at
        current["exit_code"] = exit_code

        if exit_code != 0:
            current["status"] = "failed"
            current["error"] = f"process_failed: exit_code={exit_code}"
        else:
            current["status"] = "completed"
            current["error"] = None

        _save_download_record(download_id, current)
    finally:
        import threading
        if _download_watcher_lock:
            with _download_watcher_lock:
                _active_download_watchers.discard(download_id)


def _start_download_watcher(download_id: str, process) -> None:
    import threading
    global _download_watcher_lock
    if _download_watcher_lock is None:
        _download_watcher_lock = threading.Lock()

    with _download_watcher_lock:
        if download_id in _active_download_watchers:
            return
        _active_download_watchers.add(download_id)

    watcher = threading.Thread(
        target=_watch_download_process,
        args=(download_id, process),
        daemon=True,
        name=f"download-watcher-{download_id}",
    )
    watcher.start()


async def download_data(payload: dict):
    """Trigger engine download-data (if supported)."""
    from app.engines.base import EngineFeatureNotSupported
    from app.freqtrade.backtest_runner import _resolve_engine
    import uuid

    download_id = f"dl-{uuid.uuid4().hex[:8]}"
    created_at = now_iso()

    engine = _resolve_engine()

    try:
        prepared = engine.prepare_download_data(payload)
    except EngineFeatureNotSupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_path = os.path.join(download_runs_dir(), download_id, "download.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    meta = {
        "download_id": download_id,
        "created_at": created_at,
        "updated_at": created_at,
        "completed_at": None,
        "status": "queued",
        "command": prepared.get("command"),
        "artifact_path": log_path,
        "pid": None,
        "exit_code": None,
        "error": None,
    }
    persistence.save_download_run(download_id, meta)

    try:
        result = engine.run_download_data(prepared, log_path=log_path)
    except Exception as exc:
        failed_at = now_iso()
        meta["status"] = "failed"
        meta["updated_at"] = failed_at
        meta["completed_at"] = failed_at
        meta["error"] = f"launch_failed: {exc}"
        persistence.save_download_run(download_id, meta)
        return {
            "status": meta["status"],
            "download_id": download_id,
            "command": meta["command"],
            "artifact_path": meta["artifact_path"],
            "error": meta["error"],
        }

    meta["status"] = "running"
    meta["updated_at"] = now_iso()
    meta["pid"] = result.get("pid")
    meta["error"] = None
    persistence.save_download_run(download_id, meta)

    process = result.get("process")
    if process is not None:
        _start_download_watcher(download_id, process)

    return {
        "status": meta["status"],
        "download_id": download_id,
        "command": meta["command"],
        "artifact_path": meta["artifact_path"],
    }


async def stream_download_logs(download_id: str):
    """Server-sent event stream for download-data live logs."""
    if not persistence.load_download_run(download_id):
        raise HTTPException(status_code=404, detail=f"Download {download_id} not found")

    from app.freqtrade.backtest_stream import stream_log_response
    return stream_log_response(
        lambda: persistence.load_download_run(download_id),
        download_runs_dir(),
        _TERMINAL_DOWNLOAD_STATUSES,
    )


async def list_configs():
    return {"configs": config_svc.list_saved_configs()}


async def save_config(payload: ConfigSaveRequest):
    config_svc.save_config(payload.name, payload.data)
    return {"status": "saved", "name": payload.name}


async def load_config(name: str):
    return {"name": name, "data": config_svc.load_config(name)}


async def delete_config(name: str):
    config_svc.delete_config(name)
    return {"status": "deleted", "name": name}


async def validate_data(payload: dict):
    """Validate candle availability and timerange coverage for the selected pairs."""
    from app.freqtrade.backtest_runner import _resolve_engine
    from app.freqtrade.settings import SUPPORTED_EXCHANGES, SUPPORTED_TIMEFRAMES
    from app.engines.base import EngineFeatureNotSupported

    pairs = list(payload.get("pairs", []))
    timeframe = str(payload.get("timeframe") or "")
    exchange = str(payload.get("exchange") or config_svc.get_settings().get("default_exchange") or "binance")
    timerange = payload.get("timerange")

    if not pairs:
        return JSONResponse(
            status_code=400,
            content={"valid": False, "message": "No pairs provided", "results": []},
        )

    if not timeframe:
        return JSONResponse(
            status_code=400,
            content={"valid": False, "message": "No timeframe provided", "results": []},
        )

    if not validation_svc.validate_timeframe(timeframe):
        return JSONResponse(
            status_code=400,
            content={"valid": False, "message": f"Invalid timeframe: {timeframe}", "results": []},
        )

    if timerange:
        timerange_result = validation_svc.validate_timerange(str(timerange))
        if not timerange_result.get("valid"):
            return JSONResponse(
                status_code=400,
                content={"valid": False, "message": timerange_result.get("error") or "Invalid timerange", "results": []},
            )

    engine = _resolve_engine()
    try:
        results = engine.validate_data(
            pairs=pairs,
            timeframe=timeframe,
            exchange=exchange,
            timerange=str(timerange) if timerange else None,
        )
    except EngineFeatureNotSupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    status_counts: dict[str, int] = {}
    for row in results:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    ready_count = status_counts.get("valid", 0)
    issue_count = len(results) - ready_count
    all_valid = bool(results) and issue_count == 0

    if all_valid:
        message = f"All {len(results)} pairs cover the requested data range."
    elif ready_count:
        message = f"{ready_count} pair(s) ready, {issue_count} with issues or incomplete coverage."
    else:
        message = "No pairs are ready for the selected validation request."

    return {
        "valid": all_valid,
        "message": message,
        "summary": {
            "exchange": exchange,
            "timeframe": timeframe,
            "timerange": str(timerange) if timerange else None,
            "pair_count": len(results),
            "ready_count": ready_count,
            "issue_count": issue_count,
            "status_counts": status_counts,
        },
        "results": results,
    }


__all__ = [
    # Backtest runner
    "get_options",
    "run_backtest",
    "load_live_strategy_code",
    "load_live_strategy_parameters",
    # Backtest process
    "stop_backtest_run",
    "_reconcile_stale_backtest_run",
    "_watch_backtest_process",
    "_is_terminal_status",
    "_load_run_record",
    "_start_backtest_watcher",
    # Backtest stream
    "stream_backtest_logs",
    # Backtest results
    "list_backtest_runs",
    "get_backtest_run",
    "compare_backtest_runs",
    "get_summary",
    "get_trades",
    "_summarize_run_record",
    # Backtest diagnosis
    "get_backtest_run_diagnosis",
    "_derive_diagnosis_status",
    "_default_ai_payload",
    "_resolve_linked_version_for_run",
    # Proposal service
    "create_backtest_run_proposal_candidate",
    # Download and config
    "download_data",
    "stream_download_logs",
    "list_configs",
    "save_config",
    "load_config",
    "delete_config",
    "validate_data",
    # Services and utilities
    "results_svc",
    "config_svc",
    "persistence",
    "validation_svc",
    "analyze_run_diagnosis_overlay",
    "create_proposal_candidate_from_diagnosis",
    "user_data_results_dir",
]
