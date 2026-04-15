"""
Test suite for optimizer checkpoint rollback implementation.

Verifies that:
1. Checkpoint loading works
2. ROLLBACK version is created with correct parameters
3. Version is promoted to ACTIVE status
4. Parameters are reactivated correctly
5. Audit trail is maintained
"""

import json
import os
from unittest.mock import MagicMock, patch
import pytest

from app.models.optimizer_models import ChangeType, MutationRequest, StrategyVersion, VersionStatus
from app.services.persistence_service import PersistenceService
from app.services.mutation_service import StrategyMutationService


@pytest.fixture
def tmp_paths(tmp_path):
    """Create necessary directory structure."""
    data_root = tmp_path / "data"
    versions_root = data_root / "versions"
    optimizer_runs_root = data_root / "optimizer_runs"
    
    versions_root.mkdir(parents=True, exist_ok=True)
    optimizer_runs_root.mkdir(parents=True, exist_ok=True)
    
    return {
        "data_root": data_root,
        "versions_root": versions_root,
        "optimizer_runs_root": optimizer_runs_root,
    }


@pytest.fixture
def patched_services(monkeypatch, tmp_paths):
    """Patch persistence and mutation services with temp paths."""
    from app.services import persistence_service as perse_module
    from app.services import mutation_service as mut_module
    from app.utils import paths as paths_module

    # Patch paths
    monkeypatch.setattr(paths_module, "optimizer_runs_dir", lambda: str(tmp_paths["optimizer_runs_root"]))
    monkeypatch.setattr(paths_module, "storage_dir", lambda: str(tmp_paths["data_root"]))
    monkeypatch.setattr(
        paths_module,
        "strategy_versions_dir",
        lambda strategy: str(tmp_paths["versions_root"] / strategy),
    )
    monkeypatch.setattr(
        paths_module,
        "strategy_version_file",
        lambda strategy, version_id: str(tmp_paths["versions_root"] / strategy / f"{version_id}.json"),
    )
    monkeypatch.setattr(
        paths_module,
        "strategy_active_version_file",
        lambda strategy: str(tmp_paths["versions_root"] / strategy / "active_version.json"),
    )

    # Create fresh service instances
    persistence = PersistenceService()
    mutation = StrategyMutationService()

    return {
        "persistence": persistence,
        "mutation": mutation,
        "paths": tmp_paths,
    }


def test_checkpoint_rollback_creates_rollback_version(patched_services):
    """Test that rollback creates a ROLLBACK version with correct metadata."""
    persistence = patched_services["persistence"]
    mutation = patched_services["mutation"]
    
    strategy_name = "TestStrat"
    run_id = "test-run-001"
    checkpoint_id = "epoch_0010_abc123"
    
    # Create checkpoint data
    checkpoint_data = {
        "checkpoint_id": checkpoint_id,
        "epoch": 10,
        "profit_pct": 5.25,
        "params": {"buy_threshold": 0.5, "sell_threshold": -0.5},
        "saved_at": "2026-04-15T10:30:00.000Z",
    }
    
    # Save checkpoint to disk
    checkpoint_path = patched_services["paths"]["optimizer_runs_root"] / run_id / "checkpoints"
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path / f"{checkpoint_id}.json", "w") as f:
        json.dump(checkpoint_data, f)
    
    # Save run metadata with strategy
    run_meta = {
        "run_id": run_id,
        "status": "started",
        "started_at": "2026-04-15T10:00:00.000Z",
        "payload": {"strategy": strategy_name},
    }
    persistence.save_optimizer_run(run_id, run_meta)
    
    # Create initial ACTIVE version (baseline)
    initial_version = mutation.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.INITIAL,
            summary="Initial version",
            created_by="test",
            code="# Initial strategy",
            parameters={"buy_threshold": 0.4, "sell_threshold": -0.4},
        )
    )
    initial_id = initial_version.version_id
    mutation.accept_version(initial_id)
    
    # Perform rollback
    result = persistence.rollback(run_id, checkpoint_id, strategy_name)
    
    # Verify result structure
    assert result.get("status") == "rolled_back", f"Status should be 'rolled_back', got: {result}"
    assert result.get("run_id") == run_id
    assert result.get("checkpoint_id") == checkpoint_id
    assert result.get("strategy_name") == strategy_name
    assert "version_id" in result
    assert "promoted_version" in result
    
    # Verify promoted version is ACTIVE
    promoted_version_dict = result.get("promoted_version", {})
    assert promoted_version_dict.get("status") == "active"
    assert promoted_version_dict.get("change_type") == "rollback"
    assert promoted_version_dict.get("source_ref") == checkpoint_id
    
    # Verify parameters were extracted and wrapped correctly
    params = promoted_version_dict.get("parameters_snapshot", {})
    assert params.get("hyperopt_params") == checkpoint_data["params"]
    assert params.get("profit_pct") == checkpoint_data["profit_pct"]
    
    # Verify source_context contains checkpoint metadata
    context = promoted_version_dict.get("source_context", {})
    assert context.get("run_id") == run_id
    assert context.get("epoch") == checkpoint_data["epoch"]
    assert context.get("profit_pct") == checkpoint_data["profit_pct"]


