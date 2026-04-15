"""
Backtest results orchestration and retrieval.

Orchestrates ResultsService for ingestion, summary loading, and comparison.
"""
from typing import Any

from app.freqtrade.backtest_process import _load_run_record, _list_freqtrade_runs
from app.freqtrade.backtest_stream import _derive_backtest_progress
from app.models.backtest_models import BacktestRunRecord
from app.services.results_service import ResultsService

results_svc = ResultsService()


def _summarize_run_record(run_record: BacktestRunRecord) -> dict[str, Any]:
    return results_svc.summarize_backtest_run(run_record, progress=_derive_backtest_progress(run_record))


async def list_backtest_runs(strategy: str | None = None):
    runs = [_summarize_run_record(run) for run in _list_freqtrade_runs(strategy=strategy)]
    return {"runs": runs}


async def get_backtest_run(run_id: str):
    from fastapi import HTTPException
    
    run = _load_run_record(run_id)
    if run is None or str(getattr(run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"run": _summarize_run_record(run)}


async def compare_backtest_runs(left_run_id: str, right_run_id: str):
    from fastapi import HTTPException
    
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


async def get_summary(strategy: str | None = None):
    """Load latest backtest summary for a strategy."""
    if not strategy:
        return {"summary": None}
    summary = results_svc.load_latest_summary(strategy)
    return {"summary": summary}


async def get_trades(strategy: str | None = None):
    """Load trades from latest backtest summary."""
    if not strategy:
        return {"trades": []}
    trades = results_svc.load_trades(strategy)
    return {"trades": trades}
