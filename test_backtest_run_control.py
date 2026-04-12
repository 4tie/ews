import asyncio
import json
from types import SimpleNamespace

from app.freqtrade import runtime
from app.models.backtest_models import (
    BacktestRunRecord,
    BacktestRunRequest,
    BacktestRunStatus,
    BacktestTriggerSource,
)
from app.services import persistence_service as persistence_module


def make_run(
    tmp_path,
    *,
    status=BacktestRunStatus.RUNNING,
    log_lines=None,
    stop_requested_at=None,
    error=None,
    exit_code=None,
    pid=1234,
):
    log_path = tmp_path / "bt.log"
    lines = list(log_lines or [])
    log_path.write_text("\n".join(lines), encoding="utf-8")
    completed_at = None if status in {BacktestRunStatus.QUEUED, BacktestRunStatus.RUNNING} else "2026-01-01T00:05:00"
    return BacktestRunRecord(
        run_id="bt-test",
        engine="freqtrade",
        strategy="TestStrat",
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        completed_at=completed_at,
        stop_requested_at=stop_requested_at,
        status=status,
        command="freqtrade backtesting",
        artifact_path=str(log_path),
        raw_result_path=None,
        result_path=None,
        summary_path=None,
        exit_code=exit_code,
        pid=pid,
        error=error,
    )


def test_stopped_is_treated_as_terminal_status():
    assert runtime._is_terminal_status(BacktestRunStatus.STOPPED)


def test_derive_backtest_progress_reports_phase_from_log(tmp_path):
    run = make_run(
        tmp_path,
        log_lines=["2026-04-11 09:23:47,870 - freqtrade.optimize.backtesting - INFO - Loading data from 2025-07-01 00:00:00 up to 2026-04-11 00:00:00 (284 days)."],
    )

    progress = runtime._derive_backtest_progress(run)

    assert progress == {"phase": "loading_data", "percent": 25, "label": "Loading data"}


def test_get_backtest_run_includes_progress(tmp_path, monkeypatch):
    run = make_run(
        tmp_path,
        log_lines=["2026-04-11 09:23:49,749 - freqtrade.optimize.backtesting - INFO - Running backtesting for Strategy TestStrat"],
    )
    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)

    payload = asyncio.run(runtime.get_backtest_run("bt-test"))

    assert payload["run"]["status"] == BacktestRunStatus.RUNNING.value
    assert payload["run"]["progress"] == {"phase": "backtesting", "percent": 70, "label": "Running backtest"}


def test_list_backtest_runs_includes_progress(tmp_path, monkeypatch):
    run = make_run(
        tmp_path,
        log_lines=["2026-04-11 09:23:49,749 - freqtrade.optimize.backtesting - INFO - Dataload complete. Calculating indicators"],
    )
    monkeypatch.setattr(runtime, "_list_freqtrade_runs", lambda strategy=None: [run])

    payload = asyncio.run(runtime.list_backtest_runs())

    assert payload["runs"][0]["progress"] == {"phase": "indicators", "percent": 45, "label": "Calculating indicators"}


def test_stop_backtest_run_marks_running_run_stopped(tmp_path, monkeypatch):
    run = make_run(tmp_path, error=None, pid=321)
    saved = []

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)
    monkeypatch.setattr(runtime, "_save_run_record", lambda record: saved.append((record.status, record.stop_requested_at, record.exit_code, record.error)))
    monkeypatch.setattr(runtime, "_terminate_process_tree", lambda record: 143)

    payload = asyncio.run(runtime.stop_backtest_run("bt-test"))

    assert run.status == BacktestRunStatus.STOPPED
    assert run.stop_requested_at is not None
    assert run.exit_code == 143
    assert payload["status"] == BacktestRunStatus.STOPPED.value
    assert payload["run"]["status"] == BacktestRunStatus.STOPPED.value
    assert saved


def test_stop_backtest_run_is_idempotent_for_terminal_run(tmp_path, monkeypatch):
    run = make_run(tmp_path, status=BacktestRunStatus.COMPLETED, exit_code=0, pid=None)
    terminate_called = {"value": False}

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)

    def fake_terminate(record):
        terminate_called["value"] = True
        return None

    monkeypatch.setattr(runtime, "_terminate_process_tree", fake_terminate)

    payload = asyncio.run(runtime.stop_backtest_run("bt-test"))

    assert payload["status"] == "already_terminal"
    assert terminate_called["value"] is False


