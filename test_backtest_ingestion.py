"""\
Test script to verify run-scoped backtest ingestion artifacts.

This is a lightweight smoke test (not pytest) mirroring the repo's current test style.
"""

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone

from app.engines.freqtrade import engine as freqtrade_engine_module
from app.engines.freqtrade.engine import FreqtradeEngine
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.services.results_service import ResultsService
from app.utils.command_builder import build_backtest_command
from app.utils.datetime_utils import now_iso
from app.utils.paths import strategy_results_dir


def _write_raw_zip(raw_zip_path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(raw_zip_path), exist_ok=True)
    json_name = f"{os.path.splitext(os.path.basename(raw_zip_path))[0]}.json"
    with zipfile.ZipFile(raw_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(json_name, json.dumps(payload))


def _write_ohlcv_json(path: str, timestamps_ms: list[int]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    candles = [[ts, 100.0, 101.0, 99.0, 100.5, 1.0] for ts in timestamps_ms]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(candles, handle)


def _timestamp_ms(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp() * 1000)


def test_ingest_writes_run_scoped_artifacts() -> None:
    strategy = "_TestStrategyIngest"
    run_id = "bt-test-ingest"
    base_dir = strategy_results_dir(strategy)
    raw_zip_path = os.path.join(base_dir, f"{run_id}.backtest.zip")

    payload = {
        "strategy": {
            strategy: {
                "results_per_pair": [
                    {"key": "TOTAL", "profit_total_pct": 12.34},
                    {"key": "BTC/USDT", "profit_total_pct": 1.23},
                ],
                "trades": [],
            }
        },
        "strategy_comparison": {"note": "ok"},
    }

    try:
        _write_raw_zip(raw_zip_path, payload)

        run_record = BacktestRunRecord(
            run_id=run_id,
            strategy=strategy,
            version_id=None,
            trigger_source=BacktestTriggerSource.MANUAL,
            created_at=now_iso(),
            updated_at=now_iso(),
            completed_at=None,
            status=BacktestRunStatus.RUNNING,
            command="freqtrade backtesting ...",
            artifact_path=None,
            raw_result_path=raw_zip_path,
            result_path=None,
            summary_path=None,
            exit_code=None,
            pid=None,
            error=None,
        )

        svc = ResultsService()
        result = svc.ingest_backtest_run(run_record)

        assert result["raw_result_path"] == raw_zip_path
        assert result["profit_pct"] == 12.34
        assert os.path.isfile(result["result_path"]), result["result_path"]
        assert os.path.isfile(result["summary_path"]), result["summary_path"]
        assert os.path.isfile(os.path.join(base_dir, "latest.summary.json"))

        with open(result["result_path"], "r", encoding="utf-8") as handle:
            normalized = json.load(handle)
        assert normalized.get("run_id") == run_id
        assert normalized.get("strategy") == strategy
        assert normalized.get("profit_total_pct") == 12.34
        assert isinstance(normalized.get("result"), dict)

        with open(result["summary_path"], "r", encoding="utf-8") as handle:
            summary = json.load(handle)
        assert strategy in summary
        assert summary[strategy]["results_per_pair"][0]["key"] == "TOTAL"

        print("[PASS] Ingestion writes run-scoped artifacts")
    finally:
        if os.path.isdir(base_dir):
            shutil.rmtree(base_dir, ignore_errors=True)


def test_prepare_backtest_run_rejects_conflicting_export_flags() -> None:
    cli = FreqtradeCliService()
    payload = {
        "run_id": "bt-test-flags",
        "strategy": "Anything",
        "timeframe": "5m",
        "extra_flags": ["--notes", "custom-note"],
    }
    try:
        cli.prepare_backtest_run(payload)
        raise AssertionError("Expected ValueError for conflicting export flags")
    except ValueError:
        print("[PASS] Conflicting extra_flags are rejected")


def test_freqtrade_engine_validate_data_reports_timerange_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        candle_path = os.path.join(tmpdir, "data", "binance", "ETH_USDT-5m.json")
        _write_ohlcv_json(
            candle_path,
            [
                _timestamp_ms(2025, 1, 1),
                _timestamp_ms(2025, 1, 2),
                _timestamp_ms(2025, 1, 3),
            ],
        )

        original_get_settings = freqtrade_engine_module.config_svc.get_settings
        base_settings = original_get_settings()
        freqtrade_engine_module.config_svc.get_settings = lambda: {
            **base_settings,
            "user_data_path": tmpdir,
            "default_exchange": "binance",
        }
        try:
            engine = FreqtradeEngine()
            results = engine.validate_data(
                pairs=["ETH/USDT"],
                timeframe="5m",
                exchange="binance",
                timerange="20250101-20250103",
            )
        finally:
            freqtrade_engine_module.config_svc.get_settings = original_get_settings

        assert results[0]["status"] == "valid"
        assert results[0]["candle_count"] == 3
        assert results[0]["coverage_start"] == "2025-01-01 00:00:00 UTC"
        assert results[0]["coverage_end"] == "2025-01-03 00:00:00 UTC"
        print("[PASS] Data validation reports full timerange coverage")


def test_freqtrade_engine_validate_data_reports_partial_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        candle_path = os.path.join(tmpdir, "data", "binance", "ETH_USDT-5m.json")
        _write_ohlcv_json(
            candle_path,
            [
                _timestamp_ms(2025, 1, 1),
                _timestamp_ms(2025, 1, 2),
            ],
        )

        original_get_settings = freqtrade_engine_module.config_svc.get_settings
        base_settings = original_get_settings()
        freqtrade_engine_module.config_svc.get_settings = lambda: {
            **base_settings,
            "user_data_path": tmpdir,
            "default_exchange": "binance",
        }
        try:
            engine = FreqtradeEngine()
            results = engine.validate_data(
                pairs=["ETH/USDT"],
                timeframe="5m",
                exchange="binance",
                timerange="20250101-20250105",
            )
        finally:
            freqtrade_engine_module.config_svc.get_settings = original_get_settings

        assert results[0]["status"] == "partial"
        assert "requested timerange" in results[0]["message"]
        print("[PASS] Data validation reports partial timerange coverage")


def test_prepare_backtest_run_uses_strategy_directory_and_notes() -> None:
    cli = FreqtradeCliService()
    strategy = "_TestStrategyPrepared"
    result_dir = strategy_results_dir(strategy)

    try:
        prepared = cli.prepare_backtest_run(
            {
                "run_id": "bt-test-prepared",
                "strategy": strategy,
                "timeframe": "5m",
            }
        )

        assert prepared["raw_result_dir"] == result_dir
        assert prepared["raw_result_path"] is None
        assert prepared["log_file"] == os.path.join(result_dir, "bt-test-prepared.backtest.log")
        assert "--backtest-directory" in prepared["cmd"]
        assert result_dir in prepared["cmd"]
        assert "--notes" in prepared["cmd"]
        assert "bt-test-prepared" in prepared["cmd"]
        assert "--export-filename" not in prepared["cmd"]
        assert prepared["cmd"][-2:] == ["--cache", "none"]
        assert prepared["cmd"].count("--cache") == 1
        print("[PASS] Prepared backtest run uses strategy directory, notes, and disables cache by default")
    finally:
        if os.path.isdir(result_dir):
            shutil.rmtree(result_dir, ignore_errors=True)


def test_build_backtest_command_includes_backtest_directory_and_notes() -> None:
    cmd = build_backtest_command(
        freqtrade_path="",
        strategy="Anything",
        config_path="config.json",
        timeframe="5m",
        dry_run_wallet=0,
        max_open_trades=0,
        export_mode="trades",
        backtest_directory="results",
        notes="bt-test-run",
        extra_flags=["--cache", "none"],
    )

    assert "--dry-run-wallet" in cmd
    assert "0" in cmd
    assert "--max-open-trades" in cmd
    assert "--export" in cmd
    assert "trades" in cmd
    assert "--backtest-directory" in cmd
    assert "results" in cmd
    assert "--notes" in cmd
    assert "bt-test-run" in cmd
    assert cmd[-2:] == ["--cache", "none"]
    print("[PASS] Backtest command includes backtest directory and run notes")


def test_prepare_backtest_run_preserves_explicit_cache_flag() -> None:
    cli = FreqtradeCliService()
    prepared = cli.prepare_backtest_run(
        {
            "run_id": "bt-test-cache-day",
            "strategy": "Anything",
            "timeframe": "5m",
            "extra_flags": ["--cache", "day"],
        }
    )

    assert prepared["cmd"][-2:] == ["--cache", "day"]
    assert prepared["cmd"].count("--cache") == 1
    print("[PASS] Explicit backtest cache flag is preserved")


def test_prepare_download_data_uses_prepend_by_default() -> None:
    cli = FreqtradeCliService()
    prepared = cli.prepare_download_data(
        {
            "pairs": ["BTC/USDT"],
            "timeframe": "5m",
            "timerange": "20260101-20260131",
        }
    )

    assert prepared["prepend"] is True
    assert "--prepend" in prepared["cmd"]
    assert "--prepend" in prepared["command"]
    print("[PASS] Download-data preparation enables --prepend by default")


def test_resolve_backtest_raw_result_matches_run_note() -> None:
    cli = FreqtradeCliService()
    strategy = "_TestStrategyResolve"
    run_id = "bt-test-resolve"
    result_dir = strategy_results_dir(strategy)
    zip_path = os.path.join(result_dir, "backtest-result-2026-04-10_12-00-27.zip")
    meta_path = zip_path[:-4] + ".meta.json"

    try:
        os.makedirs(result_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("placeholder.json", "{}")

        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump({strategy: {"notes": run_id}}, handle)

        resolved = cli.resolve_backtest_raw_result(strategy, run_id)
        assert resolved == zip_path
        print("[PASS] Raw backtest artifact is resolved from metadata notes")
    finally:
        if os.path.isdir(result_dir):
            shutil.rmtree(result_dir, ignore_errors=True)


if __name__ == "__main__":
    test_ingest_writes_run_scoped_artifacts()
    test_prepare_backtest_run_rejects_conflicting_export_flags()
    test_freqtrade_engine_validate_data_reports_timerange_coverage()
    test_freqtrade_engine_validate_data_reports_partial_coverage()
    test_prepare_backtest_run_uses_strategy_directory_and_notes()
    test_build_backtest_command_includes_backtest_directory_and_notes()
    test_prepare_backtest_run_preserves_explicit_cache_flag()
    test_prepare_download_data_uses_prepend_by_default()
    test_resolve_backtest_raw_result_matches_run_note()
    print("\n[SUCCESS] Backtest ingestion tests passed")
