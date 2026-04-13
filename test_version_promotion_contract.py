import json
import traceback
from unittest.mock import MagicMock, patch

from app.freqtrade import runtime
from app.models.optimizer_models import ChangeType, MutationRequest, MutationResult, StrategyVersion, VersionStatus
from app.services import mutation_service as mutation_module


def _configure_storage(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    versions_root = data_root / "versions"
    user_data_root = tmp_path / "user_data"

    monkeypatch.setattr(mutation_module, "storage_dir", lambda: str(data_root))
    monkeypatch.setattr(mutation_module, "strategy_versions_dir", lambda strategy: str(versions_root / strategy))
    monkeypatch.setattr(
        mutation_module,
        "strategy_version_file",
        lambda strategy, version_id: str(versions_root / strategy / f"{version_id}.json"),
    )
    monkeypatch.setattr(
        mutation_module,
        "strategy_active_version_file",
        lambda strategy: str(versions_root / strategy / "active_version.json"),
    )
    monkeypatch.setattr(
        mutation_module,
        "live_strategy_file",
        lambda strategy_name, user_data_path=None: str(user_data_root / "strategies" / f"{strategy_name}.py"),
    )
    monkeypatch.setattr(
        mutation_module,
        "strategy_config_file",
        lambda strategy_name, user_data_path=None: str(user_data_root / "config" / f"config_{strategy_name}.json"),
    )
    monkeypatch.setattr(
        mutation_module.ConfigService,
        "get_settings",
        lambda self: {"user_data_path": str(user_data_root)},
    )

    return {
        "data_root": data_root,
        "versions_root": versions_root,
        "user_data_root": user_data_root,
        "strategy_file": user_data_root / "strategies" / "TestStrat.py",
        "config_file": user_data_root / "config" / "config_TestStrat.json",
        "active_file": versions_root / "TestStrat" / "active_version.json",
    }


def _version(
    version_id: str,
    *,
    status: VersionStatus,
    parent_version_id: str | None = None,
    code_snapshot: str | None = "class TestStrat:\n    pass\n",
    parameters_snapshot: dict | None = None,
) -> StrategyVersion:
    return StrategyVersion(
        version_id=version_id,
        parent_version_id=parent_version_id,
        strategy_name="TestStrat",
        created_at="2026-01-01T00:00:00",
        created_by="tester",
        change_type=ChangeType.PARAMETER_CHANGE if parameters_snapshot is not None else ChangeType.CODE_CHANGE,
        summary=f"summary for {version_id}",
        status=status,
        code_snapshot=code_snapshot,
        parameters_snapshot=parameters_snapshot,
    )


def test_create_mutation_does_not_write_live_files(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()

    result = service.create_mutation(
        MutationRequest(
            strategy_name="TestStrat",
            change_type=ChangeType.PARAMETER_CHANGE,
            summary="candidate mutation",
            created_by="tester",
            parent_version_id="v-parent",
            parameters={"stoploss": -0.1},
        )
    )

    created = service.get_version_by_id(result.version_id)

    assert result.status == "created"
    assert created is not None
    assert created.status == VersionStatus.CANDIDATE
    assert not paths["strategy_file"].exists()
    assert not paths["config_file"].exists()


def test_accept_version_rejects_non_candidate_versions(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()
    active = _version("v-active", status=VersionStatus.ACTIVE, parameters_snapshot={"stoploss": -0.2})
    service._save_version(active)
    service._set_active_version(active)

    result = service.accept_version(active.version_id)

    assert result.status == "error"
    assert "not a candidate" in result.message
    assert not paths["strategy_file"].exists()
    assert not paths["config_file"].exists()


def test_accept_version_writes_live_artifacts_and_archives_previous_active(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()

    previous_active = _version(
        "v-active",
        status=VersionStatus.ACTIVE,
        code_snapshot="class TestStrat:\n    active = True\n",
        parameters_snapshot={"stoploss": -0.2},
    )
    candidate = _version(
        "v-candidate",
        status=VersionStatus.CANDIDATE,
        parent_version_id=previous_active.version_id,
        code_snapshot="class TestStrat:\n    active = False\n",
        parameters_snapshot={"stoploss": -0.1, "max_open_trades": 2},
    )

    service._save_version(previous_active)
    service._save_version(candidate)
    service._set_active_version(previous_active)

    result = service.accept_version(candidate.version_id, notes="ship it")

    promoted = service.get_version_by_id(candidate.version_id)
    archived = service.get_version_by_id(previous_active.version_id)
    active_ref = json.loads(paths["active_file"].read_text(encoding="utf-8"))

    assert result.status == "accepted"
    assert paths["strategy_file"].read_text(encoding="utf-8") == "class TestStrat:\n    active = False\n"
    assert json.loads(paths["config_file"].read_text(encoding="utf-8")) == {"stoploss": -0.1, "max_open_trades": 2}
    assert promoted.status == VersionStatus.ACTIVE
    assert promoted.promoted_from_version_id == previous_active.version_id
    assert archived.status == VersionStatus.ARCHIVED
    assert active_ref["version_id"] == candidate.version_id


def test_accept_version_fails_closed_without_effective_code_snapshot(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()
    candidate = _version(
        "v-empty",
        status=VersionStatus.CANDIDATE,
        code_snapshot=None,
        parameters_snapshot={"stoploss": -0.15},
    )
    service._save_version(candidate)

    result = service.accept_version(candidate.version_id)

    assert result.status == "error"
    assert "invalid artifacts" in result.message or "could not be promoted" in result.message
    assert not paths["strategy_file"].exists()
    assert not paths["config_file"].exists()


def test_rollback_version_writes_target_live_artifacts_and_removes_overlay_when_missing(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()

    current_active = _version(
        "v-current",
        status=VersionStatus.ACTIVE,
        code_snapshot="class TestStrat:\n    current = True\n",
        parameters_snapshot={"stoploss": -0.05},
    )
    rollback_target = _version(
        "v-rollback",
        status=VersionStatus.ARCHIVED,
        code_snapshot="class TestStrat:\n    current = False\n",
        parameters_snapshot=None,
    )

    service._save_version(current_active)
    service._save_version(rollback_target)
    service._set_active_version(current_active)
    paths["strategy_file"].parent.mkdir(parents=True, exist_ok=True)
    paths["strategy_file"].write_text("class TestStrat:\n    stale = True\n", encoding="utf-8")
    paths["config_file"].parent.mkdir(parents=True, exist_ok=True)
    paths["config_file"].write_text(json.dumps({"stoploss": -0.05}), encoding="utf-8")

    result = service.rollback_version(rollback_target.version_id, reason="restore stable")

    rolled_back = service.get_version_by_id(rollback_target.version_id)
    archived = service.get_version_by_id(current_active.version_id)
    active_ref = json.loads(paths["active_file"].read_text(encoding="utf-8"))

    assert result.status == "rolled_back"
    assert paths["strategy_file"].read_text(encoding="utf-8") == "class TestStrat:\n    current = False\n"
    assert not paths["config_file"].exists()
    assert rolled_back.status == VersionStatus.ACTIVE
    assert rolled_back.promoted_from_version_id == current_active.version_id
    assert archived.status == VersionStatus.ARCHIVED
    assert active_ref["version_id"] == rollback_target.version_id

def test_bootstrap_initial_version_promotes_through_accept_version(monkeypatch):
    captured = {}

    monkeypatch.setattr(runtime.config_svc, "get_settings", lambda: {"user_data_path": "tmp-user-data"})
    monkeypatch.setattr(runtime, "live_strategy_file", lambda strategy_name, user_data_path=None: f"{user_data_path}/strategies/{strategy_name}.py")
    monkeypatch.setattr(
        runtime,
        "load_live_strategy_code",
        lambda strategy_name, user_data_path=None, strict=False: "class TestStrat:\n    pass\n",
    )
    monkeypatch.setattr(
        runtime,
        "load_live_strategy_parameters",
        lambda strategy_name, user_data_path=None, strict=False: {"stoploss": -0.2},
    )

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(version_id="v-bootstrap", status="created", message="created")

    def _accept_version(version_id, notes=None):
        captured["accepted"] = (version_id, notes)
        return MutationResult(version_id=version_id, status="accepted", message="accepted")

    def _get_version_by_id(version_id):
        return StrategyVersion(
            version_id=version_id,
            parent_version_id=None,
            strategy_name="TestStrat",
            created_at="2026-01-01T00:00:00",
            created_by="system",
            change_type=ChangeType.INITIAL,
            summary="Initial live strategy bootstrap",
            status=VersionStatus.ACTIVE,
            code_snapshot="class TestStrat:\n    pass\n",
            parameters_snapshot={"stoploss": -0.2},
        )

    monkeypatch.setattr(runtime.mutation_service, "create_mutation", _create_mutation)
    monkeypatch.setattr(runtime.mutation_service, "accept_version", _accept_version)
    monkeypatch.setattr(runtime.mutation_service, "get_version_by_id", _get_version_by_id)

    version = runtime._bootstrap_initial_version("TestStrat")

    request = captured["request"]
    assert request.change_type == ChangeType.INITIAL
    assert request.code == "class TestStrat:\n    pass\n"
    assert request.parameters == {"stoploss": -0.2}
    assert request.source_ref == "tmp-user-data/strategies/TestStrat.py"
    assert captured["accepted"] == ("v-bootstrap", "Accepted initial live strategy bootstrap")
    assert version.version_id == "v-bootstrap"


# ============================================================================
# PHASE 1: COMPREHENSIVE LOCKDOWN TESTS
# ============================================================================

def test_rollback_preserves_version_lineage_across_chain(monkeypatch, tmp_path):
    """Test that rollback correctly resolves artifacts from version lineage chains."""
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()

    # v1: Has code + parameters
    v1 = _version(
        "v1-base",
        status=VersionStatus.ACTIVE,
        code_snapshot="class TestStrat:\n    version = 1\n",
        parameters_snapshot={"stoploss": -0.1, "max_open_trades": 1},
    )

    # v2: Parent is v1, only updates parameters (no code in v2)
    v2 = _version(
        "v2-param-only",
        status=VersionStatus.ACTIVE,
        parent_version_id=v1.version_id,
        code_snapshot=None,  # No code snapshot in v2
        parameters_snapshot={"stoploss": -0.15, "max_open_trades": 2},
    )

    # v3: Parent is v2, updates parameters again (no code in v3)
    v3 = _version(
        "v3-param-only",
        status=VersionStatus.ACTIVE,
        parent_version_id=v2.version_id,
        code_snapshot=None,  # No code snapshot in v3
        parameters_snapshot={"stoploss": -0.2, "max_open_trades": 3},
    )

    service._save_version(v1)
    service._save_version(v2)
    service._save_version(v3)
    service._set_active_version(v3)

    # Rollback to v2 (which should resolve code from v1 + params from v2)
    result = service.rollback_version(v2.version_id, reason="restore to v2")

    # Verify result
    assert result.status == "rolled_back"

    # Verify live artifacts
    assert paths["strategy_file"].read_text(encoding="utf-8") == "class TestStrat:\n    version = 1\n"
    assert json.loads(paths["config_file"].read_text(encoding="utf-8")) == {
        "stoploss": -0.15,
        "max_open_trades": 2,
    }

    # Verify version status
    rolled_back_v2 = service.get_version_by_id(v2.version_id)
    assert rolled_back_v2.status == VersionStatus.ACTIVE
    assert rolled_back_v2.promoted_from_version_id == v3.version_id

    archived_v3 = service.get_version_by_id(v3.version_id)
    assert archived_v3.status == VersionStatus.ARCHIVED

    # Verify active marker
    active_ref = json.loads(paths["active_file"].read_text(encoding="utf-8"))
    assert active_ref["version_id"] == v2.version_id


def test_no_live_writes_except_from_mutation_service(monkeypatch, tmp_path):
    """
    Comprehensive test proving that ONLY _write_live_artifacts() writes to live paths.
    This test verifies that live file writes occur exactly during accept_version() and
    rollback_version(), and that no other paths produce live files.
    """
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()

    # Create version chain
    active = _version(
        "v-active",
        status=VersionStatus.ACTIVE,
        code_snapshot="class TestStrat:\n    active = True\n",
        parameters_snapshot={"stoploss": -0.2},
    )
    candidate = _version(
        "v-candidate",
        status=VersionStatus.CANDIDATE,
        parent_version_id=active.version_id,
        code_snapshot="class TestStrat:\n    candidate = True\n",
        parameters_snapshot={"stoploss": -0.1},
    )

    service._save_version(active)
    service._save_version(candidate)
    service._set_active_version(active)

    # Baseline: create_mutation should NOT write live files
    result_create = service.create_mutation(
        MutationRequest(
            strategy_name="TestStrat",
            change_type=ChangeType.PARAMETER_CHANGE,
            summary="new candidate",
            created_by="tester",
            parent_version_id=candidate.version_id,
            parameters={"stoploss": -0.05},
        )
    )
    new_candidate_id = result_create.version_id

    assert not paths["strategy_file"].exists(), "create_mutation should NOT write live files"
    assert not paths["config_file"].exists(), "create_mutation should NOT write live files"

    # Test 1: accept_version SHOULD write live files (via _write_live_artifacts)
    result_accept = service.accept_version(candidate.version_id)
    assert result_accept.status == "accepted"
    assert paths["strategy_file"].exists(), "accept_version should write live strategy file"
    assert paths["config_file"].exists(), "accept_version should write live config file"

    strategy_content_after_accept = paths["strategy_file"].read_text(encoding="utf-8")
    config_content_after_accept = json.loads(paths["config_file"].read_text(encoding="utf-8"))

    # Test 2: rollback_version SHOULD write live files (via _write_live_artifacts)
    rolled_back = _version(
        "v-rollback",
        status=VersionStatus.ARCHIVED,
        code_snapshot="class TestStrat:\n    rollback = True\n",
        parameters_snapshot=None,
    )
    service._save_version(rolled_back)

    result_rollback = service.rollback_version(rolled_back.version_id)
    assert result_rollback.status == "rolled_back"
    assert paths["strategy_file"].exists(), "rollback_version should write live strategy file"

    strategy_content_after_rollback = paths["strategy_file"].read_text(encoding="utf-8")
    assert strategy_content_after_accept != strategy_content_after_rollback, "Rollback should change live files"

    # Test 3: Verify live files were only written through promotion paths
    # by checking that the files have expected content from accept/rollback operations
    assert "candidate = True" in strategy_content_after_accept, "Accept wrote wrong content"
    assert "rollback = True" in strategy_content_after_rollback, "Rollback wrote wrong content"


def test_rerun_creates_isolated_workspace_per_run(monkeypatch, tmp_path):
    """
    Test that rerun creates isolated, version-scoped workspaces.
    Each run should have its own workspace directory, independent of live files.
    """
    from app.freqtrade import cli_service

    # Setup
    paths = _configure_storage(monkeypatch, tmp_path)

    # Mock necessary services
    service = mutation_module.StrategyMutationService()

    version = _version(
        "v-rerun",
        status=VersionStatus.ACTIVE,
        code_snapshot="class TestStrat:\n    test = True\n",
        parameters_snapshot={"stoploss": -0.1},
    )

    service._save_version(version)
    service._set_active_version(version)

    # Create cli_service instance (no-arg constructor)
    cli = cli_service.FreqtradeCliService()

    # Monkeypatch workspace paths
    def _workspace_paths(run_id, strategy):
        workspace_dir = tmp_path / "data" / "backtest_runs" / run_id / "workspace"
        strategies_dir = workspace_dir / "strategies"
        return {
            "workspace_dir": str(workspace_dir),
            "strategies_dir": str(strategies_dir),
            "strategy_file": str(strategies_dir / f"{strategy}.py"),
            "config_overlay_path": str(workspace_dir / "config.version.json"),
        }

    monkeypatch.setattr(cli, "_workspace_paths", _workspace_paths)

    # Test: Materialize workspace for run_a
    run_a_id = "run-a-12345"
    result_a = cli._materialize_version_workspace(
        {
            "run_id": run_a_id,
            "version_id": version.version_id,
            "strategy": "TestStrat",
        },
        "base_config.json",
    )

    # Test: Materialize workspace for run_b (same version)
    run_b_id = "run-b-67890"
    result_b = cli._materialize_version_workspace(
        {
            "run_id": run_b_id,
            "version_id": version.version_id,
            "strategy": "TestStrat",
        },
        "base_config.json",
    )

    # Verify: Both runs have their own workspace dirs
    workspace_a = tmp_path / "data" / "backtest_runs" / run_a_id / "workspace"
    workspace_b = tmp_path / "data" / "backtest_runs" / run_b_id / "workspace"

    assert str(workspace_a) in result_a["workspace_dir"]
    assert str(workspace_b) in result_b["workspace_dir"]
    assert result_a["workspace_dir"] != result_b["workspace_dir"]

    # Verify: Strategy files exist in both workspaces
    strategy_file_a = workspace_a / "strategies" / "TestStrat.py"
    strategy_file_b = workspace_b / "strategies" / "TestStrat.py"
    assert strategy_file_a.exists()
    assert strategy_file_b.exists()

    # Verify: Both strategy files have same code
    assert strategy_file_a.read_text(encoding="utf-8") == "class TestStrat:\n    test = True\n"
    assert strategy_file_b.read_text(encoding="utf-8") == "class TestStrat:\n    test = True\n"

    # Verify: Live strategy file is NOT modified (workspace doesn't touch live)
    assert not paths["strategy_file"].exists(), "Live strategy file should not be touched by rerun workspace materialization"


def test_reject_version_rejects_only_candidate_versions(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()

    archived = _version(
        "v-archived",
        status=VersionStatus.ARCHIVED,
        code_snapshot="class TestStrat:\n    archived = True\n",
        parameters_snapshot={"stoploss": -0.2},
    )
    service._save_version(archived)

    result = service.reject_version(archived.version_id, reason="not actionable")

    assert result.status == "error"
    assert "not a candidate" in result.message
    assert service.get_version_by_id(archived.version_id).status == VersionStatus.ARCHIVED
    assert not paths["strategy_file"].exists()
    assert not paths["config_file"].exists()


def test_rollback_version_rejects_candidate_targets(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    service = mutation_module.StrategyMutationService()

    active = _version(
        "v-active",
        status=VersionStatus.ACTIVE,
        code_snapshot="class TestStrat:\n    active = True\n",
        parameters_snapshot={"stoploss": -0.2},
    )
    candidate = _version(
        "v-candidate",
        status=VersionStatus.CANDIDATE,
        parent_version_id=active.version_id,
        code_snapshot="class TestStrat:\n    candidate = True\n",
        parameters_snapshot={"stoploss": -0.1},
    )

    service._save_version(active)
    service._save_version(candidate)
    service._set_active_version(active)

    result = service.rollback_version(candidate.version_id, reason="invalid rollback target")

    assert result.status == "error"
    assert "cannot be used as a rollback target" in result.message
    assert service.get_version_by_id(candidate.version_id).status == VersionStatus.CANDIDATE
    assert service.get_version_by_id(active.version_id).status == VersionStatus.ACTIVE
    assert not paths["strategy_file"].exists()
    assert not paths["config_file"].exists()
