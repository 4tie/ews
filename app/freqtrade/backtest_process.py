"""
Backtest process lifecycle management.

Handles run record persistence, process monitoring, watcher registry,
and stale run reconciliation.
"""
import os
import signal
import threading
from datetime import datetime
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None

from fastapi import HTTPException

from app.engines.resolver import engine_from_id
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus
from app.services.persistence_service import PersistenceService
from app.utils.datetime_utils import now_iso

persistence = PersistenceService()

_TERMINAL_BACKTEST_STATUSES = {
    BacktestRunStatus.COMPLETED.value,
    BacktestRunStatus.FAILED.value,
    BacktestRunStatus.STOPPED.value,
}
_watcher_registry_lock = threading.Lock()
_active_backtest_watchers: set[str] = set()


def _status_value(status: BacktestRunStatus | str | None) -> str:
    if isinstance(status, BacktestRunStatus):
        return status.value
    return str(status or "")


def _is_terminal_status(status: BacktestRunStatus | str) -> bool:
    return _status_value(status) in _TERMINAL_BACKTEST_STATUSES


def _save_run_record(run_record: BacktestRunRecord) -> None:
    persistence.save_backtest_run(run_record.run_id, run_record.model_dump(mode="json"))


def _is_stop_requested(run_record: BacktestRunRecord | None) -> bool:
    return bool(getattr(run_record, "stop_requested_at", None))


def _process_started_for_run(process, run_record: BacktestRunRecord) -> bool:
    created_at = getattr(run_record, "created_at", None)
    if not created_at:
        return True

    try:
        run_started_ts = datetime.fromisoformat(str(created_at)).timestamp()
    except ValueError:
        return True

    process_started_ts = process.create_time()
    if process_started_ts + 30 < run_started_ts:
        return False
    if process_started_ts - run_started_ts > 300:
        return False
    return True


