"""
mutation_service.py — Mutation service for version control and strategy evolution tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import uuid

from app.models.optimizer_models import ChangeType, MutationRequest
from app.utils.datetime_utils import now_iso
from app.utils.json_io import read_json, write_json
from app.utils.paths import mutations_dir, versions_dir, resolve_safe


@dataclass
class MutationResult:
    """Result of creating a mutation."""
    version_id: str
    status: str = "created"
    message: str = ""


@dataclass
class AcceptResult:
    """Result of accepting a version."""
    version_id: str
    status: str = "accepted"
    message: str = ""


@dataclass
class StrategyVersion:
    """Represents a strategy version."""
    version_id: str
    strategy_name: str
    change_type: str
    summary: str
    created_by: str
    created_at: str
    code: Optional[str] = None
    parameters: Optional[dict] = None
    source_ref: Optional[str] = None
    is_active: bool = False
    accepted_at: Optional[str] = None
    notes: Optional[str] = None
    backtest_runs: list[str] = field(default_factory=list)
    best_profit_pct: Optional[float] = None


class MutationService:
    """Service for managing strategy mutations and versions."""
    
    def create_mutation(self, request: MutationRequest) -> MutationResult:
        """
        Create a new mutation (version candidate).
        
        Args:
            request: MutationRequest with strategy details
        
        Returns:
            MutationResult with version_id
        """
        version_id = f"v-{uuid.uuid4().hex[:12]}"
        created_at = now_iso()
        
        version = StrategyVersion(
            version_id=version_id,
            strategy_name=request.strategy_name,
            change_type=request.change_type.value if hasattr(request.change_type, 'value') else str(request.change_type),
            summary=request.summary,
            created_by=request.created_by,
            created_at=created_at,
            code=request.code,
            parameters=request.parameters,
            source_ref=request.source_ref,
            is_active=False,
        )
        
        self._save_version(version)
        return MutationResult(version_id=version_id, status="created")
    
    def accept_version(self, version_id: str, notes: str = "") -> AcceptResult:
        """
        Accept (promote) a version to active status.
        
        Args:
            version_id: ID of version to accept
            notes: Optional acceptance notes
        
        Returns:
            AcceptResult with status
        """
        version = self.get_version_by_id(version_id)
        if version is None:
            return AcceptResult(version_id=version_id, status="error", message=f"Version {version_id} not found")
        
        # Deactivate previous active version
        active = self.get_active_version(version.strategy_name)
        if active:
            active.is_active = False
            self._save_version(active)
        
        # Activate this version
        version.is_active = True
        version.accepted_at = now_iso()
        version.notes = notes
        self._save_version(version)
        
        return AcceptResult(version_id=version_id, status="accepted")
    
    def get_version_by_id(self, version_id: str) -> Optional[StrategyVersion]:
        """Load a version by ID."""
        if not version_id:
            return None
        
        path = resolve_safe(versions_dir(), f"{version_id}.json")
        data = read_json(path)
        
        if not data:
            return None
        
        return StrategyVersion(**data)
    
    def get_active_version(self, strategy_name: str) -> Optional[StrategyVersion]:
        """Get the currently active version for a strategy."""
        versions = self.list_versions(strategy_name)
        for version in versions:
            if version.is_active:
                return version
        return None
    
    def get_version(self, strategy_name: str, version_id: str) -> Optional[StrategyVersion]:
        """Get a specific version for a strategy."""
        version = self.get_version_by_id(version_id)
        if version and version.strategy_name == strategy_name:
            return version
        return None
    
    def list_versions(self, strategy_name: str, include_archived: bool = False) -> list[StrategyVersion]:
        """List all versions for a strategy."""
        versions = []
        versions_path = versions_dir()
        
        if not versions_path or not __import__('os').path.isdir(versions_path):
            return versions
        
        for filename in __import__('os').listdir(versions_path):
            if not filename.endswith(".json"):
                continue
            
            path = resolve_safe(versions_path, filename)
            data = read_json(path)
            
            if not data or data.get("strategy_name") != strategy_name:
                continue
            
            try:
                version = StrategyVersion(**data)
                versions.append(version)
            except Exception:
                continue
        
        # Sort by created_at descending
        versions.sort(key=lambda v: v.created_at, reverse=True)
        return versions
    
    def link_backtest(self, version_id: str, run_id: str, profit_pct: Optional[float] = None) -> None:
        """Link a backtest run to a version."""
        version = self.get_version_by_id(version_id)
        if version is None:
            return
        
        if run_id not in version.backtest_runs:
            version.backtest_runs.append(run_id)
        
        if profit_pct is not None:
            if version.best_profit_pct is None or profit_pct > version.best_profit_pct:
                version.best_profit_pct = profit_pct
        
        self._save_version(version)
    
    def rollback_version(self, target_version_id: str, reason: str = "") -> AcceptResult:
        """Rollback to an older version."""
        version = self.get_version_by_id(target_version_id)
        if version is None:
            return AcceptResult(version_id=target_version_id, status="error", message="Version not found")
        
        # Deactivate current active
        active = self.get_active_version(version.strategy_name)
        if active:
            active.is_active = False
            self._save_version(active)
        
        # Activate target
        version.is_active = True
        version.notes = f"Rolled back: {reason}" if reason else "Rolled back"
        self._save_version(version)
        
        return AcceptResult(version_id=target_version_id, status="accepted", message="Rolled back successfully")
    
    def resolve_effective_artifacts(self, version_id: str) -> dict[str, Any]:
        """
        Resolve effective code and parameters for a version.
        
        Returns dict with 'code_snapshot' and 'parameters_snapshot'
        """
        version = self.get_version_by_id(version_id)
        if version is None:
            return {"code_snapshot": None, "parameters_snapshot": None}
        
        return {
            "code_snapshot": version.code,
            "parameters_snapshot": version.parameters or {},
        }
    
    def _save_version(self, version: StrategyVersion) -> None:
        """Save version to disk."""
        path = resolve_safe(versions_dir(), f"{version.version_id}.json")
        data = {
            "version_id": version.version_id,
            "strategy_name": version.strategy_name,
            "change_type": version.change_type,
            "summary": version.summary,
            "created_by": version.created_by,
            "created_at": version.created_at,
            "code": version.code,
            "parameters": version.parameters,
            "source_ref": version.source_ref,
            "is_active": version.is_active,
            "accepted_at": version.accepted_at,
            "notes": version.notes,
            "backtest_runs": version.backtest_runs,
            "best_profit_pct": version.best_profit_pct,
        }
        write_json(path, data)


# Global instance
mutation_service = MutationService()
