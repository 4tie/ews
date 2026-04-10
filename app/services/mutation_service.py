"""
Strategy Mutation Service - Core contract for version-controlled strategy mutations.

All strategy changes (Strategy Lab save, AI apply-code, Evolution generation, 
Parameter-only quick actions) MUST go through this service to ensure:
- Every mutation creates a new version (no in-place overwrites)
- Full traceability (who, when, what)
- Reversibility (Accept/Rollback)
- Backtest/evolution reruns track exact version_id used
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from app.models.optimizer_models import (
    MutationRequest,
    MutationResult,
    StrategyVersion,
    VersionStatus,
)
from app.utils.json_io import read_json, write_json
from app.utils.paths import (
    storage_dir,
    strategy_active_version_file,
    strategy_version_file,
    strategy_versions_dir,
)


@dataclass
class MutationContext:
    """Context passed through the mutation pipeline."""
    request: MutationRequest
    version: StrategyVersion
    success: bool
    error: Optional[str] = None


class StrategyMutationService:
    """Single source of truth for all strategy mutations."""

    def __init__(self):
        self._cache: Dict[str, StrategyVersion] = {}

    def _generate_version_id(self, strategy_name: str) -> str:
        """Generate a unique version ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:6]
        return f"v_{strategy_name}_{timestamp}_{short_uuid}"

    def _ensure_version_dir(self, strategy_name: str) -> None:
        """Ensure version directory exists."""
        version_dir = strategy_versions_dir(strategy_name)
        os.makedirs(version_dir, exist_ok=True)

    def _load_version_from_disk(self, strategy_name: str, version_id: str) -> Optional[StrategyVersion]:
        """Load version from disk."""
        version_file = strategy_version_file(strategy_name, version_id)
        if not os.path.exists(version_file):
            return None
        data = read_json(version_file, fallback={})
        if not data:
            return None
        return StrategyVersion(**data)

    def _save_version(self, version: StrategyVersion) -> None:
        """Save version to disk."""
        self._ensure_version_dir(version.strategy_name)
        version_file = strategy_version_file(version.strategy_name, version.version_id)
        write_json(version_file, version.model_dump())
        self._cache[version.version_id] = version

    def _set_active_version(self, version: StrategyVersion) -> None:
        """Set active version reference."""
        self._ensure_version_dir(version.strategy_name)
        active_file = strategy_active_version_file(version.strategy_name)
        write_json(active_file, {
            "version_id": version.version_id,
            "updated_at": datetime.now().isoformat(),
        })

    def _get_active_version_id(self, strategy_name: str) -> Optional[str]:
        """Get the active version ID."""
        active_file = strategy_active_version_file(strategy_name)
        if not os.path.exists(active_file):
            return None
        data = read_json(active_file, fallback={})
        return data.get("version_id")

    def get_version_by_id(self, version_id: str) -> Optional[StrategyVersion]:
        """Get a version by ID without inferring ownership from the ID format."""
        if version_id in self._cache:
            return self._cache[version_id]

        versions_root = os.path.join(storage_dir(), "versions")
        if not os.path.isdir(versions_root):
            return None

        for strategy_name in os.listdir(versions_root):
            strategy_dir = os.path.join(versions_root, strategy_name)
            if not os.path.isdir(strategy_dir):
                continue

            version = self._load_version_from_disk(strategy_name, version_id)
            if version:
                return version

        return None

    def create_mutation(self, request: MutationRequest) -> MutationResult:
        """
        Create a new version from a mutation request.

        This is the ONLY way to create new strategy versions.
        All change paths must use this service.
        """
        version_id = self._generate_version_id(request.strategy_name)

        parent_version_id = request.parent_version_id
        if not parent_version_id:
            parent_version_id = self._get_active_version_id(request.strategy_name)

        version = StrategyVersion(
            version_id=version_id,
            parent_version_id=parent_version_id,
            strategy_name=request.strategy_name,
            created_at=datetime.now().isoformat(),
            created_by=request.created_by,
            change_type=request.change_type,
            summary=request.summary,
            diff_ref=request.diff_ref,
            source_ref=request.source_ref,
            status=VersionStatus.CANDIDATE,
            code_snapshot=request.code,
            parameters_snapshot=request.parameters,
        )

        self._save_version(version)

        return MutationResult(
            version_id=version_id,
            status="created",
            message=f"New candidate version {version_id} created from {request.change_type}",
        )

    def accept_version(self, version_id: str, notes: Optional[str] = None) -> MutationResult:
        """Promote a candidate version to active."""
        version = self.get_version_by_id(version_id)
        if not version:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} not found",
            )

        if version.status == VersionStatus.ACTIVE:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} is already active",
            )

        active_id = self._get_active_version_id(version.strategy_name)
        if active_id and active_id != version.version_id:
            old_active = self.get_version(version.strategy_name, active_id) or self.get_version_by_id(active_id)
            if old_active:
                old_active.status = VersionStatus.ARCHIVED
                self._save_version(old_active)

        version.status = VersionStatus.ACTIVE
        version.promoted_from_version_id = active_id
        version.promoted_at = datetime.now().isoformat()
        self._save_version(version)
        self._set_active_version(version)

        return MutationResult(
            version_id=version_id,
            status="accepted",
            message=f"Version {version_id} promoted to active" + (f": {notes}" if notes else ""),
        )

    def rollback_version(self, target_version_id: str, reason: Optional[str] = None) -> MutationResult:
        """Rollback to an existing version."""
        target_version = self.get_version_by_id(target_version_id)
        if not target_version:
            return MutationResult(
                version_id=target_version_id,
                status="error",
                message=f"Version {target_version_id} not found",
            )

        current_active = self._get_active_version_id(target_version.strategy_name)
        if current_active and current_active != target_version.version_id:
            current = self.get_version(target_version.strategy_name, current_active) or self.get_version_by_id(current_active)
            if current:
                current.status = VersionStatus.ARCHIVED
                self._save_version(current)

        target_version.status = VersionStatus.ACTIVE
        target_version.promoted_from_version_id = current_active
        target_version.promoted_at = datetime.now().isoformat()
        self._save_version(target_version)
        self._set_active_version(target_version)

        return MutationResult(
            version_id=target_version_id,
            status="rolled_back",
            message=f"Rolled back to {target_version_id}" + (f": {reason}" if reason else ""),
        )

    def get_version(self, strategy_name: str, version_id: str) -> Optional[StrategyVersion]:
        """Get a specific version."""
        if version_id in self._cache:
            return self._cache[version_id]
        return self._load_version_from_disk(strategy_name, version_id)

    def get_active_version(self, strategy_name: str) -> Optional[StrategyVersion]:
        """Get the active version for a strategy."""
        active_id = self._get_active_version_id(strategy_name)
        if not active_id:
            return None
        return self.get_version(strategy_name, active_id)

    def list_versions(self, strategy_name: str, include_archived: bool = False) -> List[StrategyVersion]:
        """List all versions for a strategy."""
        version_dir = strategy_versions_dir(strategy_name)
        if not os.path.exists(version_dir):
            return []

        versions: List[StrategyVersion] = []
        for fname in os.listdir(version_dir):
            if not fname.endswith(".json"):
                continue
            if fname == "active_version.json":
                continue

            version_id = fname[:-5]
            version = self.get_version(strategy_name, version_id)
            if version and (include_archived or version.status != VersionStatus.ARCHIVED):
                versions.append(version)

        return sorted(versions, key=lambda v: v.created_at, reverse=True)

    def link_backtest(
        self,
        version_id: str,
        backtest_run_id: str,
        profit_pct: Optional[float] = None,
    ) -> None:
        """Link a backtest run to a version."""
        version = self.get_version_by_id(version_id)
        if version:
            version.backtest_run_id = backtest_run_id
            version.backtest_profit_pct = profit_pct
            self._save_version(version)


mutation_service = StrategyMutationService()


__all__ = [
    "StrategyMutationService",
    "MutationContext",
    "mutation_service",
    "MutationRequest",
    "MutationResult",
    "VersionStatus",
]
