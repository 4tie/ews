"""
Version Management Router - Endpoints for strategy version control.
Provides Accept (promote) and Rollback functionality.
"""
from typing import Any

from fastapi import APIRouter, HTTPException
from app.freqtrade.backtest_process import _list_freqtrade_runs
from app.models.optimizer_models import (
    AcceptRequest,
    RejectRequest,
    RollbackRequest,
    StrategyVersion,
    VersionDetailResponse,
    VersionListResponse,
)
from app.services.mutation_service import mutation_service
from app.services.results_service import ResultsService


# Prefix is set in app/main.py
router = APIRouter(tags=["versions"])
results_svc = ResultsService()


def _require_owned_version(strategy_name: str, version_id: str) -> StrategyVersion:
    version = mutation_service.get_version_by_id(version_id)
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found")
    if version.strategy_name != strategy_name:
        raise HTTPException(
            status_code=400,
            detail=f"Version {version_id} belongs to {version.strategy_name}, not {strategy_name}",
        )
    return version


def _run_sort_key(run: Any) -> str:
    return str(
        getattr(run, "completed_at", None)
        or getattr(run, "created_at", None)
        or getattr(run, "run_id", None)
        or ""
    )


def _sorted_strategy_runs(strategy_name: str) -> list[Any]:
    return sorted(
        list(_list_freqtrade_runs(strategy=strategy_name)),
        key=_run_sort_key,
        reverse=True,
    )


def _summarize_runs_for_version(strategy_name: str, version_id: str) -> tuple[list[Any], list[dict[str, Any]]]:
    run_records = [
        run
        for run in _sorted_strategy_runs(strategy_name)
        if getattr(run, "version_id", None) == version_id
    ]
    summaries = [results_svc.summarize_backtest_run(run) for run in run_records]
    return run_records, summaries


def _latest_comparable_run(run_records: list[Any]) -> Any | None:
    for run in run_records:
        status = getattr(run, "status", None)
        status_value = getattr(status, "value", status)
        if str(status_value or "").lower() != "completed":
            continue
        if results_svc.load_run_summary_state(run).get("state") != "ready":
            continue
        return run
    return None


def _resolve_compare_version_id(
    strategy_name: str,
    version: StrategyVersion,
    active_version_id: str | None,
    explicit_compare_version_id: str | None,
) -> str | None:
    candidate_ids = [
        explicit_compare_version_id,
        version.parent_version_id,
        version.promoted_from_version_id,
        active_version_id if active_version_id != version.version_id else None,
    ]

    for candidate_id in candidate_ids:
        if not candidate_id or candidate_id == version.version_id:
            continue
        _require_owned_version(strategy_name, candidate_id)
        return candidate_id
    return None


@router.get("/{strategy_name}")
async def list_versions(
    strategy_name: str,
    include_archived: bool = False,
) -> VersionListResponse:
    """List all versions for a strategy."""
    versions = mutation_service.list_versions(strategy_name, include_archived)
    active_version = mutation_service.get_active_version(strategy_name)

    return VersionListResponse(
        strategy_name=strategy_name,
        versions=versions,
        active_version_id=active_version.version_id if active_version else None,
    )


@router.get("/{strategy_name}/active")
async def get_active_version(strategy_name: str) -> StrategyVersion:
    """Get the active version for a strategy."""
    active = mutation_service.get_active_version(strategy_name)
    if not active:
        raise HTTPException(status_code=404, detail=f"No active version for {strategy_name}")
    return active


@router.get("/{strategy_name}/{version_id}")
async def get_version(strategy_name: str, version_id: str) -> StrategyVersion:
    """Get a specific version."""
    return _require_owned_version(strategy_name, version_id)


