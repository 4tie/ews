"""
AI Apply Code Service - AI chat candidate staging and run-scoped workflow helpers.
All changes still flow through the version contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.freqtrade import runtime as freqtrade_runtime
from app.models.backtest_models import BacktestRunRecord, BacktestRunRequest, BacktestTriggerSource
from app.models.optimizer_models import ChangeType, MutationRequest, VersionStatus
from app.services.mutation_service import mutation_service
from app.services.persistence_service import PersistenceService
from app.services.results.diagnosis_service import diagnosis_service
from app.services.results.strategy_intelligence_apply_service import create_proposal_candidate_from_diagnosis
from app.services.results_service import ResultsService


@dataclass
class ApplyResult:
    success: bool
    file_path: str | None
    error: str | None
    backup_path: str | None
    version_id: str | None
    message: str | None = None


persistence = PersistenceService()
results_svc = ResultsService()


async def apply_code_patch(
    strategy_name: str,
    code: str,
    strategy_dir: str | None = None,
    created_by: str = "ai_apply",
    summary: str | None = None,
    source_ref: str | None = None,
    parent_version_id: str | None = None,
) -> ApplyResult:
    """Create a candidate version for an AI-generated code patch without touching live files."""
    del strategy_dir
    mutation_result = mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.CODE_CHANGE,
            summary=summary or f"AI code change applied to {strategy_name}",
            created_by=created_by,
            code=code,
            source_ref=source_ref,
            parent_version_id=parent_version_id,
        )
    )

    return ApplyResult(
        success=True,
        file_path=None,
        error=None,
        backup_path=None,
        version_id=mutation_result.version_id,
        message=f"Candidate version {mutation_result.version_id} created. Accept it through the version workflow when ready.",
    )


async def apply_parameters(
    strategy_name: str,
    parameters: dict[str, Any],
    config_file: str | None = None,
    created_by: str = "ai_apply",
    summary: str | None = None,
    source_ref: str | None = None,
    parent_version_id: str | None = None,
) -> ApplyResult:
    """Create a candidate version for AI-generated parameter changes without touching live files."""
    del config_file
    mutation_result = mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.PARAMETER_CHANGE,
            summary=summary or f"Parameter-only change for {strategy_name}",
            created_by=created_by,
            parameters=parameters,
            source_ref=source_ref,
            parent_version_id=parent_version_id,
        )
    )

    return ApplyResult(
        success=True,
        file_path=None,
        error=None,
        backup_path=None,
        version_id=mutation_result.version_id,
        message=f"Candidate version {mutation_result.version_id} created. Accept it through the version workflow when ready.",
    )


async def create_run_scoped_candidate(
    *,
    run_id: str,
    strategy_name: str,
    parameters: dict[str, Any] | None = None,
    code: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Stage a run-scoped AI chat candidate through the unified proposal lifecycle."""
    run = _load_run_record(run_id)
    if run.strategy != strategy_name:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} belongs to {run.strategy}, not {strategy_name}",
        )

    summary_state = results_svc.load_run_summary_state(run)
    if summary_state.get("state") != "ready":
        raise HTTPException(
            status_code=400,
            detail=summary_state.get("error") or "Summary is not ready for proposal generation yet.",
        )

    summary_payload = summary_state.get("summary")
    summary_block = results_svc.extract_run_summary_block(summary_payload, run.strategy) if summary_payload else None
    summary_metrics = results_svc._normalize_summary_metrics(summary_payload, run.strategy) if summary_payload else None
    trades = summary_block.get("trades") if isinstance(summary_block, dict) and isinstance(summary_block.get("trades"), list) else []
    results_per_pair = (
        summary_block.get("results_per_pair")
        if isinstance(summary_block, dict) and isinstance(summary_block.get("results_per_pair"), list)
        else []
    )

    linked_version, linked_source = _resolve_linked_version_for_run(run)
    if linked_version is None:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} is not linked to a version and no active version fallback is available.",
        )

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

    result = await create_proposal_candidate_from_diagnosis(
        strategy_name=run.strategy,
        run_id=run.run_id,
        linked_version=linked_version,
        request_snapshot=run.request_snapshot or {},
        summary_metrics=summary_metrics,
        diagnosis=diagnosis,
        ai_payload={},
        source_kind="ai_chat_draft",
        source_index=0,
        candidate_mode="code_patch" if code else "parameter_only",
        candidate_parameters=parameters,
        candidate_code=code,
        candidate_summary=summary,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or result.message)

    return {
        "baseline_run_id": run.run_id,
        "baseline_version_id": getattr(linked_version, "version_id", None),
        "baseline_run_version_id": run.version_id,
        "baseline_version_source": linked_source,
        "candidate_version_id": result.version_id,
        "candidate_change_type": result.candidate_change_type,
        "candidate_status": result.candidate_status,
        "message": result.message,
    }


