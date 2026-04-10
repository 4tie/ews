"""
Version Management Router - Endpoints for strategy version control.
Provides Accept (promote) and Rollback functionality.
"""
from fastapi import APIRouter, HTTPException
from app.models.optimizer_models import (
    AcceptRequest,
    RejectRequest,
    RollbackRequest,
    StrategyVersion,
    VersionListResponse,
)
from app.services.mutation_service import mutation_service


# Prefix is set in app/main.py
router = APIRouter(tags=["versions"])


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


@router.post("/{strategy_name}/accept")
async def accept_version(
    strategy_name: str,
    request: AcceptRequest,
) -> dict:
    """Accept (promote) a candidate version to active."""
    _require_owned_version(strategy_name, request.version_id)

    result = mutation_service.accept_version(request.version_id, request.notes)
    if result.status == "error":
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "version_id": result.version_id,
        "status": result.status,
        "message": result.message,
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
