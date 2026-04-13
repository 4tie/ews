import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.freqtrade import runtime
from app.main import app
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource
from app.models.optimizer_models import ChangeType, StrategyVersion, VersionStatus
from app.routers import backtest as backtest_router
from app.services import mutation_service as mutation_module
from app.services import persistence_service as persistence_module
from app.services import results_service as results_module


client = TestClient(app)


class FakeBacktestEngine:
    engine_id = "freqtrade"

    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.launches: list[dict] = []

    def list_strategies(self) -> list[str]:
        return ["TestStrat"]

    def prepare_backtest_run(self, payload: dict) -> dict:
        run_id = payload["run_id"]
        return {
            "command": f"freqtrade backtesting --strategy {payload['strategy']}",
            "raw_result_path": str(self.results_dir / f"{run_id}.zip"),
            "request_config_path": str(self.results_dir / f"{run_id}.config.json"),
        }

    def run_backtest(self, payload: dict, prepared: dict | None = None) -> dict:
        self.launches.append(dict(payload))
        prepared = prepared or {}
        run_id = payload["run_id"]
        return {
            "command": prepared.get("command") or f"freqtrade backtesting --strategy {payload['strategy']}",
            "run_record_log_path": str(self.results_dir / f"{run_id}.log"),
            "raw_result_path": prepared.get("raw_result_path") or str(self.results_dir / f"{run_id}.zip"),
            "pid": None,
        }