def _process_matches_run_record(run_record: BacktestRunRecord) -> bool:
    if psutil is None:
        return False

    pid = getattr(run_record, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return False

    try:
        process = psutil.Process(pid)
        if not process.is_running():
            return False
        if process.status() == getattr(psutil, "STATUS_ZOMBIE", "zombie"):
            return False

        return _process_started_for_run(process, run_record)
    except psutil.Error:
        return False


def _resolve_process_exit_code(run_record: BacktestRunRecord) -> int | None:
    if run_record.exit_code is not None:
        return run_record.exit_code
    if psutil is None:
        return None

    pid = getattr(run_record, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return None

    try:
        process = psutil.Process(pid)
        if not _process_started_for_run(process, run_record):
            return None
        return process.wait(timeout=0)
    except (psutil.TimeoutExpired, psutil.Error):
        return None


def _terminate_process_tree(run_record: BacktestRunRecord) -> int | None:
    pid = getattr(run_record, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return _resolve_process_exit_code(run_record)

    if psutil is not None:
        try:
            process = psutil.Process(pid)
            if not _process_started_for_run(process, run_record):
                return None
        except psutil.Error:
            return _resolve_process_exit_code(run_record)

        try:
            children = process.children(recursive=True)
        except psutil.Error:
            children = []

        for child in children:
            try:
                child.terminate()
            except psutil.Error:
                pass

        try:
            process.terminate()
        except psutil.Error:
            pass

        try:
            return process.wait(timeout=5)
        except psutil.TimeoutExpired:
            for child in children:
                try:
                    child.kill()
                except psutil.Error:
                    pass
            try:
                process.kill()
            except psutil.Error:
                pass
            try:
                return process.wait(timeout=5)
            except (psutil.TimeoutExpired, psutil.Error):
                return None
        except psutil.Error:
            return None

    try:
        os.kill(pid, getattr(signal, "SIGTERM", signal.SIGINT))
    except OSError:
        return _resolve_process_exit_code(run_record)
    return None


def _tail_log_lines(log_path: str | None, *, max_lines: int = 200) -> list[str]:
    if not log_path or not os.path.isfile(log_path):
        return []

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            return [line.rstrip("\r\n") for line in handle.readlines()[-max_lines:]]
    except OSError:
        return []


def _extract_level_message(line: str, level: str) -> str | None:
    marker = f" - {level} - "
    if marker not in line:
        return None
    message = line.split(marker, 1)[1].strip()
    return message or None


def _extract_process_failure_detail(run_record: BacktestRunRecord) -> str | None:
    last_error = None
    last_warning = None

    for line in reversed(_tail_log_lines(run_record.artifact_path)):
        if last_error is None:
            last_error = _extract_level_message(line, "ERROR")

        if last_warning is None:
            warning = _extract_level_message(line, "WARNING")
            if warning and ("download-data" in warning.lower() or "no history" in warning.lower()):
                last_warning = warning

        if last_error and last_warning:
            break

    if last_error and last_warning and last_error.lower().startswith("no data found"):
        return f"{last_error} {last_warning}"
    return last_error or last_warning


def _build_process_failure_error(
    run_record: BacktestRunRecord,
    *,
    exit_code: int | None = None,
    fallback: str | None = None,
) -> str:
    detail = _extract_process_failure_detail(run_record)
    if detail and exit_code is not None:
        return f"process_failed: exit_code={exit_code} | {detail}"
    if detail:
        return f"process_failed: {detail}"
    if exit_code is not None and fallback:
        return f"process_failed: exit_code={exit_code} | {fallback}"
    if exit_code is not None:
        return f"process_failed: exit_code={exit_code}"
    if fallback:
        return f"process_failed: {fallback}"
    return "process_failed"


def _is_correctable_terminal_failure(run_record: BacktestRunRecord | None) -> bool:
    if run_record is None:
        return False
    status_value = _status_value(run_record.status)
    if status_value != BacktestRunStatus.FAILED.value:
        return False
    if run_record.exit_code is not None:
        return False
    return str(run_record.error or "").startswith("process_failed: process exited before run finalization")


def _mark_failed_run(run_record: BacktestRunRecord, error: str, exit_code: int | None = None) -> None:
    failed_at = now_iso()
    run_record.status = BacktestRunStatus.FAILED
    run_record.updated_at = failed_at
    run_record.completed_at = failed_at
    run_record.exit_code = exit_code
    run_record.error = error
    _save_run_record(run_record)


def _mark_stopped_run(
    run_record: BacktestRunRecord,
    *,
    exit_code: int | None = None,
    reason: str = "stopped_by_user: stop requested from UI",
) -> BacktestRunRecord:
    stopped_at = now_iso()
    run_record.status = BacktestRunStatus.STOPPED
    run_record.updated_at = stopped_at
    run_record.completed_at = stopped_at
    if run_record.stop_requested_at is None:
        run_record.stop_requested_at = stopped_at
    run_record.exit_code = exit_code
    run_record.error = reason
    _save_run_record(run_record)
    return run_record


def _finalize_successful_backtest_run(run_record: BacktestRunRecord, *, exit_code: int | None) -> BacktestRunRecord:
    from app.services.results_service import ResultsService
    
    results_svc = ResultsService()
    
    completed_at = now_iso()
    run_record.updated_at = completed_at
    run_record.completed_at = completed_at
    if exit_code is not None:
        run_record.exit_code = exit_code
    elif run_record.exit_code is None:
        run_record.exit_code = 0

    try:
        if not run_record.raw_result_path:
            run_record.raw_result_path = engine_from_id(run_record.engine).resolve_backtest_raw_result_path(run_record)
    except Exception as exc:
        run_record.status = BacktestRunStatus.FAILED
        run_record.error = f"artifact_resolution_failed: {exc}"
        _save_run_record(run_record)
        return run_record

    if not run_record.raw_result_path:
        run_record.status = BacktestRunStatus.FAILED
        run_record.error = "artifact_resolution_failed: raw result artifact not found"
        _save_run_record(run_record)
        return run_record

    try:
        ingest_result = results_svc.ingest_backtest_run(run_record)
    except Exception as exc:
        run_record.status = BacktestRunStatus.FAILED
        run_record.error = f"ingestion_failed: {exc}"
        _save_run_record(run_record)
        return run_record

    run_record.status = BacktestRunStatus.COMPLETED
    run_record.exit_code = 0 if run_record.exit_code is None else run_record.exit_code
    run_record.raw_result_path = ingest_result.get("raw_result_path", run_record.raw_result_path)
    run_record.result_path = ingest_result.get("result_path")
    run_record.summary_path = ingest_result.get("summary_path")
    run_record.error = None
    _save_run_record(run_record)

    if run_record.version_id:
        from app.services.mutation_service import mutation_service
        mutation_service.link_backtest(
            run_record.version_id,
            run_record.run_id,
            ingest_result.get("profit_pct"),
        )
    return run_record


def _reconcile_stale_backtest_run(run_record: BacktestRunRecord) -> BacktestRunRecord:
    status_value = _status_value(run_record.status)
    if status_value != BacktestRunStatus.RUNNING.value:
        return run_record
    if _process_matches_run_record(run_record):
        return run_record

    if run_record.raw_result_path:
        return _finalize_successful_backtest_run(run_record, exit_code=run_record.exit_code)

    try:
        resolved_raw_result = engine_from_id(run_record.engine).resolve_backtest_raw_result_path(run_record)
    except Exception:
        resolved_raw_result = None

    if resolved_raw_result:
        run_record.raw_result_path = resolved_raw_result
        return _finalize_successful_backtest_run(run_record, exit_code=run_record.exit_code)

    exit_code = _resolve_process_exit_code(run_record)
    if _is_stop_requested(run_record):
        return _mark_stopped_run(
            run_record,
            exit_code=exit_code,
            reason=str(run_record.error or "stopped_by_user: stop requested from UI"),
        )

    _mark_failed_run(
        run_record,
        _build_process_failure_error(
            run_record,
            exit_code=exit_code,
            fallback="process exited before run finalization",
        ),
        exit_code=exit_code,
    )
    return run_record


def _load_run_record(run_id: str) -> BacktestRunRecord | None:
    data = persistence.load_backtest_run(run_id)
    if not data:
        return None
    return _reconcile_stale_backtest_run(BacktestRunRecord(**data))


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
            runs.append(_reconcile_stale_backtest_run(BacktestRunRecord(**data)))
        except Exception:
            continue
    return runs


def _watch_backtest_process(run_id: str, process) -> None:
    try:
        current = _load_run_record(run_id)
        if current is None:
            return
        if _is_terminal_status(current.status) and not _is_correctable_terminal_failure(current):
            return

        try:
            exit_code = process.wait()
        except Exception as exc:
            current = _load_run_record(run_id)
            if current is None:
                return
            if _is_terminal_status(current.status) and not _is_correctable_terminal_failure(current):
                return
            if _is_stop_requested(current):
                _mark_stopped_run(
                    current,
                    reason=str(current.error or "stopped_by_user: stop requested from UI"),
                )
                return
            _mark_failed_run(
                current,
                _build_process_failure_error(
                    current,
                    fallback=str(exc),
                ),
            )
            return

        current = _load_run_record(run_id)
        if current is None:
            return
        if _is_terminal_status(current.status) and not _is_correctable_terminal_failure(current):
            return

        if exit_code == 0:
            _finalize_successful_backtest_run(current, exit_code=exit_code)
            return

        if _is_stop_requested(current):
            _mark_stopped_run(
                current,
                exit_code=exit_code,
                reason=str(current.error or "stopped_by_user: stop requested from UI"),
            )
            return

        _mark_failed_run(
            current,
            _build_process_failure_error(current, exit_code=exit_code),
            exit_code=exit_code,
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


async def stop_backtest_run(run_id: str):
    run = _load_run_record(run_id)
    if run is None or str(getattr(run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if _is_terminal_status(run.status):
        from app.freqtrade.backtest_results import _summarize_run_record
        return {"status": "already_terminal", "run": _summarize_run_record(run)}

    requested_at = now_iso()
    run.stop_requested_at = requested_at
    run.updated_at = requested_at
    run.error = run.error or "stopped_by_user: stop requested from UI"
    _save_run_record(run)

    exit_code = _terminate_process_tree(run)
    current = _load_run_record(run_id) or run
    if not _is_terminal_status(current.status):
        current = _mark_stopped_run(
            current,
            exit_code=exit_code,
            reason=str(current.error or "stopped_by_user: stop requested from UI"),
        )

    from app.freqtrade.backtest_results import _summarize_run_record
    return {"status": _status_value(current.status) or "stopped", "run": _summarize_run_record(current)}
