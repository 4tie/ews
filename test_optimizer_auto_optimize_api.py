import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource
from app.services import persistence_service as persistence_module
from app.services import results_service as results_module
from app.services.persistence_service import PersistenceService
from app.services.autotune.auto_optimize_service import auto_optimize_service


client = TestClient(app)


def _configure_storage(monkeypatch, tmp_path: Path) -> dict:
    data_root = tmp_path / "data"
    user_data_root = tmp_path / "user_data"
    results_root = user_data_root / "backtest_results"

    monkeypatch.setattr(persistence_module, "backtest_runs_dir", lambda: str(data_root / "backtest_runs"))
    monkeypatch.setattr(persistence_module, "optimizer_runs_dir", lambda: str(data_root / "optimizer_runs"))

    monkeypatch.setattr(
        results_module,
        "strategy_results_dir",
        lambda strategy, user_data_path=None: str(results_root / strategy),
    )

    (data_root / "backtest_runs").mkdir(parents=True, exist_ok=True)
    (data_root / "optimizer_runs").mkdir(parents=True, exist_ok=True)

    return {
        "data_root": data_root,
        "results_root": results_root,
    }


def test_optimizer_auto_optimize_can_create_and_fetch_run(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)

    monkeypatch.setattr(auto_optimize_service, '_start_task', lambda optimizer_run_id: None)

    strategy = "TestStrat"
    baseline_run_id = "bt-baseline"

    results_dir = Path(results_module.strategy_results_dir(strategy))
    results_dir.mkdir(parents=True, exist_ok=True)

    summary_path = results_dir / f"{baseline_run_id}.summary.json"
    summary_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    baseline = BacktestRunRecord(
        run_id=baseline_run_id,
        engine="freqtrade",
        strategy=strategy,
        version_id="v-baseline",
        request_snapshot={
            "strategy": strategy,
            "timeframe": "5m",
            "timerange": None,
            "pairs": [],
            "exchange": "binance",
            "max_open_trades": None,
            "dry_run_wallet": None,
            "extra_flags": [],
            "trigger_source": BacktestTriggerSource.MANUAL.value,
            "config_path": None,
            "engine": "freqtrade",
        },
        request_snapshot_schema_version=1,
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:01+00:00",
        completed_at="2026-01-01T00:00:02+00:00",
        status=BacktestRunStatus.COMPLETED,
        command="freqtrade backtesting --strategy TestStrat",
        summary_path=str(summary_path),
        artifact_path=None,
        raw_result_path=None,
        result_path=None,
        exit_code=0,
        pid=None,
        error=None,
    )

    PersistenceService().save_backtest_run(baseline_run_id, baseline.model_dump(mode="json"))

    create = client.post(
        "/api/optimizer/runs",
        json={
            "baseline_run_id": baseline_run_id,
            "attempts": 2,
            "beam_width": 2,
            "branch_factor": 2,
            "include_ai_suggestions": False,
            "thresholds": {
                "min_profit_total_pct": 0.5,
                "min_total_trades": 30,
                "max_allowed_drawdown_pct": 35,
            },
            "hard_stops": {
                "max_total_nodes": 10,
                "max_failed_runs": 5,
                "max_consecutive_no_improvement_attempts": 3,
            },
        },
    )
    assert create.status_code == 200
    optimizer_run_id = create.json().get("optimizer_run_id")
    assert optimizer_run_id

    run_meta = paths["data_root"] / "optimizer_runs" / optimizer_run_id / "run_meta.json"
    nodes_path = paths["data_root"] / "optimizer_runs" / optimizer_run_id / "nodes.json"
    assert run_meta.is_file()
    assert nodes_path.is_file()

    fetch = client.get(f"/api/optimizer/runs/{optimizer_run_id}")
    assert fetch.status_code == 200
    payload = fetch.json()
    assert payload["schema_version"] == 1
    assert payload["optimizer_run_id"] == optimizer_run_id
    assert payload["baseline_run_id"] == baseline_run_id
    assert payload["baseline_version_id"] == "v-baseline"


