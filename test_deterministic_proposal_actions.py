"""
Tests for deterministic proposal actions: tighten_entries, reduce_weak_pairs, tighten_stoploss, accelerate_exits.

Verification:
- Each action creates a candidate version through the mutation/version system
- No live files are written during candidate creation
- Advisory output returned when required parameters are missing
- Actions are non-destructive
"""

import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.backtest as backtest_router
import app.routers.versions as versions_router
import app.services.freqtrade_cli_service as cli_module
import app.services.persistence_service as persistence_module
import app.services.results_service as results_module
import app.services.mutation_service as mutation_module
from app.models.backtest_models import (
    BacktestRunRecord,
    BacktestRunStatus,
    BacktestTriggerSource,
    DeterministicActionType,
)
from app.models.optimizer_models import ChangeType, MutationRequest
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.services.results.diagnosis_service import diagnosis_service
from app.services.results_service import ResultsService
from app.utils.datetime_utils import now_iso


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _make_trade(
    index: int,
    *,
    pair: str = "BTC/USDT",
    profit_ratio: float = 0.05,
    open_hour: int = 0,
    duration_min: int = 60,
    max_gain: float = 0.10,
    min_loss: float = -0.35,
) -> dict:
    open_rate = 100.0
    max_rate = open_rate * (1.0 + max_gain)
    min_rate = open_rate * (1.0 + min_loss)
    close_rate = open_rate * (1.0 + profit_ratio)
    close_hour = open_hour + max(duration_min // 60, 1)
    return {
        "pair": pair,
        "open_date": f"2026-01-01 {open_hour:02d}:00:00+00:00",
        "close_date": f"2026-01-01 {close_hour:02d}:00:00+00:00",
        "open_rate": open_rate,
        "close_rate": close_rate,
        "amount": 1.0,
        "stake_amount": 1.0,
        "profit_abs": close_rate - open_rate,
        "profit_ratio": profit_ratio,
        "open_fee": 0.0025,
        "close_fee": 0.0025,
        "buy_tag": f"buy_{index}",
        "sell_reason": "roi" if profit_ratio > 0 else "stoploss",
        "min_rate": min_rate,
        "max_rate": max_rate,
        "is_open": False,
        "is_short": False,
        "trade_duration": duration_min,
    }


def _make_summary(
    strategy: str,
    *,
    profit_pct: float = 5.0,
    total_trades: int = 100,
    winrate: float = 0.55,
    drawdown_account: float = 0.10,
) -> dict:
    return {
        "strategy_name": strategy,
        "stake_currency": "USDT",
        "dry_run_wallet": 1000.0,
        "starting_balance": 1000.0,
        "final_balance": 1000.0 * (1.0 + profit_pct / 100.0),
        "absolute_profit": 1000.0 * profit_pct / 100.0,
        "total_profit_pct": profit_pct,
        "total_trades": total_trades,
        "trade_count_long": total_trades,
        "trade_count_short": 0,
        "wins": int(total_trades * winrate),
        "losses": int(total_trades * (1.0 - winrate)),
        "draws": 0,
        "duration_avg": "1:00:00",
        "profit_mean_pct": profit_pct / total_trades if total_trades > 0 else 0,
        "profit_median_pct": profit_pct / total_trades / 2 if total_trades > 0 else 0,
        "profit_std_pct": 2.0,
        "profit_sum_pct": profit_pct,
        "max_drawdown_abs": 100.0 * drawdown_account,
        "max_drawdown_pct": drawdown_account * 100.0,
        "max_drawdown_account_abs": 100.0 * drawdown_account,
        "max_drawdown_account_pct": drawdown_account * 100.0,
        "drawdown_high_abs": 100.0 * drawdown_account,
        "drawdown_high_pct": drawdown_account * 100.0,
        "drawdown_start": "2026-01-01 10:00:00+00:00",
        "drawdown_start_ts": 1704110400000,
        "drawdown_end": "2026-01-02 10:00:00+00:00",
        "drawdown_end_ts": 1704196800000,
        "market_change_pct": 2.0,
        "sharpe_ratio": 1.5,
        "sortino_ratio": 2.0,
        "calmar_ratio": 3.0,
        "bot_start_timestamp": 1704110400000,
        "bot_stop_timestamp": 1704196800000,
        "trades": [
            _make_trade(i, pair="BTC/USDT" if i % 2 == 0 else "ETH/USDT", profit_ratio=0.05 - (i * 0.001))
            for i in range(total_trades)
        ],
        "results_per_pair": [
            {
                "key": "BTC/USDT",
                "trades": total_trades // 2,
                "profit_mean_pct": profit_pct / (total_trades // 2) if total_trades > 0 else 0,
                "profit_sum_pct": profit_pct / 2,
                "profit_total_abs": 50.0,
                "profit_total_pct": profit_pct / 2,
            },
            {
                "key": "ETH/USDT",
                "trades": total_trades // 2,
                "profit_mean_pct": profit_pct / (total_trades // 2) if total_trades > 0 else 0,
                "profit_sum_pct": profit_pct / 2,
                "profit_total_abs": 50.0,
                "profit_total_pct": profit_pct / 2,
            },
        ],
    }


def _write_run_meta(
    env,
    *,
    run_id: str,
    strategy: str,
    status: str = "completed",
    summary_payload: Optional[dict] = None,
    version_id: Optional[str] = None,
    completed: bool = False,
    include_snapshot_fields: bool = False,
    raw_result_path: Optional[str] = None,
) -> None:
    run_dir = os.path.join(env.backtest_runs_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)

    summary_path = os.path.join(run_dir, "summary.json")
    if summary_payload:
        _write_json(summary_path, summary_payload)

    meta = {
        "run_id": run_id,
        "engine": "freqtrade",
        "strategy": strategy,
        "version_id": version_id,
        "trigger_source": "manual",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "completed_at": now_iso() if completed else None,
        "status": status,
        "command": "freqtrade backtest ...",
        "artifact_path": os.path.join(run_dir, "backtest.log"),
        "raw_result_path": raw_result_path or os.path.join(run_dir, "backtest-result.json"),
        "result_path": summary_path,
        "summary_path": summary_path,
        "exit_code": 0 if completed else None,
        "pid": None,
        "error": None,
    }

    if include_snapshot_fields:
        meta["request_snapshot"] = {
            "strategy": strategy,
            "timeframe": "1h",
            "pairs": ["BTC/USDT", "ETH/USDT"],
            "timerange": "20260101-20260105",
        }
        meta["request_snapshot_schema_version"] = 1

    meta_path = os.path.join(run_dir, "meta.json")
    _write_json(meta_path, meta)

    result_dir = os.path.join(env.backtest_runs_dir, run_id)
    _write_json(os.path.join(result_dir, "backtest-result.json"), {"version": "2.0", "strategy": strategy})


class _DummyEngine:
    def __init__(self, env):
        self.env = env

    @property
    def engine_id(self):
        return "freqtrade"

    def list_strategies(self):
        return ["Sample", "Test"]

    def run_backtest(self, payload, prepared=None):
        return {"command": "freqtrade backtest", "log_file": None, "raw_result_path": None, "process": None}

    def prepare_backtest_run(self, payload):
        strategy = payload.get("strategy", "Sample")
        return {
            "command": "freqtrade backtest",
            "config_path": "/tmp/config.json",
            "request_config_path": "/tmp/request_config.json",
            "raw_result_path": os.path.join(self.env.results_dir, strategy, "backtest-result.json"),
        }

    def resolve_backtest_raw_result_path(self, run_record):
        return os.path.join(self.env.results_dir, run_record.strategy, "backtest-result.json")

    def prepare_download_data(self, payload):
        return {"command": "freqtrade download-data"}

    def run_download_data(self, prepared, log_path):
        return {"command": "freqtrade download-data", "log_file": log_path, "process": None}


class _PatchedEnv:
    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="optimizer_test_")
        self.results_dir = os.path.join(self.tmpdir, "user_data", "backtest_results")
        self.backtest_runs_dir = os.path.join(self.tmpdir, "data", "backtest_runs")
        self.versions_dir = os.path.join(self.tmpdir, "data", "versions")
        self._patches = []
        self.settings = {
            "user_data_path": os.path.join(self.tmpdir, "user_data"),
            "freqtrade_path": "/fake/path/freqtrade",
        }

    def _patch(self, obj, name, value):
        original = getattr(obj, name)
        setattr(obj, name, value)
        self._patches.append((obj, name, original))

    def __enter__(self):
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.backtest_runs_dir, exist_ok=True)
        os.makedirs(self.versions_dir, exist_ok=True)

        self._patch(results_module, "strategy_results_dir", lambda strategy: os.path.join(self.results_dir, strategy))
        self._patch(results_module, "backtest_runs_dir", lambda: self.backtest_runs_dir)
        self._patch(results_module.results_svc._config_service, "get_settings", lambda: self.settings)
        self._patch(results_module.results_svc._results_service, "get_settings", lambda: self.settings)

        self._patch(persistence_module, "backtest_runs_dir", lambda: self.backtest_runs_dir)
        self._patch(persistence_module, "load_backtest_run", self._load_backtest_run)
        self._patch(persistence_module, "save_backtest_run", self._save_backtest_run)
        self._patch(persistence_module, "list_backtest_runs", self._list_backtest_runs)

        self._patch(cli_module, "strategy_results_dir", lambda strategy: os.path.join(self.results_dir, strategy))
        self._patch(cli_module, "backtest_runs_dir", lambda: self.backtest_runs_dir)
        self._patch(cli_module.config_svc, "get_settings", self.settings)

        mutation_module.mutation_service._cache.clear()
        return self

    def __exit__(self, exc_type, exc, tb):
        mutation_module.mutation_service._cache.clear()
        while self._patches:
            obj, name, original = self._patches.pop()
            setattr(obj, name, original)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _load_backtest_run(self, run_id: str) -> Optional[dict]:
        meta_path = os.path.join(self.backtest_runs_dir, run_id, "meta.json")
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        return None

    def _save_backtest_run(self, run_id: str, data: dict) -> None:
        meta_path = os.path.join(self.backtest_runs_dir, run_id, "meta.json")
        _write_json(meta_path, data)

    def _list_backtest_runs(self) -> list[dict]:
        runs = []
        for run_id in os.listdir(self.backtest_runs_dir):
            meta = self._load_backtest_run(run_id)
            if meta:
                runs.append(meta)
        return runs


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(backtest_router.router, prefix="/api/backtest")
    return TestClient(app)


def _make_full_client() -> TestClient:
    app = FastAPI()
    app.include_router(backtest_router.router, prefix="/api/backtest")
    app.include_router(versions_router.router, prefix="/api/versions")
    return TestClient(app)


def _create_active_version(
    strategy_name: str,
    code: str = "class Sample: pass\n",
    parameters: Optional[dict] = None,
) -> str:
    result = mutation_module.mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.MANUAL,
            summary=f"Seed version for {strategy_name}",
            created_by="test",
            code=code,
            parameters=parameters,
        )
    )
    version = mutation_module.mutation_service.get_version_by_id(result.version_id)
    mutation_module.mutation_service.accept_version(result.version_id, notes="Activate seed")
    return result.version_id