def test_watch_backtest_process_marks_stop_requested_run_stopped(tmp_path, monkeypatch):
    run = make_run(
        tmp_path,
        stop_requested_at="2026-01-01T00:00:05",
        error="stopped_by_user: stop requested from UI",
    )
    calls = {}

    class FakeProcess:
        def wait(self):
            return 1

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: run)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("unexpected terminal path")

    monkeypatch.setattr(runtime, "_mark_failed_run", fail_if_called)
    monkeypatch.setattr(runtime, "_finalize_successful_backtest_run", fail_if_called)

    def fake_mark_stopped(record, *, exit_code=None, reason=""):
        calls["exit_code"] = exit_code
        calls["reason"] = reason
        record.status = BacktestRunStatus.STOPPED
        return record

    monkeypatch.setattr(runtime, "_mark_stopped_run", fake_mark_stopped)

    runtime._watch_backtest_process("bt-test", FakeProcess())

    assert calls["exit_code"] == 1
    assert "stopped_by_user" in calls["reason"]


def test_run_backtest_persists_run_meta_with_version_and_request_snapshot(tmp_path, monkeypatch):
    base_config_path = tmp_path / "base.config.json"
    base_config_path.write_text("{}", encoding="utf-8")
    captured = {}

    class FakeEngine:
        engine_id = "freqtrade"

        def prepare_backtest_run(self, launch_payload):
            captured["launch_payload"] = dict(launch_payload)
            return {
                "run_id": launch_payload["run_id"],
                "cmd": ["freqtrade", "backtesting"],
                "command": "freqtrade backtesting",
                "config_path": str(base_config_path),
                "request_config_path": str(base_config_path),
                "raw_result_path": None,
                "log_file": str(tmp_path / "run.log"),
                "artifact_path": str(tmp_path / "run.log"),
            }

        def run_backtest(self, payload, prepared=None):
            return {
                "command": prepared["command"],
                "status": "running",
                "pid": 321,
                "log_file": prepared["log_file"],
                "raw_result_path": prepared["raw_result_path"],
                "process": None,
            }

    monkeypatch.setattr(persistence_module, "backtest_runs_dir", lambda: str(tmp_path))
    monkeypatch.setattr(runtime, "_resolve_version_for_launch", lambda payload: SimpleNamespace(version_id="v-resolved", strategy_name=payload.strategy))
    monkeypatch.setattr(runtime, "_resolve_engine", lambda: FakeEngine())
    monkeypatch.setattr(runtime.mutation_service, "link_backtest", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime.uuid, "uuid4", lambda: SimpleNamespace(hex="12345678abcdef00"))

    response = asyncio.run(
        runtime.run_backtest(
            BacktestRunRequest(
                strategy="TestStrat",
                timeframe="5m",
                timerange="20240101-20240201",
                pairs=["BTC/USDT"],
                exchange="binance",
                max_open_trades=2,
                dry_run_wallet=250.0,
                config_path=str(base_config_path),
                extra_flags=["--cache", "none"],
                trigger_source=BacktestTriggerSource.AI_APPLY,
            )
        )
    )

    run_id = response["run_id"]
    meta_path = tmp_path / run_id / "run_meta.json"
    persisted = json.loads(meta_path.read_text(encoding="utf-8"))

    assert run_id == "bt-12345678"
    assert captured["launch_payload"]["version_id"] == "v-resolved"
    assert persisted["run_id"] == run_id
    assert persisted["version_id"] == "v-resolved"
    assert persisted["request_snapshot"] == {
        "strategy": "TestStrat",
        "timeframe": "5m",
        "timerange": "20240101-20240201",
        "pairs": ["BTC/USDT"],
        "exchange": "binance",
        "max_open_trades": 2,
        "dry_run_wallet": 250.0,
        "extra_flags": ["--cache", "none"],
        "trigger_source": "ai_apply",
        "config_path": str(base_config_path),
        "engine": "freqtrade",
    }
