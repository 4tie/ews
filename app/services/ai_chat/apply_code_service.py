"""
AI Apply Code Service - Applies AI-generated code patches to strategies.
All changes go through StrategyMutationService for version control.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from typing import Any

from app.models.optimizer_models import ChangeType, MutationRequest
from app.services.mutation_service import mutation_service, VersionStatus


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
    create_backup: bool = False,
    created_by: str = "ai_apply",
) -> ApplyResult:
    """Apply AI-generated code patch to strategy file with version control.
    
    Creates a candidate version WITHOUT touching live strategy files.
    Use promote_candidate() to apply changes to live files.
    """
    if not strategy_dir:
        strategy_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "user_data", "strategies")
        strategy_dir = os.path.abspath(strategy_dir)
    
    file_path = os.path.join(strategy_dir, f"{strategy_name}.py")
    
    if not os.path.exists(strategy_dir):
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Strategy directory not found: {strategy_dir}",
            backup_path=None,
            version_id=None,
            message=None,
        )
    
    # Create candidate version (no live file modification)
    mutation_result = mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.CODE_CHANGE,
            summary=f"AI code change applied to {strategy_name}",
            created_by=created_by,
            code=code,
        )
    )
    
    version_id = mutation_result.version_id
    
    return ApplyResult(
        success=True,
        file_path=None,
        error=None,
        backup_path=None,
        version_id=version_id,
        message=f"Candidate version {version_id} created. Use promote_candidate() to apply to live strategy file.",
    )


async def apply_parameters(
    strategy_name: str,
    parameters: dict[str, Any],
    config_file: str | None = None,
    created_by: str = "ai_apply",
) -> ApplyResult:
    """Apply AI-generated parameters to strategy config with version control.
    
    Creates a candidate version WITHOUT touching live config files.
    Use promote_candidate() to apply changes to live files.
    """
    if not config_file:
        config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "user_data", "config")
        config_dir = os.path.abspath(config_dir)
        config_file = os.path.join(config_dir, f"config_{strategy_name}.json")
    
    # Create candidate version (no live file modification)
    mutation_result = mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.PARAMETER_CHANGE,
            summary=f"Parameter-only change for {strategy_name}",
            created_by=created_by,
            parameters=parameters,
        )
    )
    
    version_id = mutation_result.version_id
    
    return ApplyResult(
        success=True,
        file_path=None,
        error=None,
        backup_path=None,
        version_id=version_id,
        message=f"Candidate version {version_id} created. Use promote_candidate() to apply to live config file.",
    )


async def restore_backup(backup_path: str) -> ApplyResult:
    """Restore strategy from backup."""
    if not os.path.exists(backup_path):
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Backup file not found: {backup_path}",
            backup_path=None,
            version_id=None,
            message=None,
        )
    
    try:
        original_path = backup_path.replace(".bak", "")
        shutil.copy2(backup_path, original_path)
        
        return ApplyResult(
            success=True,
            file_path=original_path,
            error=None,
            backup_path=backup_path,
            version_id=None,
            message="Backup restored successfully.",
        )
    except Exception as e:
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Failed to restore backup: {str(e)}",
            backup_path=None,
            version_id=None,
            message=None,
        )


async def promote_candidate(
    version_id: str,
    strategy_dir: str | None = None,
    config_dir: str | None = None,
) -> ApplyResult:
    """Promote a candidate version by applying its code/parameters to live files.
    
    This function loads the candidate version and writes its code/parameters
    to the live strategy file and/or config file.
    """
    if not strategy_dir:
        strategy_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "user_data", "strategies")
        strategy_dir = os.path.abspath(strategy_dir)
    
    if not config_dir:
        config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "user_data", "config")
        config_dir = os.path.abspath(config_dir)
    
    # Extract strategy name from version_id
    parts = version_id.split("_")
    strategy_name = parts[1] if len(parts) > 1 else "unknown"
    
    # Load the candidate version
    version = mutation_service.get_version(strategy_name, version_id)
    
    if not version:
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Version {version_id} not found",
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
    
    file_path = None
    config_file = None
    applied_items = []
    
    # Apply code if present
    if version.code_snapshot:
        file_path = os.path.join(strategy_dir, f"{strategy_name}.py")
        
        # Create backup of live file
        backup_path = None
        if os.path.exists(file_path):
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(version.code_snapshot)
            applied_items.append("code")
        except Exception as e:
            return ApplyResult(
                success=False,
                file_path=None,
                error=f"Failed to write strategy file: {str(e)}",
                backup_path=backup_path,
                version_id=version_id,
                message=None,
            )
    
    # Apply parameters if present
    if version.parameters_snapshot:
        config_file = os.path.join(config_dir, f"config_{strategy_name}.json")
        
        config_data = {}
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                config_data = json.load(f)
        
        config_data.update(version.parameters_snapshot)
        
        try:
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w") as f:
                json.dump(config_data, f, indent=2)
            applied_items.append("parameters")
        except Exception as e:
            return ApplyResult(
                success=False,
                file_path=file_path,
                error=f"Failed to write config file: {str(e)}",
                backup_path=None,
                version_id=version_id,
                message=None,
            )
    
    # Promote version status via mutation service
    mutation_service.accept_version(version_id, notes=f"Promoted with {', '.join(applied_items) if applied_items else 'empty'}")
    
    return ApplyResult(
        success=True,
        file_path=file_path,
        error=None,
        backup_path=None,
        version_id=version_id,
        message=f"Promoted {version_id} to active. Applied: {', '.join(applied_items) if applied_items else 'none'}.",
    )


__all__ = ["ApplyResult", "apply_code_patch", "apply_parameters", "promote_candidate", "restore_backup"]
