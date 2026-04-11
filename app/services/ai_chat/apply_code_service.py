"""
AI Apply Code Service - Legacy compatibility helpers for candidate staging.
All changes go through StrategyMutationService for version control.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.optimizer_models import ChangeType, MutationRequest, VersionStatus
from app.services.mutation_service import mutation_service


@dataclass
class ApplyResult:
    success: bool
    file_path: str | None
    error: str | None
    backup_path: str | None
    version_id: str | None
    message: str | None = None


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


async def promote_candidate(
    version_id: str,
    strategy_name: str | None = None,
    strategy_dir: str | None = None,
    config_dir: str | None = None,
) -> ApplyResult:
    """Promote a candidate by accepting the existing version through the mutation contract only."""
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


__all__ = ["ApplyResult", "apply_code_patch", "apply_parameters", "promote_candidate"]