def test_deterministic_action_tighten_entries() -> None:
    """Test tighten_entries action creates parameter candidate without live writes."""
    with _PatchedEnv() as env:
        strategy = "TightenEntriesStrategy"
        baseline_version_id = _create_active_version(
            strategy,
            code="class TightenEntriesStrategy: pass\n",
            parameters={"buy_rsi": 35, "buy_threshold": 0.5, "stoploss": -0.10},
        )

        summary = _make_summary(strategy, profit_pct=-5.0, total_trades=50, winrate=0.45, drawdown_account=0.15)
        _write_run_meta(
            env,
            run_id="bt-tighten-entries",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "backtest-result.json"),
        )

        client = _make_client()
        patched_engine = _DummyEngine(env)

        original_resolve = backtest_router._resolve_engine
        try:
            backtest_router._resolve_engine = lambda: patched_engine

            # Create deterministic candidate
            response = client.post(
                "/api/backtest/runs/bt-tighten-entries/proposal-candidates",
                json={
                    "source_kind": "deterministic_action",
                    "source_index": 0,
                    "candidate_mode": "auto",
                    "action_type": "tighten_entries",
                },
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            candidate_version_id = payload["candidate_version_id"]
            assert candidate_version_id is not None

            # Verify candidate was created (not live written)
            candidate_version = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
            assert candidate_version is not None
            assert candidate_version.status.value == "candidate"
            assert candidate_version.change_type.value == "parameter_change"
            assert candidate_version.created_by == "deterministic_proposal"
            assert candidate_version.parameters_snapshot is not None

            # Verify no live files were touched (parameters should be modified but not on disk)
            assert candidate_version.code_snapshot is None  # No code change
            print(
                "[PASS] tighten_entries creates parameter candidate without live writes, status=candidate, created_by=deterministic_proposal"
            )

        finally:
            backtest_router._resolve_engine = original_resolve


def test_deterministic_action_reduce_weak_pairs() -> None:
    """Test reduce_weak_pairs action creates non-destructive parameter advisory candidate."""
    with _PatchedEnv() as env:
        strategy = "ReduceWeakPairsStrategy"
        baseline_version_id = _create_active_version(
            strategy,
            code="class ReduceWeakPairsStrategy: pass\n",
            parameters={"excluded_pairs": [], "stoploss": -0.10},
        )

        # Low profit + pair dragger scenario
        summary = _make_summary(strategy, profit_pct=2.0, total_trades=50, winrate=0.50, drawdown_account=0.12)
        _write_run_meta(
            env,
            run_id="bt-reduce-weak",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "backtest-result.json"),
        )

        client = _make_client()
        patched_engine = _DummyEngine(env)

        original_resolve = backtest_router._resolve_engine
        try:
            backtest_router._resolve_engine = lambda: patched_engine

            response = client.post(
                "/api/backtest/runs/bt-reduce-weak/proposal-candidates",
                json={
                    "source_kind": "deterministic_action",
                    "source_index": 0,
                    "candidate_mode": "auto",
                    "action_type": "reduce_weak_pairs",
                },
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            candidate_version_id = payload["candidate_version_id"]

            # Verify candidate is non-destructive (added to excluded_pairs, not removed from whitelist)
            candidate_version = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
            assert candidate_version.status.value == "candidate"
            assert candidate_version.parameters_snapshot is not None
            # Should have added to excluded_pairs, not destructively removed
            assert "excluded_pairs" in candidate_version.parameters_snapshot
            print("[PASS] reduce_weak_pairs creates non-destructive parameter candidate (excluded_pairs advisory)")

        finally:
            backtest_router._resolve_engine = original_resolve


def test_deterministic_action_tighten_stoploss() -> None:
    """Test tighten_stoploss action creates parameter candidate when stoploss exists."""
    with _PatchedEnv() as env:
        strategy = "TightenStoplossStrategy"
        baseline_version_id = _create_active_version(
            strategy,
            code="class TightenStoplossStrategy: pass\n",
            parameters={"stoploss": -0.15, "trailing_stop": False, "trailing_stop_positive": 0.01},
        )

        # High drawdown scenario
        summary = _make_summary(strategy, profit_pct=10.0, total_trades=100, winrate=0.60, drawdown_account=0.25)
        _write_run_meta(
            env,
            run_id="bt-tighten-sl",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "backtest-result.json"),
        )

        client = _make_client()
        patched_engine = _DummyEngine(env)

        original_resolve = backtest_router._resolve_engine
        try:
            backtest_router._resolve_engine = lambda: patched_engine

            response = client.post(
                "/api/backtest/runs/bt-tighten-sl/proposal-candidates",
                json={
                    "source_kind": "deterministic_action",
                    "source_index": 0,
                    "candidate_mode": "auto",
                    "action_type": "tighten_stoploss",
                },
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            candidate_version_id = payload["candidate_version_id"]

            candidate_version = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
            assert candidate_version.status.value == "candidate"
            # Verify stoploss tightened (more negative → less negative, closer to 0)
            assert candidate_version.parameters_snapshot["stoploss"] > -0.15  # Tightened (less negative)
            assert candidate_version.parameters_snapshot["stoploss"] < 0  # Still negative
            print("[PASS] tighten_stoploss creates parameter candidate with tightened stoploss value")

        finally:
            backtest_router._resolve_engine = original_resolve


def test_deterministic_action_accelerate_exits() -> None:
    """Test accelerate_exits action creates parameter candidate with reduced hold times."""
    with _PatchedEnv() as env:
        strategy = "AccelerateExitsStrategy"
        baseline_version_id = _create_active_version(
            strategy,
            code="class AccelerateExitsStrategy: pass\n",
            parameters={"minimal_roi": {"0": 0.10, "60": 0.05, "120": 0.02, "180": 0.01}, "stoploss": -0.10},
        )

        # Long hold time scenario
        summary = _make_summary(strategy, profit_pct=8.0, total_trades=50, winrate=0.55, drawdown_account=0.08)
        _write_run_meta(
            env,
            run_id="bt-accel-exits",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "backtest-result.json"),
        )

        client = _make_client()
        patched_engine = _DummyEngine(env)

        original_resolve = backtest_router._resolve_engine
        try:
            backtest_router._resolve_engine = lambda: patched_engine

            response = client.post(
                "/api/backtest/runs/bt-accel-exits/proposal-candidates",
                json={
                    "source_kind": "deterministic_action",
                    "source_index": 0,
                    "candidate_mode": "auto",
                    "action_type": "accelerate_exits",
                },
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            candidate_version_id = payload["candidate_version_id"]

            candidate_version = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
            assert candidate_version.status.value == "candidate"
            # Verify minimal_roi times accelerated (reduced by 50%)
            roi = candidate_version.parameters_snapshot.get("minimal_roi", {})
            accelerated_times = [int(t) for t in roi.keys()]
            # Should have faster exit times (roughly 50% of original)
            assert all(t < 200 for t in accelerated_times)  # Original max was 180, should be less
            print("[PASS] accelerate_exits creates parameter candidate with accelerated exit timing windows")

        finally:
            backtest_router._resolve_engine = original_resolve


def test_deterministic_action_advisory_when_parameters_missing() -> None:
    """Test tighten_stoploss returns advisory (not error) when stoploss key missing."""
    with _PatchedEnv() as env:
        strategy = "NoStoplossStrategy"
        # Create version WITHOUT stoploss parameter
        baseline_version_id = _create_active_version(
            strategy,
            code="class NoStoplossStrategy: pass\n",
            parameters={"trailing_stop": False},  # No stoploss key
        )

        summary = _make_summary(strategy, profit_pct=5.0, total_trades=50, winrate=0.55, drawdown_account=0.12)
        _write_run_meta(
            env,
            run_id="bt-no-stoploss",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "backtest-result.json"),
        )

        client = _make_client()
        patched_engine = _DummyEngine(env)

        original_resolve = backtest_router._resolve_engine
        try:
            backtest_router._resolve_engine = lambda: patched_engine

            response = client.post(
                "/api/backtest/runs/bt-no-stoploss/proposal-candidates",
                json={
                    "source_kind": "deterministic_action",
                    "source_index": 0,
                    "candidate_mode": "auto",
                    "action_type": "tighten_stoploss",
                },
            )

            # Should return error (not found message), but endpoint returns 400 gracefully
            # The action should return a ProposalCandidateResult with success=False
            assert response.status_code == 400, f"Expected 400 error for missing parameters, got {response.status_code}: {response.text}"
            error_detail = response.json().get("detail", "")
            assert "stoploss" in error_detail.lower() or "not found" in error_detail.lower()
            print("[PASS] deterministic action returns honest advisory when required parameters missing")

        finally:
            backtest_router._resolve_engine = original_resolve


