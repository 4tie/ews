import asyncio
import json

import pytest

from app.freqtrade import runtime
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource


def _run_record(
    *,
    run_id: str = "bt-1",
    status: BacktestRunStatus = BacktestRunStatus.RUNNING,
    completed_at: str | None = None,
    summary_path: str | None = None,
    raw_result_path: str | None = None,
    error: str | None = None,
    version_id: str | None = None,
) -> BacktestRunRecord:
    return BacktestRunRecord(
        run_id=run_id,
        strategy="TestStrat",
        version_id=version_id,
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        completed_at=completed_at,
        status=status,
        command="freqtrade backtesting",
        artifact_path=None,
        raw_result_path=raw_result_path,
        summary_path=summary_path,
        error=error,
    )


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


def test_get_backtest_run_diagnosis_reports_ready(monkeypatch):
    run = _run_record(
        status=BacktestRunStatus.COMPLETED,
        completed_at="2026-01-01T00:05:00",
        summary_path="/tmp/bt-1.summary.json",
        raw_result_path="/tmp/bt-1.zip",
    )
    summary_payload = {"TestStrat": {"profit_total_pct": 1.25}}

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)
    monkeypatch.setattr(
        runtime.results_svc,
        "load_run_summary_state",
        lambda record: {"state": "ready", "summary": summary_payload, "error": None},
    )
    monkeypatch.setattr(
        runtime.results_svc,
        "extract_run_summary_block",
        lambda summary, strategy: {"trades": [], "results_per_pair": [], "profit_total_pct": 1.25},
    )
    monkeypatch.setattr(
        runtime.results_svc,
        "_normalize_summary_metrics",
        lambda summary, strategy: {"profit_total_pct": 1.25},
    )
    monkeypatch.setattr(
        runtime.diagnosis_service,
        "diagnose_run",
        lambda **kwargs: {"primary_flags": ["healthy"], "proposal_actions": []},
    )

    payload = asyncio.run(runtime.get_backtest_run_diagnosis("bt-1", include_ai=False))

    assert payload["summary_available"] is True
    assert payload["diagnosis_status"] == "ready"
    assert payload["summary_metrics"] == {"profit_total_pct": 1.25}
    assert payload["diagnosis"]["primary_flags"] == ["healthy"]
    assert payload["ai"]["ai_status"] == "disabled"
    assert payload["error"] is None


def test_get_backtest_run_diagnosis_reports_pending_summary(monkeypatch):
    run = _run_record(status=BacktestRunStatus.RUNNING)

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)
    monkeypatch.setattr(runtime.results_svc, "load_run_summary_state", lambda record: {"state": "pending"})

    payload = asyncio.run(runtime.get_backtest_run_diagnosis("bt-1", include_ai=False))

    assert payload["summary_available"] is False
    assert payload["diagnosis_status"] == "pending_summary"
    assert payload["ai"]["ai_status"] == "disabled"


def test_get_backtest_run_diagnosis_reports_ingestion_failed_for_summary_load_failure(monkeypatch):
    run = _run_record(status=BacktestRunStatus.RUNNING)

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)
    monkeypatch.setattr(
        runtime.results_svc,
        "load_run_summary_state",
        lambda record: {"state": "load_failed", "summary": None, "error": "summary_load_failed: broken json"},
    )

    payload = asyncio.run(runtime.get_backtest_run_diagnosis("bt-1", include_ai=False))

    assert payload["summary_available"] is False
    assert payload["diagnosis_status"] == "ingestion_failed"
    assert payload["error"] == "summary_load_failed: broken json"


@pytest.mark.parametrize(
    ("summary_path", "raw_result_path"),
    [
        (None, "/tmp/bt-1.zip"),
        ("/tmp/bt-1.summary.json", None),
    ],
)
def test_get_backtest_run_diagnosis_reports_ingestion_failed_for_completed_run_with_missing_artifacts(
    monkeypatch,
    summary_path,
    raw_result_path,
):
    run = _run_record(
        status=BacktestRunStatus.COMPLETED,
        completed_at="2026-01-01T00:05:00",
        summary_path=summary_path,
        raw_result_path=raw_result_path,
    )

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)
    monkeypatch.setattr(
        runtime.results_svc,
        "load_run_summary_state",
        lambda record: {"state": "missing", "summary": None, "error": None},
    )

    payload = asyncio.run(runtime.get_backtest_run_diagnosis("bt-1", include_ai=False))

    assert payload["summary_available"] is False
    assert payload["diagnosis_status"] == "ingestion_failed"


def test_get_backtest_run_diagnosis_reports_ingestion_failed_for_failed_run(monkeypatch):
    run = _run_record(status=BacktestRunStatus.FAILED, error="freqtrade_failed: exit 2")

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)
    monkeypatch.setattr(
        runtime.results_svc,
        "load_run_summary_state",
        lambda record: {"state": "missing", "summary": None, "error": None},
    )

    payload = asyncio.run(runtime.get_backtest_run_diagnosis("bt-1", include_ai=False))

    assert payload["summary_available"] is False
    assert payload["diagnosis_status"] == "ingestion_failed"
    assert payload["error"] == "freqtrade_failed: exit 2"
