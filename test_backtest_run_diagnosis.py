import asyncio
import json

from app.freqtrade import runtime
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource


def test_live_strategy_snapshot_helpers_read_existing_live_files(tmp_path, monkeypatch):
    strategy_path = tmp_path / "TestStrat.py"
    config_path = tmp_path / "config_TestStrat.json"
    strategy_path.write_text("class TestStrat:\n    pass\n", encoding="utf-8")
    config_path.write_text(json.dumps({"stoploss": -0.1}), encoding="utf-8")

    monkeypatch.setattr(runtime, "live_strategy_file", lambda strategy_name, user_data_path=None: str(strategy_path))
    monkeypatch.setattr(runtime, "strategy_config_file", lambda strategy_name, user_data_path=None: str(config_path))

    assert runtime.load_live_strategy_code("TestStrat") == "class TestStrat:\n    pass\n"
    assert runtime.load_live_strategy_parameters("TestStrat") == {"stoploss": -0.1}


def test_live_strategy_snapshot_helpers_fallback_to_none_when_files_are_missing(tmp_path, monkeypatch):
    missing_strategy = tmp_path / "Missing.py"
    missing_config = tmp_path / "missing.json"

    monkeypatch.setattr(runtime, "live_strategy_file", lambda strategy_name, user_data_path=None: str(missing_strategy))
    monkeypatch.setattr(runtime, "strategy_config_file", lambda strategy_name, user_data_path=None: str(missing_config))

    assert runtime.load_live_strategy_code("Missing") is None
    assert runtime.load_live_strategy_parameters("Missing") is None


def test_get_backtest_run_diagnosis_reports_pending_summary(monkeypatch):
    run = BacktestRunRecord(
        run_id="bt-1",
        strategy="TestStrat",
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        status=BacktestRunStatus.RUNNING,
        command="freqtrade backtesting",
    )

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)
    monkeypatch.setattr(runtime.results_svc, "load_run_summary_state", lambda record: {"state": "pending"})

    payload = asyncio.run(runtime.get_backtest_run_diagnosis("bt-1", include_ai=False))

    assert payload["summary_available"] is False
    assert payload["diagnosis_status"] == "pending_summary"
    assert payload["ai"]["ai_status"] == "disabled"
