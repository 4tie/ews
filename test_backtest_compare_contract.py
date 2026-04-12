import json

import pytest

from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource
from app.services import results_service as results_module


def _run_record(run_id: str, summary_path: str | None) -> BacktestRunRecord:
    return BacktestRunRecord(
        run_id=run_id,
        strategy="TestStrat",
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        completed_at="2026-01-01T00:05:00",
        status=BacktestRunStatus.COMPLETED,
        command="freqtrade backtesting",
        raw_result_path=f"/tmp/{run_id}.zip",
        summary_path=summary_path,
    )


def _summary_payload(profit_total_pct: float, profit_total_abs: float, trades: int, wins: int) -> dict:
    return {
        "TestStrat": {
            "strategy_name": "TestStrat",
            "results_per_pair": [
                {"key": "BTC/USDT", "profit_total_pct": profit_total_pct / 2},
                {
                    "key": "TOTAL",
                    "profit_total_pct": profit_total_pct,
                    "profit_total_abs": profit_total_abs,
                    "trades": trades,
                    "wins": wins,
                    "max_drawdown_account": 0.1,
                    "sharpe": 1.0,
                    "sortino": 1.2,
                    "calmar": 0.8,
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


def test_compare_backtest_runs_requires_persisted_summary(monkeypatch, tmp_path):
    strategy_dir = tmp_path / "TestStrat"
    monkeypatch.setattr(results_module, "strategy_results_dir", lambda strategy, user_data_path=None: str(strategy_dir))
    service = results_module.ResultsService()

    left_run = _run_record("bt-left", None)
    right_run = _run_record("bt-right", None)

    with pytest.raises(ValueError, match="persisted summary"):
        service.compare_backtest_runs(left_run, right_run)


def test_compare_backtest_runs_uses_real_summary_artifacts(monkeypatch, tmp_path):
    strategy_dir = tmp_path / "TestStrat"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(results_module, "strategy_results_dir", lambda strategy, user_data_path=None: str(strategy_dir))
    service = results_module.ResultsService()

    left_summary_path = strategy_dir / "bt-left.summary.json"
    right_summary_path = strategy_dir / "bt-right.summary.json"
    left_summary_path.write_text(json.dumps(_summary_payload(1.5, 100.0, 10, 6)), encoding="utf-8")
    right_summary_path.write_text(json.dumps(_summary_payload(3.0, 130.0, 12, 7)), encoding="utf-8")

    left_run = _run_record("bt-left", str(left_summary_path))
    right_run = _run_record("bt-right", str(right_summary_path))

    comparison = service.compare_backtest_runs(left_run, right_run)
    profit_row = next(row for row in comparison["metrics"] if row["key"] == "profit_total_pct")

    assert comparison["left"]["summary_available"] is True
    assert comparison["right"]["summary_available"] is True
    assert profit_row == {
        "key": "profit_total_pct",
        "label": "Total Profit %",
        "format": "pct",
        "left": 1.5,
        "right": 3.0,
        "delta": 1.5,
    }
