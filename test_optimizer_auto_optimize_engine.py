import asyncio
import json
from pathlib import Path

from app.freqtrade import runtime as runtime_module
from app.models.backtest_models import BacktestRunRecord, BacktestRunRequest, BacktestRunStatus, BacktestTriggerSource
from app.models.optimizer_models import (
    ChangeType,
    MutationRequest,
    OptimizationResultKind,
    OptimizationRunCreateRequest,
    OptimizationRunStatus,
)
from app.services import mutation_service as mutation_module
from app.services import persistence_service as persistence_module
from app.services import results_service as results_module
from app.services.autotune.auto_optimize_service import AutoOptimizeService
from app.services.mutation_service import mutation_service
from app.services.persistence_service import PersistenceService


def _configure_storage(monkeypatch, tmp_path: Path) -> dict:
    data_root = tmp_path / "data"
    versions_root = data_root / "versions"
    user_data_root = tmp_path / "user_data"
    results_root = user_data_root / "backtest_results"

    # Persistence paths
    monkeypatch.setattr(persistence_module, "backtest_runs_dir", lambda: str(data_root / "backtest_runs"))
    monkeypatch.setattr(persistence_module, "optimizer_runs_dir", lambda: str(data_root / "optimizer_runs"))

    # Results paths (summary path guard)
    monkeypatch.setattr(
        results_module,
        "strategy_results_dir",
        lambda strategy, user_data_path=None: str(results_root / strategy),
    )

    # Version storage paths
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

    (data_root / "backtest_runs").mkdir(parents=True, exist_ok=True)
    (data_root / "optimizer_runs").mkdir(parents=True, exist_ok=True)
    versions_root.mkdir(parents=True, exist_ok=True)
    results_root.mkdir(parents=True, exist_ok=True)

    return {
        "data_root": data_root,
        "versions_root": versions_root,
        "user_data_root": user_data_root,
        "results_root": results_root,
    }