def test_checkpoint_rollback_reactivates_parameters(patched_services):
    """Test that rollback reactivates parameters from checkpoint."""
    persistence = patched_services["persistence"]
    mutation = patched_services["mutation"]
    
    strategy_name = "TestStrat"
    run_id = "test-run-002"
    checkpoint_id = "epoch_0020_def456"
    
    # Create checkpoint with specific parameters
    checkpoint_data = {
        "checkpoint_id": checkpoint_id,
        "epoch": 20,
        "profit_pct": 7.50,
        "params": {
            "buy_threshold": 0.7,
            "sell_threshold": -0.3,
            "rsi_period": 14,
        },
        "saved_at": "2026-04-15T11:00:00.000Z",
    }
    
    checkpoint_path = patched_services["paths"]["optimizer_runs_root"] / run_id / "checkpoints"
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path / f"{checkpoint_id}.json", "w") as f:
        json.dump(checkpoint_data, f)
    
    run_meta = {
        "run_id": run_id,
        "status": "started",
        "payload": {"strategy": strategy_name},
    }
    persistence.save_optimizer_run(run_id, run_meta)
    
    # Create and accept initial version
    initial = mutation.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.INITIAL,
            summary="Initial",
            created_by="test",
            code="# strategy",
            parameters={"buy_threshold": 0.5, "rsi_period": 30},
        )
    )
    mutation.accept_version(initial.version_id)
    
    # Rollback to checkpoint
    result = persistence.rollback(run_id, checkpoint_id, strategy_name)
    assert result.get("status") == "rolled_back"
    
    # Verify new version has checkpoint parameters
    promoted_version = result.get("promoted_version", {})
    effective_params = promoted_version.get("parameters_snapshot", {})
    
    assert effective_params["hyperopt_params"]["buy_threshold"] == 0.7
    assert effective_params["hyperopt_params"]["sell_threshold"] == -0.3
    assert effective_params["hyperopt_params"]["rsi_period"] == 14
    assert effective_params["profit_pct"] == 7.50


def test_checkpoint_rollback_missing_checkpoint_returns_error(patched_services):
    """Test that rollback returns error when checkpoint doesn't exist."""
    persistence = patched_services["persistence"]
    
    strategy_name = "TestStrat"
    run_id = "test-run-003"
    nonexistent_checkpoint_id = "epoch_9999_missing"
    
    run_meta = {
        "run_id": run_id,
        "status": "started",
        "payload": {"strategy": strategy_name},
    }
    persistence.save_optimizer_run(run_id, run_meta)
    
    result = persistence.rollback(run_id, nonexistent_checkpoint_id, strategy_name)
    
    assert result.get("status") == "error"
    assert "not found" in result.get("message", "").lower()


def test_checkpoint_rollback_maintains_audit_trail(patched_services):
    """Test that rollback version has proper audit events."""
    persistence = patched_services["persistence"]
    mutation = patched_services["mutation"]
    
    strategy_name = "TestStrat"
    run_id = "test-run-004"
    checkpoint_id = "epoch_0030_ghi789"
    
    checkpoint_data = {
        "checkpoint_id": checkpoint_id,
        "epoch": 30,
        "profit_pct": 6.0,
        "params": {"buy_threshold": 0.6},
        "saved_at": "2026-04-15T12:00:00.000Z",
    }
    
    checkpoint_path = patched_services["paths"]["optimizer_runs_root"] / run_id / "checkpoints"
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path / f"{checkpoint_id}.json", "w") as f:
        json.dump(checkpoint_data, f)
    
    run_meta = {
        "run_id": run_id,
        "status": "started",
        "payload": {"strategy": strategy_name},
    }
    persistence.save_optimizer_run(run_id, run_meta)
    
    # Create initial version
    initial = mutation.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.INITIAL,
            summary="Initial",
            created_by="test",
            code="# strategy",
        )
    )
    mutation.accept_version(initial.version_id)
    
    # Rollback
    result = persistence.rollback(run_id, checkpoint_id, strategy_name)
    promoted_version = result.get("promoted_version", {})
    
    # Verify audit events
    audit_events = promoted_version.get("audit_events", [])
    assert len(audit_events) >= 2  # created + accepted events
    
    # Find accepted event
    accepted_events = [e for e in audit_events if e.get("event_type") == "accepted"]
    assert len(accepted_events) >= 1
    assert "Rolled back" in accepted_events[0].get("note", "")


def test_checkpoint_rollback_endpoint_integration(patched_services, monkeypatch, tmp_path):
    """Integration test: verify router endpoint works with rollback logic."""
    from fastapi.testclient import TestClient
    from app.main import app
    
    persistence = patched_services["persistence"]
    mutation = patched_services["mutation"]
    
    # Patch the global services in main.py
    import app.main as main_module
    monkeypatch.setattr(main_module, "persistence", persistence)
    
    strategy_name = "TestStrat"
    run_id = "test-run-005"
    checkpoint_id = "epoch_0040_jkl012"
    
    # Setup
    checkpoint_data = {
        "checkpoint_id": checkpoint_id,
        "epoch": 40,
        "profit_pct": 8.0,
        "params": {"buy_threshold": 0.8},
        "saved_at": "2026-04-15T13:00:00.000Z",
    }
    
    checkpoint_path = patched_services["paths"]["optimizer_runs_root"] / run_id / "checkpoints"
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path / f"{checkpoint_id}.json", "w") as f:
        json.dump(checkpoint_data, f)
    
    run_meta = {
        "run_id": run_id,
        "status": "started",
        "payload": {"strategy": strategy_name},
    }
    persistence.save_optimizer_run(run_id, run_meta)
    
    # Create initial version
    initial = mutation.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.INITIAL,
            summary="Initial",
            created_by="test",
            code="# strategy",
        )
    )
    mutation.accept_version(initial.version_id)
    
    # Test endpoint
    client = TestClient(app)
    response = client.post(f"/api/optimizer/runs/{run_id}/rollback/{checkpoint_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "rolled_back"
    assert data.get("version_id")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
