"""
Backtest diagnosis and AI analysis orchestration.

Handles diagnosis status derivation, AI payload defaults, and diagnosis context assembly.
"""
from typing import Any

from fastapi import HTTPException

from app.freqtrade.backtest_process import _load_run_record
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus
from app.services.mutation_service import mutation_service
from app.services.results.diagnosis_service import diagnosis_service
from app.services.results.strategy_intelligence_service import analyze_run_diagnosis_overlay
from app.services.results_service import ResultsService

results_svc = ResultsService()

_KNOWN_FAILURE_PREFIXES = (
    "launch_failed:",
    "process_failed:",
    "artifact_resolution_failed:",
    "ingestion_failed:",
    "summary_load_failed:",
)


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


def _resolve_linked_version_for_run(run_record: BacktestRunRecord):
    if run_record.version_id:
        linked_version = mutation_service.get_version_by_id(run_record.version_id)
        if linked_version is not None:
            return linked_version, "run"

    active_version = mutation_service.get_active_version(run_record.strategy)
    if active_version is not None:
        return active_version, "active_fallback"

    return None, "unavailable"


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
                    run_id=run.run_id,
                    trades=trades,
                    results_per_pair=results_per_pair,
                    request_snapshot=run.request_snapshot or {},
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
        "trades": trades,
        "results_per_pair": results_per_pair,
        "summary": summary,
        "diagnosis": diagnosis,
        "ai": ai_payload,
        "error": summary_state.get("error") or run.error or None,
    }
