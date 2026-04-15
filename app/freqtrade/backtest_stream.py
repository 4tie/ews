"""
Backtest log streaming and progress tracking.

Handles live log streaming via SSE, progress milestone parsing,
and generic stream response generation.
"""
import asyncio
import json
import os
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from app.freqtrade.backtest_process import _load_run_record, _tail_log_lines
from app.freqtrade.paths import user_data_results_dir
from app.models.backtest_models import BacktestRunStatus

_BACKTEST_PROGRESS_MILESTONES = (
    ("dumping json to", {"phase": "finalizing", "percent": 90, "label": "Writing results"}),
    ("running backtesting for strategy", {"phase": "backtesting", "percent": 70, "label": "Running backtest"}),
    ("backtesting with data from", {"phase": "backtesting", "percent": 70, "label": "Running backtest"}),
    ("dataload complete. calculating indicators", {"phase": "indicators", "percent": 45, "label": "Calculating indicators"}),
    ("loading data from", {"phase": "loading_data", "percent": 25, "label": "Loading data"}),
)
_BACKTEST_BOOTSTRAP_MARKERS = (
    "using config:",
    "using user-data directory:",
    "checking exchange...",
    "validating configuration",
    "starting freqtrade in backtesting mode",
    "using resolved strategy",
)


def _status_value(status: BacktestRunStatus | str | None) -> str:
    if isinstance(status, BacktestRunStatus):
        return status.value
    return str(status or "")


def _terminal_backtest_progress(status: str) -> dict[str, Any] | None:
    if status == BacktestRunStatus.COMPLETED.value:
        return {"phase": "completed", "percent": 100, "label": "Completed"}
    if status == BacktestRunStatus.FAILED.value:
        return {"phase": "failed", "percent": 100, "label": "Failed"}
    if status == BacktestRunStatus.STOPPED.value:
        return {"phase": "stopped", "percent": 100, "label": "Stopped"}
    return None


def _derive_backtest_progress(run_record) -> dict[str, Any] | None:
    status_value = _status_value(getattr(run_record, "status", None))
    terminal = _terminal_backtest_progress(status_value)
    if terminal is not None:
        return terminal
    if status_value == BacktestRunStatus.QUEUED.value:
        return {"phase": "queued", "percent": 0, "label": "Queued"}

    for line in reversed(_tail_log_lines(getattr(run_record, "artifact_path", None), max_lines=200)):
        lowered = line.lower()
        for marker, payload in _BACKTEST_PROGRESS_MILESTONES:
            if marker in lowered:
                return dict(payload)
        if any(marker in lowered for marker in _BACKTEST_BOOTSTRAP_MARKERS):
            return {"phase": "bootstrap", "percent": 10, "label": "Initializing"}

    return {"phase": "bootstrap", "percent": 10, "label": "Initializing"}


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
    def _with_progress(meta: dict, payload: dict) -> dict:
        progress = meta.get("progress") if isinstance(meta, dict) else None
        if progress is not None:
            payload["progress"] = progress
        return payload

    def _terminal_payload(meta: dict) -> dict:
        status = meta.get("status")
        exit_code = meta.get("exit_code")
        error = meta.get("error")
        line = f"[done] status={status} exit_code={exit_code}"
        if error:
            line = f"{line} error={error}"
        return _with_progress(meta, {
            "line": line,
            "status": status,
            "exit_code": exit_code,
            "error": error,
        })

    async def log_generator():
        initial_meta = meta_loader() or {}
        yield _sse(_with_progress(initial_meta, {"line": "[stream] streaming started"}))

        log_path = None

        while True:
            meta = meta_loader() or {}
            log_path = meta.get("artifact_path")
            status = meta.get("status")

            if log_path:
                break

            if str(status) in terminal_statuses:
                yield _sse(_terminal_payload(meta))
                return
            await asyncio.sleep(0.25)

        try:
            log_path = _assert_within_base(log_path, allowed_base)

            while not os.path.isfile(log_path):
                meta = meta_loader() or {}
                status = meta.get("status")

                if str(status) in terminal_statuses:
                    yield _sse(_terminal_payload(meta))
                    return
                yield _sse(_with_progress(meta, {"line": "[stream] waiting for log file..."}))
                await asyncio.sleep(0.25)

            last_pos = 0
            while True:
                if not os.path.isfile(log_path):
                    break

                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
                        handle.seek(last_pos)
                        new_lines = handle.readlines()
                        if new_lines:
                            meta = meta_loader() or {}
                            for line in new_lines:
                                yield _sse(_with_progress(meta, {"line": line.rstrip("\n")}))
                            last_pos = handle.tell()
                except IOError:
                    pass

                meta = meta_loader() or {}
                status = meta.get("status")

                if str(status) in terminal_statuses:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
                        remaining = handle.read()
                        if remaining:
                            for line in remaining.splitlines():
                                yield _sse(_with_progress(meta, {"line": line}))
                    yield _sse(_terminal_payload(meta))
                    return

                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            yield _sse({"line": "[stream] cancelled"})
        except Exception as exc:
            yield _sse({"line": f"[stream] error: {exc}"})

    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def stream_backtest_logs(run_id: str):
    """Server-sent event stream for backtest live logs."""
    run = _load_run_record(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    def _meta_loader() -> dict:
        from app.freqtrade.backtest_results import _summarize_run_record
        current = _load_run_record(run_id)
        return _summarize_run_record(current) if current is not None else {}

    _TERMINAL_BACKTEST_STATUSES = {
        BacktestRunStatus.COMPLETED.value,
        BacktestRunStatus.FAILED.value,
        BacktestRunStatus.STOPPED.value,
    }

    return stream_log_response(
        _meta_loader,
        user_data_results_dir(),
        _TERMINAL_BACKTEST_STATUSES,
    )