@router.get("/{strategy_name}/{version_id}/detail")
async def get_version_detail(
    strategy_name: str,
    version_id: str,
    compare_to_version_id: str | None = None,
) -> VersionDetailResponse:
    """Get the enriched detail payload for a specific version."""
    version = _require_owned_version(strategy_name, version_id)
    active_version = mutation_service.get_active_version(strategy_name)
    active_version_id = active_version.version_id if active_version else None

    try:
        resolved = mutation_service.resolve_effective_artifacts(version.version_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Version {version.version_id} artifacts could not be resolved: {exc}") from exc

    linked_run_records, linked_runs = _summarize_runs_for_version(strategy_name, version.version_id)
    latest_run = linked_runs[0] if linked_runs else None
    metrics = latest_run.get("summary_metrics") if isinstance(latest_run, dict) else None

    resolved_compare_version_id = _resolve_compare_version_id(
        strategy_name,
        version,
        active_version_id,
        compare_to_version_id,
    )

    comparison = None
    run_comparison = None
    if resolved_compare_version_id:
        comparison = mutation_service.build_version_compare_payload(
            resolved_compare_version_id,
            version.version_id,
        )
        baseline_version_id = (
            (comparison.get("versions") or {}).get("baseline_version_id")
            or resolved_compare_version_id
        )
        baseline_run_records, _ = _summarize_runs_for_version(strategy_name, baseline_version_id)
        baseline_run = _latest_comparable_run(baseline_run_records)
        candidate_run = _latest_comparable_run(linked_run_records)

        if baseline_run is not None and candidate_run is not None:
            try:
                run_comparison = results_svc.compare_backtest_runs(baseline_run, candidate_run)
            except ValueError:
                run_comparison = None

        resolved_compare_version_id = baseline_version_id

    return VersionDetailResponse(
        strategy_name=strategy_name,
        version=version,
        active_version_id=active_version_id,
        compare_version_id=resolved_compare_version_id,
        resolved_code_snapshot=resolved.get("code_snapshot"),
        resolved_parameters_snapshot=resolved.get("parameters_snapshot"),
        lineage_version_ids=list(resolved.get("lineage") or []),
        linked_runs=linked_runs,
        latest_run=latest_run,
        metrics=metrics if isinstance(metrics, dict) else None,
        comparison=comparison,
        run_comparison=run_comparison,
    )


@router.post("/{strategy_name}/accept")
async def accept_version(
    strategy_name: str,
    request: AcceptRequest,
) -> dict:
    """Accept (promote) a candidate version to active."""
    _require_owned_version(strategy_name, request.version_id)

    if request.promotion_mode.value == "promote_new_strategy":
        result = mutation_service.promote_as_new_strategy(
            request.version_id,
            new_strategy_name=request.new_strategy_name,
            notes=request.notes,
        )
        if result.status == "error":
            raise HTTPException(status_code=400, detail=result.message)

        return {
            "version_id": result.version_id,
            "status": result.status,
            "message": result.message,
            "promotion_mode": request.promotion_mode.value,
            "new_strategy_name": request.new_strategy_name,
            "source_version_id": request.version_id,
        }

    result = mutation_service.accept_version(request.version_id, request.notes)
    if result.status == "error":
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "version_id": result.version_id,
        "status": result.status,
        "message": result.message,
        "promotion_mode": request.promotion_mode.value,
    }


@router.post("/{strategy_name}/rollback")
async def rollback_version(
    strategy_name: str,
    request: RollbackRequest,
) -> dict:
    """Rollback to an older version."""
    _require_owned_version(strategy_name, request.target_version_id)

    result = mutation_service.rollback_version(request.target_version_id, request.reason)
    if result.status == "error":
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "version_id": result.version_id,
        "status": result.status,
        "message": result.message,
    }


@router.post("/{strategy_name}/reject")
async def reject_version(
    strategy_name: str,
    request: RejectRequest,
) -> dict:
    """Reject a candidate version without changing the active version."""
    _require_owned_version(strategy_name, request.version_id)

    result = mutation_service.reject_version(request.version_id, request.reason)
    if result.status == "error":
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "version_id": result.version_id,
        "status": result.status,
        "message": result.message,
    }


@router.post("/{strategy_name}/{version_id}/link-backtest")
async def link_backtest(
    strategy_name: str,
    version_id: str,
    backtest_run_id: str,
    profit_pct: float | None = None,
) -> dict:
    """Link a backtest run to a version."""
    _require_owned_version(strategy_name, version_id)

    mutation_service.link_backtest(version_id, backtest_run_id, profit_pct)
    return {
        "version_id": version_id,
        "backtest_run_id": backtest_run_id,
        "profit_pct": profit_pct,
    }


__all__ = ["router"]