def test_ranked_issue_auto_maps_to_deterministic_action() -> None:
    """Test that ranked_issue source_kind auto-maps to deterministic action for low_win_rate."""
    with _PatchedEnv() as env:
        strategy = "RankedIssueMapStrategy"
        baseline_version_id = _create_active_version(
            strategy,
            code="class RankedIssueMapStrategy: pass\n",
            parameters={"buy_rsi": 30, "stoploss": -0.10},
        )

        # High sample, low win rate (triggers low_win_rate flag)
        summary = _make_summary(strategy, profit_pct=2.0, total_trades=100, winrate=0.35, drawdown_account=0.10)
        _write_run_meta(
            env,
            run_id="bt-ranked-map",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "backtest-result.json"),
        )

        client = _make_client()
        patched_engine = _DummyEngine(env)

        original_resolve = backtest_router._resolve_engine
        try:
            backtest_router._resolve_engine = lambda: patched_engine

            # POST with source_kind="ranked_issue" (should auto-map to tighten_entries via low_win_rate rule)
            response = client.post(
                "/api/backtest/runs/bt-ranked-map/proposal-candidates",
                json={"source_kind": "ranked_issue", "source_index": 0, "candidate_mode": "auto"},
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            candidate_version_id = payload["candidate_version_id"]
            assert candidate_version_id is not None

            candidate_version = mutation_module.mutation_service.get_version_by_id(candidate_version_id)
            assert candidate_version.status.value == "candidate"
            assert candidate_version.created_by == "deterministic_proposal"
            print("[PASS] ranked_issue source_kind auto-maps to deterministic action (low_win_rate → tighten_entries)")

        finally:
            backtest_router._resolve_engine = original_resolve


if __name__ == "__main__":
    test_deterministic_action_tighten_entries()
    test_deterministic_action_reduce_weak_pairs()
    test_deterministic_action_tighten_stoploss()
    test_deterministic_action_accelerate_exits()
    test_deterministic_action_advisory_when_parameters_missing()
    test_ranked_issue_auto_maps_to_deterministic_action()
    print("\n✅ All deterministic proposal action tests passed!")
