"""\
Test script to verify run-scoped backtest ingestion artifacts.

This is a lightweight smoke test (not pytest) mirroring the repo's current test style.
"""

import json
import os
import shutil
import zipfile

from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.services.results_service import ResultsService
from app.utils.datetime_utils import now_iso
from app.utils.paths import strategy_results_dir


def _write_raw_zip(raw_zip_path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(raw_zip_path), exist_ok=True)
    json_name = f"{os.path.splitext(os.path.basename(raw_zip_path))[0]}.json"
    with zipfile.ZipFile(raw_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(json_name, json.dumps(payload))


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
        "extra_flags": ["--export", "trades"],
    }
    try:
        cli.prepare_backtest_run(payload)
        raise AssertionError("Expected ValueError for conflicting export flags")
    except ValueError:
        print("[PASS] Conflicting extra_flags are rejected")


if __name__ == "__main__":
    test_ingest_writes_run_scoped_artifacts()
    test_prepare_backtest_run_rejects_conflicting_export_flags()
    print("\n[SUCCESS] Backtest ingestion tests passed")