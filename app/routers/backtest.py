import os
import threading
import uuid
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.models.backtest_models import (
    BacktestRunRecord,
    BacktestRunRequest,
    BacktestRunStatus,
    ConfigSaveRequest,
)
from app.models.optimizer_models import ChangeType, MutationRequest
from app.services.config_service import ConfigService
from app.engines.base import EngineFeatureNotSupported
from app.engines.resolver import engine_from_id, resolve_engine
from app.services.mutation_service import mutation_service
from app.services.persistence_service import PersistenceService
from app.services.results.diagnosis_service import diagnosis_service
from app.services.results.strategy_intelligence_service import analyze_run_diagnosis_overlay
from app.services.results_service import ResultsService
from app.utils.datetime_utils import now_iso
from app.utils.paths import download_runs_dir, live_strategy_file, strategy_config_file, user_data_results_dir

router = APIRouter()
results_svc = ResultsService()
config_svc = ConfigService()
persistence = PersistenceService()

_KNOWN_FAILURE_PREFIXES = (
    "launch_failed:",
    "process_failed:",
    "artifact_resolution_failed:",
    "ingestion_failed:",
    "summary_load_failed:",
)


def _load_json_object(path: str, label: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"{label} could not be loaded: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail=f"{label} must be a JSON object: {path}")
    return payload


def _bootstrap_initial_version(strategy_name: str):
    settings = config_svc.get_settings()
    user_data_path = settings.get("user_data_path")

    try:
        strategy_path = live_strategy_file(strategy_name, user_data_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Initial bootstrap failed: {exc}") from exc

    if not os.path.isfile(strategy_path):
        raise HTTPException(
            status_code=400,
            detail=f"Initial bootstrap failed: live strategy file not found for {strategy_name}",
        )

    try:
        with open(strategy_path, "r", encoding="utf-8") as handle:
            code_snapshot = handle.read()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Initial bootstrap failed: {exc}") from exc

    parameters_snapshot = None
    try:
        config_path = strategy_config_file(strategy_name, user_data_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Initial bootstrap failed: {exc}") from exc

    if os.path.isfile(config_path):
        parameters_snapshot = _load_json_object(config_path, f"Strategy config snapshot for {strategy_name}")

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


def _derive_diagnosis_status(run_record: BacktestRunRecord, summary_state: dict) -> str:
    if summary_state.get("state") == "ready":
        return "ready"

    error = str(run_record.error or "")
    if summary_state.get("state") == "load_failed":
        return "ingestion_failed"
    if error:
        return "ingestion_failed"
    if run_record.status == BacktestRunStatus.FAILED:
        return "ingestion_failed"
    if run_record.completed_at and not run_record.summary_path:
        return "ingestion_failed"
    if run_record.completed_at and not run_record.raw_result_path:
        return "ingestion_failed"
    if any(error.startswith(prefix) for prefix in _KNOWN_FAILURE_PREFIXES):
        return "ingestion_failed"
    return "pending_summary"


def _default_ai_payload(status: str) -> dict:
    return {
        "summary": None,
        "priorities": [],
        "rationale": [],
        "parameter_suggestions": [],
        "ai_status": status,
    }

def _resolve_engine():
    settings = config_svc.get_settings()
    try:
        return resolve_engine(settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

_TERMINAL_BACKTEST_STATUSES = {
    BacktestRunStatus.COMPLETED.value,
    BacktestRunStatus.FAILED.value,
}
_watcher_registry_lock = threading.Lock()
_active_backtest_watchers: set[str] = set()


def _is_terminal_status(status: BacktestRunStatus | str) -> bool:
    value = status.value if isinstance(status, BacktestRunStatus) else str(status)
    return value in _TERMINAL_BACKTEST_STATUSES


def _load_run_record(run_id: str) -> BacktestRunRecord | None:
    data = persistence.load_backtest_run(run_id)
    if not data:
        return None
    return BacktestRunRecord(**data)


def _save_run_record(run_record: BacktestRunRecord) -> None:
    persistence.save_backtest_run(run_record.run_id, run_record.model_dump(mode="json"))



def _list_freqtrade_runs(strategy: str | None = None) -> list[BacktestRunRecord]:
    runs = []
    for data in persistence.list_backtest_runs():
        if not isinstance(data, dict):
            continue
        if str(data.get("engine") or "freqtrade") != "freqtrade":
            continue
        if strategy and data.get("strategy") != strategy:
            continue
        try:
            runs.append(BacktestRunRecord(**data))
        except Exception:
            continue
    return runs
def _mark_failed_run(run_record: BacktestRunRecord, error: str, exit_code: int | None = None) -> None:
    failed_at = now_iso()
    run_record.status = BacktestRunStatus.FAILED
    run_record.updated_at = failed_at
    run_record.completed_at = failed_at
    run_record.exit_code = exit_code
    run_record.error = error
    _save_run_record(run_record)


def _watch_backtest_process(run_id: str, process) -> None:
    try:
        current = _load_run_record(run_id)
        if current is None or _is_terminal_status(current.status):
            return

        try:
            exit_code = process.wait()
        except Exception as exc:
            current = _load_run_record(run_id)
            if current is not None and not _is_terminal_status(current.status):
                _mark_failed_run(current, f"process_failed: {exc}")
            return

        current = _load_run_record(run_id)
        if current is None or _is_terminal_status(current.status):
            return

        completed_at = now_iso()
        current.updated_at = completed_at
        current.completed_at = completed_at
        current.exit_code = exit_code

        if exit_code != 0:
            current.status = BacktestRunStatus.FAILED
            current.error = f"process_failed: exit_code={exit_code}"
            _save_run_record(current)
            return

        try:
            current.raw_result_path = engine_from_id(current.engine).resolve_backtest_raw_result_path(current)
        except Exception as exc:
            current.status = BacktestRunStatus.FAILED
            current.error = f"artifact_resolution_failed: {exc}"
            _save_run_record(current)
            return

        if not current.raw_result_path:
            current.status = BacktestRunStatus.FAILED
            current.error = "artifact_resolution_failed: raw result artifact not found"
            _save_run_record(current)
            return

        try:
            ingest_result = results_svc.ingest_backtest_run(current)
        except Exception as exc:
            current.status = BacktestRunStatus.FAILED
            current.error = f"ingestion_failed: {exc}"
            _save_run_record(current)
            return
        current.status = BacktestRunStatus.COMPLETED
        current.raw_result_path = ingest_result.get("raw_result_path", current.raw_result_path)
        current.result_path = ingest_result.get("result_path")
        current.summary_path = ingest_result.get("summary_path")
        current.error = None
        _save_run_record(current)

        if current.version_id:
            mutation_service.link_backtest(
                current.version_id,
                current.run_id,
                ingest_result.get("profit_pct"),
            )
    finally:
        with _watcher_registry_lock:
            _active_backtest_watchers.discard(run_id)


def _start_backtest_watcher(run_id: str, process) -> None:
    with _watcher_registry_lock:
        if run_id in _active_backtest_watchers:
            return
        _active_backtest_watchers.add(run_id)

    watcher = threading.Thread(
        target=_watch_backtest_process,
        args=(run_id, process),
        daemon=True,
        name=f"backtest-watcher-{run_id}",
    )
    watcher.start()

_TERMINAL_DOWNLOAD_STATUSES = {
    "completed",
    "failed",
}
_download_watcher_lock = threading.Lock()
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
        with _download_watcher_lock:
            _active_download_watchers.discard(download_id)


def _start_download_watcher(download_id: str, process) -> None:
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


def _sse(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _assert_within_base(path: str, base: str) -> str:
    real_path = os.path.normcase(os.path.realpath(path))
    real_base = os.path.normcase(os.path.realpath(base))
    if real_path == real_base:
        return real_path
    if not real_path.startswith(real_base + os.sep):
        raise HTTPException(status_code=400, detail="Invalid log path")
    return real_path


def stream_log_response(meta_loader, allowed_base: str, terminal_statuses: set[str]):
    def _terminal_payload(meta: dict) -> dict:
        status = meta.get("status")
        exit_code = meta.get("exit_code")
        error = meta.get("error")
        line = f"[done] status={status} exit_code={exit_code}"
        if error:
            line = f"{line} error={error}"
        return {
            "line": line,
            "status": status,
            "exit_code": exit_code,
            "error": error,
        }

    async def log_generator():
        yield _sse({"line": "[stream] streaming started"})

        log_path = None
        status = None
        exit_code = None

        while True:
            meta = meta_loader() or {}
            log_path = meta.get("artifact_path")
            status = meta.get("status")
            exit_code = meta.get("exit_code")

            if log_path:
                break

            if str(status) in terminal_statuses:
                yield _sse(_terminal_payload(meta))
                return
            await asyncio.sleep(0.25)

        log_path = _assert_within_base(log_path, allowed_base)

        while not os.path.isfile(log_path):
            meta = meta_loader() or {}
            status = meta.get("status")
            exit_code = meta.get("exit_code")

            if str(status) in terminal_statuses:
                yield _sse(_terminal_payload(meta))
                return
            yield _sse({"line": "[stream] waiting for log file..."})
            await asyncio.sleep(0.25)

        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            while True:
                line = handle.readline()
                if line:
                    yield _sse({"line": line.rstrip("\n")})
                    continue

                meta = meta_loader() or {}
                status = meta.get("status")
                exit_code = meta.get("exit_code")

                if str(status) in terminal_statuses:
                    yield _sse(_terminal_payload(meta))
                    return
                await asyncio.sleep(0.25)

    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/options")
async def get_options():
    """Return available strategies, timeframes, and exchanges."""
    engine = _resolve_engine()
    try:
        strategies = engine.list_strategies()
    except EngineFeatureNotSupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return {
        "strategies": strategies,
        "timeframes": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"],
        "exchanges": ["binance", "kucoin", "bybit", "okx", "gate"],
    }


@router.post("/run")
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

    launch_payload["config_path"] = prepared.get("config_path") or launch_payload.get("config_path")
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
        }

    run_record.status = BacktestRunStatus.RUNNING
    run_record.updated_at = now_iso()
    run_record.command = result.get("command", run_record.command)
    run_record.artifact_path = result.get("log_file")
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
    }


@router.post("/download-data")
async def download_data(payload: dict):
    """Trigger engine download-data (if supported)."""
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


@router.get("/runs/{run_id}/logs/stream")
async def stream_backtest_logs(run_id: str):
    """Server-sent event stream for backtest live logs."""
    if not persistence.load_backtest_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return stream_log_response(
        lambda: persistence.load_backtest_run(run_id),
        user_data_results_dir(),
        _TERMINAL_BACKTEST_STATUSES,
    )


@router.get("/download-data/{download_id}/logs/stream")
async def stream_download_logs(download_id: str):
    """Server-sent event stream for download-data live logs."""
    if not persistence.load_download_run(download_id):
        raise HTTPException(status_code=404, detail=f"Download {download_id} not found")
    return stream_log_response(
        lambda: persistence.load_download_run(download_id),
        download_runs_dir(),
        _TERMINAL_DOWNLOAD_STATUSES,
    )


@router.get("/runs")
async def list_backtest_runs(strategy: str | None = None):
    runs = [results_svc.summarize_backtest_run(run) for run in _list_freqtrade_runs(strategy=strategy)]
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_backtest_run(run_id: str):
    run = _load_run_record(run_id)
    if run is None or str(getattr(run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"run": results_svc.summarize_backtest_run(run)}


@router.get("/runs/{run_id}/diagnosis")
async def get_backtest_run_diagnosis(run_id: str, include_ai: bool = False):
    run = _load_run_record(run_id)
    if run is None or str(getattr(run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    summary_state = results_svc.load_run_summary_state(run)
    summary_available = summary_state.get("state") == "ready"
    summary = summary_state.get("summary") if summary_available else None
    summary_block = results_svc.extract_run_summary_block(summary, run.strategy) if summary else None
    summary_metrics = results_svc._normalize_summary_metrics(summary, run.strategy) if summary else None
    trades = summary_block.get("trades") if isinstance(summary_block, dict) and isinstance(summary_block.get("trades"), list) else []
    results_per_pair = (
        summary_block.get("results_per_pair")
        if isinstance(summary_block, dict) and isinstance(summary_block.get("results_per_pair"), list)
        else []
    )
    linked_version = mutation_service.get_version_by_id(run.version_id) if run.version_id else None

    diagnosis = diagnosis_service.empty_diagnosis()
    if summary_available:
        diagnosis = diagnosis_service.diagnose_run(
            run_record=run,
            summary_metrics=summary_metrics,
            summary_block=summary_block,
            trades=trades,
            results_per_pair=results_per_pair,
            request_snapshot=run.request_snapshot or {},
            request_snapshot_schema_version=run.request_snapshot_schema_version,
            linked_version=linked_version,
        )

    if include_ai:
        if summary_available:
            try:
                ai_payload = await analyze_run_diagnosis_overlay(
                    strategy_name=run.strategy,
                    diagnosis=diagnosis,
                    summary_metrics=summary_metrics,
                    linked_version=linked_version,
                )
            except Exception:
                ai_payload = _default_ai_payload("unavailable")
        else:
            ai_payload = _default_ai_payload("unavailable")
    else:
        ai_payload = _default_ai_payload("disabled")

    return {
        "run_id": run.run_id,
        "strategy": run.strategy,
        "version_id": run.version_id,
        "run_status": run.status.value,
        "summary_available": summary_available,
        "diagnosis_status": _derive_diagnosis_status(run, summary_state),
        "summary_metrics": summary_metrics,
        "summary": summary,
        "diagnosis": diagnosis,
        "ai": ai_payload,
        "error": summary_state.get("error") or run.error or None,
    }


@router.get("/compare")
async def compare_backtest_runs(left_run_id: str, right_run_id: str):
    left_run = _load_run_record(left_run_id)
    if left_run is None or str(getattr(left_run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=404, detail=f"Run {left_run_id} not found")

    right_run = _load_run_record(right_run_id)
    if right_run is None or str(getattr(right_run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=404, detail=f"Run {right_run_id} not found")

    try:
        return results_svc.compare_backtest_runs(left_run, right_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/summary")
async def get_summary(strategy: str | None = None):
    """Load latest backtest summary for a strategy."""
    if not strategy:
        return {"summary": None}
    summary = results_svc.load_latest_summary(strategy)
    return {"summary": summary}


@router.get("/trades")
async def get_trades(strategy: str | None = None):
    """Load trades from latest backtest summary."""
    if not strategy:
        return {"trades": []}
    trades = results_svc.load_trades(strategy)
    return {"trades": trades}


@router.get("/configs")
async def list_configs():
    return {"configs": config_svc.list_saved_configs()}


@router.post("/configs")
async def save_config(payload: ConfigSaveRequest):
    config_svc.save_config(payload.name, payload.data)
    return {"status": "saved", "name": payload.name}


@router.get("/configs/{name}")
async def load_config(name: str):
    return {"name": name, "data": config_svc.load_config(name)}


@router.delete("/configs/{name}")
async def delete_config(name: str):
    config_svc.delete_config(name)
    return {"status": "deleted", "name": name}


@router.post("/validate-data")
async def validate_data(payload: dict):
    """Validate which pairs have existing candle data files."""
    pairs = payload.get("pairs", [])
    timeframe = payload.get("timeframe", "")

    if not pairs:
        return JSONResponse(
            status_code=400,
            content={"valid": False, "message": "No pairs provided", "results": []}
        )

    engine = _resolve_engine()
    try:
        results = engine.validate_data(pairs=pairs, timeframe=timeframe)
    except EngineFeatureNotSupported as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    has_data = any(r["status"] == "valid" for r in results)

    return {
        "valid": has_data,
        "message": f"Found data for {sum(1 for r in results if r['status'] == 'valid')} of {len(pairs)} pairs" if has_data else "No data found for any pairs",
        "results": results
    }






