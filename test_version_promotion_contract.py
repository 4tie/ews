import json

from app.models.optimizer_models import ChangeType, MutationRequest, StrategyVersion, VersionStatus
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
    assert "could not be promoted" in result.message
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