def _write_summary(strategy: str, run_id: str, *, profit_total_pct: float, winrate_ratio: float, trades: int, drawdown_account_ratio: float) -> str:
    results_dir = Path(results_module.strategy_results_dir(strategy))
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"{run_id}.summary.json"
    payload = {
        strategy: {
            "strategy_name": strategy,
            "timeframe": "5m",
            "timerange": None,
            "results_per_pair": [
                {
                    "key": "TOTAL",
                    "profit_total_pct": profit_total_pct,
                    "winrate": winrate_ratio,
                    "trades": trades,
                    "max_drawdown_account": drawdown_account_ratio,
                }
            ],
            "trades": [],
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_optimizer_dedup_signature_is_normalized(monkeypatch, tmp_path):
    _configure_storage(monkeypatch, tmp_path)
    svc = AutoOptimizeService()

    p1 = {"b": 2, "a": 1, "nested": {"z": 9, "y": 8}}
    p2 = {"a": 1, "nested": {"y": 8, "z": 9}, "b": 2}

    s1 = svc._sig(parent_version_id="v1", descriptor="d", parameters=p1)
    s2 = svc._sig(parent_version_id="v1", descriptor="d", parameters=p2)
    assert s1 == s2


def test_optimizer_loop_creates_candidates_dedups_and_finalists(monkeypatch, tmp_path):
    _configure_storage(monkeypatch, tmp_path)

    strategy = "TestStrat"

    # Baseline version (parameter-only baseline for the optimizer to branch from)
    baseline_version = mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy,
            change_type=ChangeType.PARAMETER_CHANGE,
            summary="baseline",
            created_by="tester",
            code="class TestStrat:\n    pass\n",
            parameters={
                "stoploss": -0.2,
                "trailing_stop": False,
                "trailing_stop_positive": 0.02,
                "minimal_roi": {"0": 0.05, "60": 0.02},
                "buy_rsi": 31,
                "buy_params": {"buy_rsi": 31},
            },
            parent_version_id=None,
        )
    )

    baseline_run_id = "bt-baseline"
    baseline_summary_path = _write_summary(
        strategy,
        baseline_run_id,
        profit_total_pct=0.1,
        winrate_ratio=0.5,
        trades=40,
        drawdown_account_ratio=-0.2,
    )

    baseline = BacktestRunRecord(
        run_id=baseline_run_id,
        engine="freqtrade",
        strategy=strategy,
        version_id=baseline_version.version_id,
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
        summary_path=baseline_summary_path,
        artifact_path=None,
        raw_result_path=None,
        result_path=None,
        exit_code=0,
        pid=None,
        error=None,
    )
    PersistenceService().save_backtest_run(baseline_run_id, baseline.model_dump(mode="json"))

    # Fake diagnosis: includes duplicate action to force dedup.
    async def fake_get_diagnosis(run_id: str, include_ai: bool = False):
        return {
            "run_id": run_id,
            "diagnosis": {
                "proposal_actions": [
                    {"action_type": "tighten_stoploss", "label": "Tighten Stoploss"},
                    {"action_type": "tighten_stoploss", "label": "Tighten Stoploss"},
                    {"action_type": "review_exit_timing", "label": "Review Exit Timing"},
                ]
            },
            "ai": {"ai_status": "disabled", "parameter_suggestions": []},
        }

    metrics_queue = [
        {"profit_total_pct": 1.2, "win_rate": 55.0, "total_trades": 40, "max_drawdown_pct": 10.0},
        {"profit_total_pct": 0.8, "win_rate": 48.0, "total_trades": 60, "max_drawdown_pct": 20.0},
        {"profit_total_pct": 1.0, "win_rate": 52.0, "total_trades": 35, "max_drawdown_pct": 15.0},
        {"profit_total_pct": 0.6, "win_rate": 60.0, "total_trades": 90, "max_drawdown_pct": 30.0},
        {"profit_total_pct": 0.4, "win_rate": 58.0, "total_trades": 55, "max_drawdown_pct": 12.0},
        {"profit_total_pct": 1.5, "win_rate": 45.0, "total_trades": 32, "max_drawdown_pct": 25.0},
    ]
    run_counter = {"i": 0}

    async def fake_run_backtest(payload: BacktestRunRequest):
        run_counter["i"] += 1
        run_id = f"bt-cand-{run_counter['i']}"
        metrics = metrics_queue[run_counter["i"] - 1]

        summary_path = _write_summary(
            payload.strategy,
            run_id,
            profit_total_pct=float(metrics["profit_total_pct"]),
            winrate_ratio=float(metrics["win_rate"]) / 100.0,
            trades=int(metrics["total_trades"]),
            drawdown_account_ratio=-abs(float(metrics["max_drawdown_pct"])) / 100.0,
        )

        record = BacktestRunRecord(
            run_id=run_id,
            engine="freqtrade",
            strategy=payload.strategy,
            version_id=payload.version_id,
            request_snapshot={
                "strategy": payload.strategy,
                "timeframe": payload.timeframe,
                "timerange": payload.timerange,
                "pairs": payload.pairs,
                "exchange": payload.exchange,
                "max_open_trades": payload.max_open_trades,
                "dry_run_wallet": payload.dry_run_wallet,
                "extra_flags": payload.extra_flags,
                "trigger_source": payload.trigger_source.value if hasattr(payload.trigger_source, "value") else str(payload.trigger_source),
                "config_path": payload.config_path,
                "engine": "freqtrade",
            },
            request_snapshot_schema_version=1,
            trigger_source=payload.trigger_source,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:01+00:00",
            completed_at="2026-01-01T00:00:02+00:00",
            status=BacktestRunStatus.COMPLETED,
            command="fake backtest",
            summary_path=summary_path,
            artifact_path=None,
            raw_result_path=None,
            result_path=None,
            exit_code=0,
            pid=None,
            error=None,
        )
        PersistenceService().save_backtest_run(run_id, record.model_dump(mode="json"))
        return {"status": record.status.value, "run_id": run_id, "version_id": payload.version_id}

    monkeypatch.setattr(runtime_module, "get_backtest_run_diagnosis", fake_get_diagnosis)
    monkeypatch.setattr(runtime_module, "run_backtest", fake_run_backtest)

    svc = AutoOptimizeService()
    req = OptimizationRunCreateRequest(
        baseline_run_id=baseline_run_id,
        attempts=2,
        beam_width=2,
        branch_factor=3,
        include_ai_suggestions=False,
    )

    run = svc.create_run(req)
    asyncio.run(svc._run_optimizer(run.optimizer_run_id))

    updated = svc.get_run(run.optimizer_run_id)
    assert updated is not None
    assert updated.status == OptimizationRunStatus.COMPLETED
    assert updated.result_kind == OptimizationResultKind.FINALISTS_FOUND
    assert len(updated.finalists) >= 2
    assert len(updated.finalists) <= 3

    # Dedup happened
    assert any(node.status == "deduped" and node.dedup_reason == "normalized_duplicate_candidate" for node in updated.nodes)

    # Baseline anchoring: all created versions use backtest_run:{baseline_run_id}
    for finalist in updated.finalists:
        version = mutation_service.get_version_by_id(finalist.version_id)
        assert version is not None
        assert version.source_ref == f"backtest_run:{baseline_run_id}"
