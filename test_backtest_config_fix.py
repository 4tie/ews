import json
import os
from types import SimpleNamespace

from app.freqtrade import commands as commands_module
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


def test_prepare_backtest_run_uses_workspace_strategy_path_and_stacked_configs(tmp_path, monkeypatch):
    service = FreqtradeCliService()
    base_config_path = tmp_path / "base.config.json"
    base_config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(service, "_workspace_paths", _workspace_paths_factory(tmp_path))
    monkeypatch.setattr(service, "_freqtrade_path", lambda: "")
    monkeypatch.setattr(service, "_backtest_artifact_paths", lambda strategy, run_id: {
        "log_file": str(tmp_path / f"{run_id}.log"),
        "raw_result_dir": str(tmp_path / "results"),
        "raw_result_path": None,
    })
    monkeypatch.setattr(commands_module, "resolve_freqtrade_executable", lambda freqtrade_path: "freqtrade")
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
            "parameters_snapshot": {"stoploss": -0.1},
        },
    )

    prepared = service.prepare_backtest_run(
        {
            "run_id": "bt-test-789",
            "strategy": "TestStrat",
            "timeframe": "5m",
            "config_path": str(base_config_path),
            "version_id": "v-test-789",
            "pairs": ["BTC/USDT"],
            "extra_flags": [],
        }
    )

    cmd = prepared["cmd"]
    config_values = [cmd[index + 1] for index, token in enumerate(cmd) if token == "--config"]

    assert config_values == [str(base_config_path), prepared["config_overlay_path"]]
    assert "--strategy-path" in cmd
    assert cmd[cmd.index("--strategy-path") + 1] == prepared["strategy_path"]
    assert prepared["strategy_path"].endswith(os.path.join("bt-test-789", "workspace", "strategies"))