def _configure_storage(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    versions_root = data_root / "versions"
    user_data_root = tmp_path / "user_data"
    results_root = user_data_root / "backtest_results"

    monkeypatch.setattr(mutation_module.mutation_service, "_cache", {})
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

    monkeypatch.setattr(persistence_module, "backtest_runs_dir", lambda: str(data_root / "backtest_runs"))
    monkeypatch.setattr(persistence_module, "download_runs_dir", lambda: str(data_root / "download_runs"))
    monkeypatch.setattr(persistence_module, "optimizer_runs_dir", lambda: str(data_root / "optimizer_runs"))
    monkeypatch.setattr(results_module, "strategy_results_dir", lambda strategy, user_data_path=None: str(results_root / strategy))
    monkeypatch.setattr(results_module, "user_data_results_dir", lambda user_data_path=None: str(results_root))

    paths = {
        "data_root": data_root,
        "user_data_root": user_data_root,
        "results_dir": results_root / "TestStrat",
        "strategy_file": user_data_root / "strategies" / "TestStrat.py",
        "config_file": user_data_root / "config" / "config_TestStrat.json",
    }
    paths["results_dir"].mkdir(parents=True, exist_ok=True)
    return paths


def _summary_payload(profit_total_pct: float, profit_total_abs: float, trades: int, wins: int) -> dict:
    return {
        "TestStrat": {
            "strategy_name": "TestStrat",
            "timeframe": "5m",
            "timerange": "20260101-20260102",
            "results_per_pair": [
                {
                    "key": "BTC/USDT",
                    "profit_total_pct": profit_total_pct,
                    "profit_total_abs": profit_total_abs,
                    "trades": trades,
                    "wins": wins,
                    "winrate": wins / trades if trades else 0,
                    "max_drawdown_account": 0.03,
                },
                {
                    "key": "TOTAL",
                    "profit_total_pct": profit_total_pct,
                    "profit_total_abs": profit_total_abs,
                    "trades": trades,
                    "wins": wins,
                    "winrate": wins / trades if trades else 0,
                    "max_drawdown_account": 0.04,
                    "sharpe": 1.0,
                    "sortino": 1.1,
                    "calmar": 0.9,
                },
            ],
            "trades": [
                {
                    "open_date": "2026-01-01T00:00:00",
                    "close_date": "2026-01-01T01:00:00",
                }
            ],
        }
    }


def _request_snapshot() -> dict:
    return {
        "strategy": "TestStrat",
        "timeframe": "5m",
        "timerange": "20260101-20260102",
        "pairs": ["BTC/USDT"],
        "exchange": "binance",
        "max_open_trades": 2,
        "dry_run_wallet": 1000,
        "extra_flags": [],
        "config_path": None,
        "engine": "freqtrade",
        "trigger_source": "manual",
    }


def _save_completed_run(run_id: str, version_id: str, summary_path: Path) -> None:
    run = BacktestRunRecord(
        run_id=run_id,
        engine="freqtrade",
        strategy="TestStrat",
        version_id=version_id,
        request_snapshot=_request_snapshot(),
        request_snapshot_schema_version=1,
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:05:00",
        completed_at="2026-01-01T00:05:00",
        status=BacktestRunStatus.COMPLETED,
        command="freqtrade backtesting --strategy TestStrat",
        raw_result_path=str(summary_path.with_suffix(".zip")),
        summary_path=str(summary_path),
    )
    runtime.persistence.save_backtest_run(run_id, run.model_dump(mode="json"))


def _seed_active_baseline(paths: dict) -> None:
    baseline = StrategyVersion(
        version_id="v-baseline",
        parent_version_id=None,
        strategy_name="TestStrat",
        created_at="2026-01-01T00:00:00",
        created_by="tester",
        change_type=ChangeType.INITIAL,
        summary="Baseline version",
        status=VersionStatus.ACTIVE,
        code_snapshot="class TestStrat:\n    stoploss = -0.2\n",
        parameters_snapshot={
            "stoploss": -0.2,
            "trailing_stop": False,
            "trailing_stop_positive": 0.02,
        },
    )
    service = mutation_module.mutation_service
    service._save_version(baseline)
    service._set_active_version(baseline)
    service._write_live_artifacts(baseline.version_id)

    assert paths["strategy_file"].exists()
    assert paths["config_file"].exists()


def _patch_diagnosis(monkeypatch):
    def _diagnose_run(**kwargs):
        run = kwargs["run_record"]
        if run.run_id == "bt-baseline":
            return {
                "primary_flags": [{"rule": "high_drawdown", "severity": "warning", "message": "Drawdown is high."}],
                "ranked_issues": [{"rule": "high_drawdown", "severity": "warning", "message": "Drawdown is high."}],
                "parameter_hints": [],
                "proposal_actions": [
                    {
                        "action_type": "tighten_stoploss",
                        "label": "Tighten Stoploss",
                        "matched_rules": ["high_drawdown"],
                        "parameters": ["stoploss", "trailing_stop"],
                    }
                ],
                "facts": {
                    "worst_pair": "BTC/USDT",
                    "worst_pair_profit_pct": -2.0,
                    "worst_pair_trades": 8,
                },
            }
        return {
            "primary_flags": [],
            "ranked_issues": [],
            "parameter_hints": [],
            "proposal_actions": [],
            "facts": {
                "worst_pair": "BTC/USDT",
                "worst_pair_profit_pct": 1.0,
                "worst_pair_trades": 10,
            },
        }

    monkeypatch.setattr(runtime.diagnosis_service, "diagnose_run", _diagnose_run)
    monkeypatch.setattr(results_module.diagnosis_service, "diagnose_run", _diagnose_run)


def test_backtest_workflow_loop_from_diagnosis_to_rollback(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    _seed_active_baseline(paths)
    _patch_diagnosis(monkeypatch)

    fake_engine = FakeBacktestEngine(paths["results_dir"])
    monkeypatch.setattr(backtest_router, "_resolve_engine", lambda: fake_engine)

    baseline_summary = paths["results_dir"] / "bt-baseline.summary.json"
    baseline_summary.write_text(json.dumps(_summary_payload(1.0, 100.0, 8, 5)), encoding="utf-8")
    _save_completed_run("bt-baseline", "v-baseline", baseline_summary)

    baseline_live_code = paths["strategy_file"].read_text(encoding="utf-8")
    baseline_live_config = json.loads(paths["config_file"].read_text(encoding="utf-8"))

    diagnosis_response = client.get("/api/backtest/runs/bt-baseline/diagnosis")
    assert diagnosis_response.status_code == 200
    diagnosis = diagnosis_response.json()
    assert diagnosis["diagnosis_status"] == "ready"
    assert diagnosis["summary_available"] is True
    assert diagnosis["version_id"] == "v-baseline"
    assert diagnosis["diagnosis"]["proposal_actions"][0]["action_type"] == "tighten_stoploss"

    candidate_response = client.post(
        "/api/backtest/runs/bt-baseline/proposal-candidates",
        json={
            "source_kind": "deterministic_action",
            "source_index": 0,
            "candidate_mode": "auto",
            "action_type": "tighten_stoploss",
        },
    )
    assert candidate_response.status_code == 200
    candidate_payload = candidate_response.json()
    candidate_version_id = candidate_payload["candidate_version_id"]
    assert candidate_payload["baseline_run_id"] == "bt-baseline"
    assert candidate_payload["baseline_version_id"] == "v-baseline"
    assert candidate_payload["baseline_run_version_id"] == "v-baseline"
    assert candidate_payload["baseline_version_source"] == "run"
    assert candidate_payload["candidate_status"] == "candidate"

    candidate_version = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
    assert candidate_version is not None
    assert candidate_version.parent_version_id == "v-baseline"
    assert candidate_version.status == VersionStatus.CANDIDATE
    assert candidate_version.source_kind == "deterministic_action"
    assert candidate_version.source_context["run_id"] == "bt-baseline"
    assert candidate_version.source_context["action_type"] == "tighten_stoploss"
    assert candidate_version.parameters_snapshot["stoploss"] == -0.15
    assert candidate_version.parameters_snapshot["trailing_stop"] is True
    assert [event.event_type for event in candidate_version.audit_events] == ["created"]
    assert candidate_version.audit_events[0].actor == candidate_version.created_by
    assert candidate_version.audit_events[0].note is None
    assert candidate_version.audit_events[0].from_version_id is None

    assert paths["strategy_file"].read_text(encoding="utf-8") == baseline_live_code
    assert json.loads(paths["config_file"].read_text(encoding="utf-8")) == baseline_live_config

    rerun_response = client.post(
        "/api/backtest/run",
        json={
            "strategy": "TestStrat",
            "timeframe": "5m",
            "timerange": "20260101-20260102",
            "pairs": ["BTC/USDT"],
            "exchange": "binance",
            "max_open_trades": 2,
            "dry_run_wallet": 1000,
            "extra_flags": [],
            "version_id": candidate_version_id,
            "trigger_source": "ai_apply",
        },
    )
    assert rerun_response.status_code == 200
    rerun_payload = rerun_response.json()
    candidate_run_id = rerun_payload["run_id"]
    assert rerun_payload["version_id"] == candidate_version_id
    assert rerun_payload["trigger_source"] == "ai_apply"
    assert fake_engine.launches[-1]["version_id"] == candidate_version_id
    assert fake_engine.launches[-1]["trigger_source"] == "ai_apply"

    candidate_run = runtime.persistence.load_backtest_run(candidate_run_id)
    assert candidate_run["version_id"] == candidate_version_id
    assert candidate_run["trigger_source"] == "ai_apply"

    assert paths["strategy_file"].read_text(encoding="utf-8") == baseline_live_code
    assert json.loads(paths["config_file"].read_text(encoding="utf-8")) == baseline_live_config

    candidate_summary = paths["results_dir"] / f"{candidate_run_id}.summary.json"
    candidate_summary.write_text(json.dumps(_summary_payload(2.5, 125.0, 10, 7)), encoding="utf-8")
    candidate_run.update(
        {
            "status": "completed",
            "updated_at": "2026-01-01T00:20:00",
            "completed_at": "2026-01-01T00:20:00",
            "summary_path": str(candidate_summary),
            "raw_result_path": str(candidate_summary.with_suffix(".zip")),
            "exit_code": 0,
            "error": None,
        }
    )
    runtime.persistence.save_backtest_run(candidate_run_id, candidate_run)
    mutation_module.mutation_service.link_backtest(candidate_version_id, candidate_run_id, 2.5)

    compare_response = client.get(
        "/api/backtest/compare",
        params={"left_run_id": "bt-baseline", "right_run_id": candidate_run_id},
    )
    assert compare_response.status_code == 200
    comparison = compare_response.json()
    profit_row = next(row for row in comparison["metrics"] if row["key"] == "profit_total_pct")
    assert comparison["left"]["summary_available"] is True
    assert comparison["right"]["summary_available"] is True
    assert profit_row["left"] == 1.0
    assert profit_row["right"] == 2.5
    assert profit_row["delta"] == 1.5
    assert comparison["versions"] == {
        "baseline_version_id": "v-baseline",
        "candidate_version_id": candidate_version_id,
        "candidate_parent_version_id": "v-baseline",
        "baseline_version_source": "run",
    }
    assert comparison["version_diff"]["source_kind"] == "deterministic_action"
    assert comparison["version_diff"]["source_title"] == "Tighten Stoploss"
    assert comparison["version_diff"]["candidate_mode"] == "parameter_only"
    assert any(row["path"] == "stoploss" for row in comparison["version_diff"]["parameter_diff_rows"])
    code_diff = comparison["version_diff"]["code_diff"]
    assert "preview_blocks" in code_diff
    assert "preview_truncated" in code_diff
    assert code_diff["preview_blocks"] == []
    assert code_diff["preview_truncated"] is False

    accept_response = client.post(
        "/api/versions/TestStrat/accept",
        json={"version_id": candidate_version_id, "notes": "Accept candidate from workflow loop test"},
    )
    assert accept_response.status_code == 200
    assert accept_response.json()["status"] == "accepted"
    assert paths["strategy_file"].read_text(encoding="utf-8") == baseline_live_code
    accepted_config = json.loads(paths["config_file"].read_text(encoding="utf-8"))
    assert accepted_config["stoploss"] == -0.15
    assert accepted_config["trailing_stop"] is True
    accepted_candidate = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
    assert accepted_candidate.status == VersionStatus.ACTIVE
    assert mutation_module.mutation_service.get_version_by_id("v-baseline").status == VersionStatus.ARCHIVED
    accepted_event = accepted_candidate.audit_events[-1]
    assert accepted_event.event_type == "accepted"
    assert accepted_event.note == "Accept candidate from workflow loop test"
    assert accepted_event.from_version_id == "v-baseline"

    version_detail_response = client.get(f"/api/versions/TestStrat/{candidate_version_id}")
    assert version_detail_response.status_code == 200
    assert version_detail_response.json()["audit_events"][-1]["event_type"] == "accepted"

    version_list_response = client.get("/api/versions/TestStrat", params={"include_archived": "true"})
    assert version_list_response.status_code == 200
    listed_candidate = next(version for version in version_list_response.json()["versions"] if version["version_id"] == candidate_version_id)
    assert listed_candidate["audit_events"][-1]["note"] == "Accept candidate from workflow loop test"

    rollback_response = client.post(
        "/api/versions/TestStrat/rollback",
        json={"target_version_id": "v-baseline", "reason": "Rollback to baseline from workflow loop test"},
    )
    assert rollback_response.status_code == 200
    assert rollback_response.json()["status"] == "rolled_back"
    assert paths["strategy_file"].read_text(encoding="utf-8") == baseline_live_code
    assert json.loads(paths["config_file"].read_text(encoding="utf-8")) == baseline_live_config
    rolled_back_baseline = mutation_module.mutation_service.get_version_by_id("v-baseline")
    archived_candidate = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
    assert rolled_back_baseline.status == VersionStatus.ACTIVE
    assert archived_candidate.status == VersionStatus.ARCHIVED
    rollback_event = rolled_back_baseline.audit_events[-1]
    assert rollback_event.event_type == "rolled_back"
    assert rollback_event.note == "Rollback to baseline from workflow loop test"
    assert rollback_event.from_version_id == candidate_version_id

def test_backtest_workflow_reject_keeps_live_baseline_intact(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)
    _seed_active_baseline(paths)
    _patch_diagnosis(monkeypatch)

    fake_engine = FakeBacktestEngine(paths["results_dir"])
    monkeypatch.setattr(backtest_router, "_resolve_engine", lambda: fake_engine)

    baseline_summary = paths["results_dir"] / "bt-baseline.summary.json"
    baseline_summary.write_text(json.dumps(_summary_payload(1.0, 100.0, 8, 5)), encoding="utf-8")
    _save_completed_run("bt-baseline", "v-baseline", baseline_summary)

    baseline_live_code = paths["strategy_file"].read_text(encoding="utf-8")
    baseline_live_config = json.loads(paths["config_file"].read_text(encoding="utf-8"))

    candidate_response = client.post(
        "/api/backtest/runs/bt-baseline/proposal-candidates",
        json={
            "source_kind": "deterministic_action",
            "source_index": 0,
            "candidate_mode": "auto",
            "action_type": "tighten_stoploss",
        },
    )
    assert candidate_response.status_code == 200
    candidate_version_id = candidate_response.json()["candidate_version_id"]

    reject_response = client.post(
        "/api/versions/TestStrat/reject",
        json={
            "version_id": candidate_version_id,
            "reason": "Reject candidate from workflow loop test",
        },
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "rejected"

    rejected_candidate = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
    baseline_version = mutation_module.mutation_service.get_version_by_id("v-baseline")

    assert rejected_candidate.status == VersionStatus.REJECTED
    assert baseline_version.status == VersionStatus.ACTIVE
    assert [event.event_type for event in rejected_candidate.audit_events] == ["created", "rejected"]
    reject_event = rejected_candidate.audit_events[-1]
    assert reject_event.note == "Reject candidate from workflow loop test"
    assert reject_event.from_version_id is None
    assert paths["strategy_file"].read_text(encoding="utf-8") == baseline_live_code
    assert json.loads(paths["config_file"].read_text(encoding="utf-8")) == baseline_live_config
