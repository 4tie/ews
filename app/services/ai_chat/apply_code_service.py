"""
AI Apply Code Service - Applies AI-generated code patches to strategies.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any


@dataclass
class ApplyResult:
    success: bool
    file_path: str | None
    error: str | None
    backup_path: str | None


async def apply_code_patch(
    strategy_name: str,
    code: str,
    strategy_dir: str | None = None,
    create_backup: bool = True,
) -> ApplyResult:
    """Apply AI-generated code patch to strategy file."""
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
        )
    
    backup_path = None
    if create_backup and os.path.exists(file_path):
        backup_path = f"{file_path}.bak"
        shutil.copy2(file_path, backup_path)
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        
        return ApplyResult(
            success=True,
            file_path=file_path,
            error=None,
            backup_path=backup_path,
        )
    except Exception as e:
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Failed to write strategy file: {str(e)}",
            backup_path=backup_path,
        )


async def apply_parameters(
    strategy_name: str,
    parameters: dict[str, Any],
    config_file: str | None = None,
) -> ApplyResult:
    """Apply AI-generated parameters to strategy config."""
    if not config_file:
        config_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "user_data", "config")
        config_dir = os.path.abspath(config_dir)
        config_file = os.path.join(config_dir, f"config_{strategy_name}.json")
    
    import json
    
    config_data = {}
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config_data = json.load(f)
    
    config_data.update(parameters)
    
    try:
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        with open(config_file, "w") as f:
            json.dump(config_data, f, indent=2)
        
        return ApplyResult(
            success=True,
            file_path=config_file,
            error=None,
            backup_path=None,
        )
    except Exception as e:
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Failed to write config file: {str(e)}",
            backup_path=None,
        )


async def restore_backup(backup_path: str) -> ApplyResult:
    """Restore strategy from backup."""
    if not os.path.exists(backup_path):
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Backup file not found: {backup_path}",
            backup_path=None,
        )
    
    try:
        original_path = backup_path.replace(".bak", "")
        shutil.copy2(backup_path, original_path)
        
        return ApplyResult(
            success=True,
            file_path=original_path,
            error=None,
            backup_path=backup_path,
        )
    except Exception as e:
        return ApplyResult(
            success=False,
            file_path=None,
            error=f"Failed to restore backup: {str(e)}",
            backup_path=None,
        )


__all__ = ["ApplyResult", "apply_code_patch", "apply_parameters", "restore_backup"]