def test_optimizer_runs_endpoint_still_accepts_legacy_payload(monkeypatch, tmp_path):
    _configure_storage(monkeypatch, tmp_path)

    response = client.post(
        "/api/optimizer/runs",
        json={
            "strategy": "TestStrat",
            "timeframe": "5m",
            "epochs": 10,
            "spaces": ["buy"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("run_id")
    assert payload.get("optimizer_run_id") is None


def test_optimizer_stop_endpoint_stops_auto_optimize_run(monkeypatch, tmp_path):
    _configure_storage(monkeypatch, tmp_path)

    monkeypatch.setattr(auto_optimize_service, '_start_task', lambda optimizer_run_id: None)

    strategy = "TestStrat"
    baseline_run_id = "bt-stop-baseline"

    results_dir = Path(results_module.strategy_results_dir(strategy))
    results_dir.mkdir(parents=True, exist_ok=True)

    summary_path = results_dir / f"{baseline_run_id}.summary.json"
    summary_path.write_text(json.dumps({"ok": True}), encoding="utf-8")

    baseline = BacktestRunRecord(
        run_id=baseline_run_id,
        engine="freqtrade",
        strategy=strategy,
        version_id="v-baseline",
        request_snapshot={
            "strategy": strategy,
            "timeframe": "5m",
            "timerange": None,
            "pairs": [],
            "exchange": "binance",
            "max_open_trades": None,
            "dry_run_wallet": None,
            "extra_flags": [],
            "trigger_source": BacktestTriggerSource.MANUAL.value,
            "config_path": None,
            "engine": "freqtrade",
        },
        request_snapshot_schema_version=1,
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:01+00:00",
        completed_at="2026-01-01T00:00:02+00:00",
        status=BacktestRunStatus.COMPLETED,
        command="freqtrade backtesting --strategy TestStrat",
        summary_path=str(summary_path),
        artifact_path=None,
        raw_result_path=None,
        result_path=None,
        exit_code=0,
        pid=None,
        error=None,
    )

    PersistenceService().save_backtest_run(baseline_run_id, baseline.model_dump(mode="json"))

    create = client.post(
        "/api/optimizer/runs",
        json={
            "baseline_run_id": baseline_run_id,
            "attempts": 2,
            "beam_width": 2,
            "branch_factor": 2,
            "include_ai_suggestions": False,
        },
    )
    assert create.status_code == 200
    optimizer_run_id = create.json().get("optimizer_run_id")
    assert optimizer_run_id

    stop = client.post(f"/api/optimizer/runs/{optimizer_run_id}/stop")
    assert stop.status_code == 200
    assert stop.json() == {"run_id": optimizer_run_id, "status": "stopped"}

    fetch = client.get(f"/api/optimizer/runs/{optimizer_run_id}")
    assert fetch.status_code == 200
    payload = fetch.json()
    assert payload["status"] == "completed"
    assert payload["result_kind"] == "hard_stop_triggered"
    assert payload["completion_reason"] == "hard_stop_triggered"


def test_optimizer_stop_endpoint_stops_legacy_run(monkeypatch, tmp_path):
    paths = _configure_storage(monkeypatch, tmp_path)

    response = client.post(
        "/api/optimizer/runs",
        json={
            "strategy": "TestStrat",
            "timeframe": "5m",
            "epochs": 10,
            "spaces": ["buy"],
        },
    )

    assert response.status_code == 200
    run_id = response.json().get("run_id")
    assert run_id

    stop = client.post(f"/api/optimizer/runs/{run_id}/stop")
    assert stop.status_code == 200
    assert stop.json() == {"run_id": run_id, "status": "stopped"}

    run_meta_path = paths["data_root"] / "optimizer_runs" / run_id / "run_meta.json"
    payload = json.loads(run_meta_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == run_id
    assert payload["status"] == "stopped"
    assert payload.get("completed_at")