async def rerun_candidate_backtest(
    *,
    baseline_run_id: str,
    candidate_version_id: str,
) -> dict[str, Any]:
    """Rerun a staged candidate by reusing the baseline run snapshot and overriding version_id."""
    baseline_run = _load_run_record(baseline_run_id)
    snapshot = baseline_run.request_snapshot or {}
    if not isinstance(snapshot, dict) or not snapshot.get("strategy") or not snapshot.get("timeframe"):
        raise HTTPException(
            status_code=400,
            detail="Baseline run request snapshot is missing required strategy launch fields.",
        )

    payload = BacktestRunRequest(
        strategy=str(snapshot.get("strategy") or baseline_run.strategy),
        timeframe=str(snapshot.get("timeframe") or ""),
        timerange=str(snapshot.get("timerange")) if snapshot.get("timerange") else None,
        pairs=list(snapshot.get("pairs") or []),
        exchange=str(snapshot.get("exchange") or "binance"),
        max_open_trades=snapshot.get("max_open_trades"),
        dry_run_wallet=snapshot.get("dry_run_wallet"),
        config_path=str(snapshot.get("config_path")) if snapshot.get("config_path") else None,
        extra_flags=list(snapshot.get("extra_flags") or []),
        version_id=str(candidate_version_id or "").strip() or None,
        trigger_source=BacktestTriggerSource.AI_APPLY,
    )
    if not payload.version_id:
        raise HTTPException(status_code=400, detail="Candidate version_id is required for rerun.")

    response = await freqtrade_runtime.run_backtest(payload)
    return {
        "baseline_run_id": baseline_run_id,
        "candidate_version_id": payload.version_id,
        **dict(response),
    }


async def compare_candidate_vs_baseline(
    *,
    baseline_run_id: str,
    candidate_run_id: str,
) -> dict[str, Any]:
    """Compare the baseline run against a candidate rerun using the existing compare contract."""
    comparison = await freqtrade_runtime.compare_backtest_runs(baseline_run_id, candidate_run_id)
    return {
        "baseline_run_id": baseline_run_id,
        "candidate_run_id": candidate_run_id,
        **dict(comparison),
    }


def resolve_latest_candidate_run(
    candidate_version_id: str,
    *,
    strategy_name: str | None = None,
    completed_only: bool = False,
    summary_required: bool = False,
) -> dict[str, Any] | None:
    target_version_id = str(candidate_version_id or "").strip()
    if not target_version_id:
        return None

    for run in persistence.list_backtest_runs():
        if not isinstance(run, dict):
            continue
        if strategy_name and str(run.get("strategy") or "") != str(strategy_name):
            continue
        if str(run.get("version_id") or "") != target_version_id:
            continue
        if completed_only and str(run.get("status") or "") != "completed":
            continue
        if summary_required and not bool(run.get("summary_available")):
            continue
        return run
    return None


async def promote_candidate(
    version_id: str,
    strategy_name: str | None = None,
    strategy_dir: str | None = None,
    config_dir: str | None = None,
) -> ApplyResult:
    """Promote a candidate by accepting the existing version through the mutation contract only."""
    del strategy_dir, config_dir
    version = mutation_service.get_version_by_id(version_id)
    if not version:
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Version {version_id} not found",
            backup_path=None,
            version_id=version_id,
            message=None,
        )

    if strategy_name and version.strategy_name != strategy_name:
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Version {version_id} belongs to {version.strategy_name}, not {strategy_name}",
            backup_path=None,
            version_id=version_id,
            message=None,
        )

    if version.status != VersionStatus.CANDIDATE:
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Version {version_id} is not a candidate (status: {version.status})",
            backup_path=None,
            version_id=version_id,
            message=None,
        )

    accept_result = mutation_service.accept_version(
        version_id,
        notes="Promoted via version contract",
    )
    if accept_result.status == "error":
        return ApplyResult(
            success=False,
            file_path=None,
            error=accept_result.message,
            backup_path=None,
            version_id=version_id,
            message=None,
        )

    return ApplyResult(
        success=True,
        file_path=None,
        error=None,
        backup_path=None,
        version_id=version_id,
        message=f"Promoted {version_id} to active through the version workflow.",
    )


def _load_run_record(run_id: str) -> BacktestRunRecord:
    data = persistence.load_backtest_run(run_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    try:
        run = BacktestRunRecord(**data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Run {run_id} could not be loaded: {exc}") from exc
    if str(getattr(run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=400, detail=f"Run {run_id} is not a freqtrade run")
    return run


def _resolve_linked_version_for_run(run: BacktestRunRecord):
    if run.version_id:
        linked_version = mutation_service.get_version_by_id(run.version_id)
        if linked_version is not None:
            return linked_version, "run"

    active_version = mutation_service.get_active_version(run.strategy)
    if active_version is not None:
        return active_version, "active_fallback"

    return None, "unavailable"


__all__ = [
    "ApplyResult",
    "apply_code_patch",
    "apply_parameters",
    "create_run_scoped_candidate",
    "rerun_candidate_backtest",
    "compare_candidate_vs_baseline",
    "resolve_latest_candidate_run",
    "promote_candidate",
]
