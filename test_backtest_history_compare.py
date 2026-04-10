"""\
Smoke tests for persisted backtest history and compare APIs.
"""

import json
import os
import shutil
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.backtest as backtest_router
import app.services.persistence_service as persistence_module
import app.services.results_service as results_module


class _PatchedStorage:
    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bt-history-")
        self.runs_dir = os.path.join(self.tmpdir, "data", "backtest_runs")
        self.results_dir = os.path.join(self.tmpdir, "user_data", "backtest_results")
        os.makedirs(self.runs_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        self._orig_backtest_runs_dir = persistence_module.backtest_runs_dir
        self._orig_strategy_results_dir = results_module.strategy_results_dir
        self._orig_user_data_results_dir = results_module.user_data_results_dir

    def __enter__(self):
        persistence_module.backtest_runs_dir = lambda: self.runs_dir
        results_module.strategy_results_dir = lambda strategy: os.path.join(self.results_dir, strategy)
        results_module.user_data_results_dir = lambda: self.results_dir
        return self

    def __exit__(self, exc_type, exc, tb):
        persistence_module.backtest_runs_dir = self._orig_backtest_runs_dir
        results_module.strategy_results_dir = self._orig_strategy_results_dir
        results_module.user_data_results_dir = self._orig_user_data_results_dir
        shutil.rmtree(self.tmpdir, ignore_errors=True)


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _make_summary(strategy: str, profit_pct: float, profit_abs: float, total_trades: int, pair_count: int) -> dict:
    pairs = [{"key": f"PAIR-{index + 1}", "profit_total_pct": round(profit_pct / max(pair_count, 1), 2), "trades": 1} for index in range(pair_count)]
    total_row = {
        "key": "TOTAL",
        "profit_total_pct": profit_pct,
        "profit_total_abs": profit_abs,
        "trades": total_trades,
        "winrate": 2 / 3,
        "max_drawdown_account": 0.037,
        "sharpe": 1.5,
        "sortino": 2.2,
        "calmar": 3.1,
        "duration_avg": "4:27:00",
    }
    return {
        strategy: {
            "strategy_name": strategy,
            "timeframe": "5m",
            "timerange": "20250101-20250131",
            "stake_currency": "USDT",
            "profit_total_abs": profit_abs,
            "results_per_pair": [total_row, *pairs],
            "trades": [
                {
                    "open_date": "2026-01-01 00:00:00+00:00",
                    "close_date": "2026-01-02 00:00:00+00:00",
                    "profit_abs": 1.0,
                },
                {
                    "open_date": "2026-01-03 00:00:00+00:00",
                    "close_date": "2026-01-04 00:00:00+00:00",
                    "profit_abs": 2.0,
                },
            ],
        }
    }


def _write_run(storage: _PatchedStorage, *, run_id: str, strategy: str, created_at: str, status: str, summary_payload: dict | None = None, error: str | None = None, version_id: str | None = None) -> str | None:
    summary_path = None
    result_path = None
    raw_result_path = os.path.join(storage.results_dir, strategy, f"{run_id}.backtest.zip")
    artifact_path = os.path.join(storage.results_dir, strategy, f"{run_id}.backtest.log")

    if summary_payload is not None:
        summary_path = os.path.join(storage.results_dir, strategy, f"{run_id}.summary.json")
        result_path = os.path.join(storage.results_dir, strategy, f"{run_id}.result.json")
        _write_json(summary_path, summary_payload)
        _write_json(result_path, {"run_id": run_id, "strategy": strategy})

    run_meta = {
        "run_id": run_id,
        "engine": "freqtrade",
        "strategy": strategy,
        "version_id": version_id,
        "trigger_source": "manual",
        "created_at": created_at,
        "updated_at": created_at,
        "completed_at": created_at if status in {"completed", "failed"} else None,
        "status": status,
        "command": f"freqtrade backtesting --strategy {strategy}",
        "artifact_path": artifact_path,
        "raw_result_path": raw_result_path,
        "result_path": result_path,
        "summary_path": summary_path,
        "exit_code": 0 if status == "completed" else 1 if status == "failed" else None,
        "pid": None,
        "error": error,
    }
    _write_json(os.path.join(storage.runs_dir, run_id, "run_meta.json"), run_meta)
    return summary_path


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(backtest_router.router, prefix="/api/backtest")
    return TestClient(app)


def test_list_runs_returns_persisted_history() -> None:
    with _PatchedStorage() as storage:
        _write_run(
            storage,
            run_id="bt-alpha-new",
            strategy="Alpha",
            created_at="2026-04-10T10:00:00+00:00",
            status="completed",
            summary_payload=_make_summary("Alpha", 12.34, 6.78, 3, 2),
            version_id="v2",
        )
        _write_run(
            storage,
            run_id="bt-alpha-failed",
            strategy="Alpha",
            created_at="2026-04-10T09:00:00+00:00",
            status="failed",
            error="ingestion_failed: missing artifact",
        )
        _write_run(
            storage,
            run_id="bt-beta-old",
            strategy="Beta",
            created_at="2026-04-09T08:00:00+00:00",
            status="completed",
            summary_payload=_make_summary("Beta", 4.5, 1.2, 2, 1),
        )

        client = _make_client()
        response = client.get("/api/backtest/runs", params={"strategy": "Alpha"})
        assert response.status_code == 200, response.text
        payload = response.json()

        runs = payload["runs"]
        assert [run["run_id"] for run in runs] == ["bt-alpha-new", "bt-alpha-failed"]
        assert runs[0]["summary_available"] is True
        assert runs[0]["summary_metrics"]["profit_total_pct"] == 12.34
        assert runs[0]["summary_metrics"]["pair_count"] == 2
        assert runs[0]["summary_metrics"]["trade_start"] == "2026-01-01 00:00:00+00:00"
        assert runs[1]["summary_available"] is False
        assert runs[1]["error"] == "ingestion_failed: missing artifact"
        print("[PASS] Persisted run history listing works")


def test_get_single_run_returns_summary_context() -> None:
    with _PatchedStorage() as storage:
        _write_run(
            storage,
            run_id="bt-single",
            strategy="Gamma",
            created_at="2026-04-10T07:00:00+00:00",
            status="completed",
            summary_payload=_make_summary("Gamma", 9.9, 3.3, 4, 3),
            version_id="v7",
        )

        client = _make_client()
        response = client.get("/api/backtest/runs/bt-single")
        assert response.status_code == 200, response.text
        run = response.json()["run"]
        assert run["run_id"] == "bt-single"
        assert run["version_id"] == "v7"
        assert run["summary_available"] is True
        assert run["summary_metrics"]["strategy"] == "Gamma"
        assert run["summary_metrics"]["total_trades"] == 4
        print("[PASS] Single persisted run read works")


def test_compare_runs_returns_metric_rows() -> None:
    with _PatchedStorage() as storage:
        _write_run(
            storage,
            run_id="bt-left",
            strategy="Delta",
            created_at="2026-04-10T06:00:00+00:00",
            status="completed",
            summary_payload=_make_summary("Delta", 10.0, 4.0, 3, 2),
        )
        _write_run(
            storage,
            run_id="bt-right",
            strategy="Delta",
            created_at="2026-04-10T08:00:00+00:00",
            status="completed",
            summary_payload=_make_summary("Delta", 14.5, 6.2, 5, 3),
        )

        client = _make_client()
        response = client.get("/api/backtest/compare", params={"left_run_id": "bt-left", "right_run_id": "bt-right"})
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["left"]["run_id"] == "bt-left"
        assert payload["right"]["run_id"] == "bt-right"
        metrics = {row["key"]: row for row in payload["metrics"]}
        assert metrics["profit_total_pct"]["left"] == 10.0
        assert metrics["profit_total_pct"]["right"] == 14.5
        assert metrics["profit_total_pct"]["delta"] == 4.5
        assert metrics["total_trades"]["delta"] == 2.0
        print("[PASS] Persisted run compare works")


def test_compare_requires_persisted_summary() -> None:
    with _PatchedStorage() as storage:
        _write_run(
            storage,
            run_id="bt-ok",
            strategy="Epsilon",
            created_at="2026-04-10T05:00:00+00:00",
            status="completed",
            summary_payload=_make_summary("Epsilon", 7.0, 2.0, 2, 1),
        )
        _write_run(
            storage,
            run_id="bt-missing-summary",
            strategy="Epsilon",
            created_at="2026-04-10T05:30:00+00:00",
            status="failed",
            error="ingestion_failed: summary missing",
        )

        client = _make_client()
        response = client.get(
            "/api/backtest/compare",
            params={"left_run_id": "bt-ok", "right_run_id": "bt-missing-summary"},
        )
        assert response.status_code == 400, response.text
        assert "persisted summary" in response.json()["detail"]
        print("[PASS] Compare rejects runs without persisted summaries")


if __name__ == "__main__":
    test_list_runs_returns_persisted_history()
    test_get_single_run_returns_summary_context()
    test_compare_runs_returns_metric_rows()
    test_compare_requires_persisted_summary()
    print("\n[SUCCESS] Backtest history/compare tests passed")
