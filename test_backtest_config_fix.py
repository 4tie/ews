import json
import os
from types import SimpleNamespace

from app.freqtrade.cli_service import FreqtradeCliService
from app.services.mutation_service import mutation_service


def _workspace_paths_factory(tmp_path):
    def _workspace_paths(run_id: str, strategy: str) -> dict[str, str]:
        workspace_dir = tmp_path / run_id / "workspace"
        strategies_dir = workspace_dir / "strategies"
        return {
            "workspace_dir": str(workspace_dir),
            "strategies_dir": str(strategies_dir),
            "strategy_file": str(strategies_dir / f"{strategy}.py"),
            "config_overlay_path": str(workspace_dir / "config.version.json"),
        }

    return _workspace_paths


def test_materialize_version_workspace_without_parameters_uses_only_base_config(tmp_path, monkeypatch):
    service = FreqtradeCliService()
    base_config_path = tmp_path / "config.json"
    base_config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(service, "_workspace_paths", _workspace_paths_factory(tmp_path))
    monkeypatch.setattr(
        mutation_service,
        "get_version_by_id",
        lambda version_id: SimpleNamespace(strategy_name="TestStrat"),
    )
    monkeypatch.setattr(
        mutation_service,
        "resolve_effective_artifacts",
        lambda version_id: {
            "strategy_name": "TestStrat",
            "code_snapshot": "class TestStrat:\n    pass\n",
            "parameters_snapshot": {},
        },
    )

    result = service._materialize_version_workspace(
        {
            "run_id": "bt-test-123",
            "strategy": "TestStrat",
            "version_id": "v-test-123",
        },
        str(base_config_path),
    )

    assert result["config_paths"] == [str(base_config_path)]
    assert result["request_config_path"] == str(base_config_path)
    assert result["config_overlay_path"] is None
    assert os.path.isfile(result["strategy_file"])


def test_materialize_version_workspace_with_parameters_adds_overlay_config(tmp_path, monkeypatch):
    service = FreqtradeCliService()
    base_config_path = tmp_path / "config.json"
    base_config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(service, "_workspace_paths", _workspace_paths_factory(tmp_path))
    monkeypatch.setattr(
        mutation_service,
        "get_version_by_id",
        lambda version_id: SimpleNamespace(strategy_name="TestStrat"),
    )
    monkeypatch.setattr(
        mutation_service,
        "resolve_effective_artifacts",
        lambda version_id: {
            "strategy_name": "TestStrat",
            "code_snapshot": "class TestStrat:\n    pass\n",
            "parameters_snapshot": {"stoploss": -0.1, "nested": {"enabled": True}},
        },
    )

    result = service._materialize_version_workspace(
        {
            "run_id": "bt-test-456",
            "strategy": "TestStrat",
            "version_id": "v-test-456",
        },
        str(base_config_path),
    )

    assert result["config_paths"] == [str(base_config_path), result["config_overlay_path"]]
    assert result["config_overlay_path"] is not None
    with open(result["config_overlay_path"], "r", encoding="utf-8") as handle:
        overlay = json.load(handle)
    assert overlay == {"stoploss": -0.1, "nested": {"enabled": True}}