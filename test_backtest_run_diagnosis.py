"""
Smoke tests for run-scoped diagnosis and launch-time run/version linkage.
"""

import json
import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.routers.ai_chat as ai_chat_router
import app.routers.backtest as backtest_router
import app.routers.versions as versions_router
import app.services.freqtrade_cli_service as cli_module
import app.services.persistence_service as persistence_module
import app.services.results_service as results_module
import app.services.mutation_service as mutation_module
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource
from app.models.optimizer_models import ChangeType, MutationRequest
from app.services.freqtrade_cli_service import FreqtradeCliService
from app.services.results.diagnosis_service import diagnosis_service
from app.services.results_service import ResultsService
from app.utils.datetime_utils import now_iso


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _write_raw_zip(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_name = f"{os.path.splitext(os.path.basename(path))[0]}.json"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(json_name, json.dumps(payload))


def _make_trade(index: int, *, pair: str = "BTC/USDT", profit_ratio: float = 0.05, open_hour: int = 0, duration_min: int = 60, max_gain: float = 0.10, min_loss: float = -0.35) -> dict:
    open_rate = 100.0
    max_rate = open_rate * (1.0 + max_gain)
    min_rate = open_rate * (1.0 + min_loss)
    close_rate = open_rate * (1.0 + profit_ratio)
    close_hour = open_hour + max(duration_min // 60, 1)
    return {
        "pair": pair,
        "open_date": f"2026-01-01 {open_hour:02d}:00:00+00:00",
        "close_date": f"2026-01-01 {close_hour:02d}:00:00+00:00",
        "trade_duration": duration_min,
        "profit_ratio": profit_ratio,
        "profit_abs": round(profit_ratio * 10.0, 4),
        "open_rate": open_rate,
        "close_rate": close_rate,
        "max_rate": max_rate,
        "min_rate": min_rate,
        "stop_loss_ratio": -0.30,
        "is_open": False,
        "is_short": False,
    }


def _make_summary(strategy: str, *, profit_pct: float = 5.0, total_trades: int = 6, winrate: float = 0.5, drawdown_account: float = 0.05, results_per_pair: list[dict] | None = None, trades: list[dict] | None = None) -> dict:
    total_row = {
        "key": "TOTAL",
        "profit_total_pct": profit_pct,
        "profit_total_abs": round(profit_pct / 2.0, 2),
        "trades": total_trades,
        "winrate": winrate,
        "max_drawdown_account": drawdown_account,
        "duration_avg": "4:00:00",
        "sharpe": 1.1,
        "sortino": 1.5,
        "calmar": 1.2,
    }
    rows = results_per_pair or [
        total_row,
        {"key": "BTC/USDT", "profit_total_pct": profit_pct - 1.0, "trades": max(total_trades // 2, 1)},
        {"key": "ETH/USDT", "profit_total_pct": 1.5, "trades": max(total_trades // 2, 1)},
    ]
    block = {
        "strategy_name": strategy,
        "timeframe": "5m",
        "timerange": "20260101-20260110",
        "stake_currency": "USDT",
        "profit_total_pct": profit_pct,
        "profit_total_abs": round(profit_pct / 2.0, 2),
        "results_per_pair": rows,
        "trades": trades or [_make_trade(0), _make_trade(1, pair="ETH/USDT", profit_ratio=-0.02, open_hour=3)],
        "holding_avg": "4:00:00",
        "holding_avg_s": 14400.0,
        "winner_holding_avg": "0d 01:00",
        "winner_holding_avg_s": 3600.0,
        "loser_holding_avg": "0d 05:00",
        "loser_holding_avg_s": 18000.0,
        "max_drawdown_account": drawdown_account,
        "winrate": winrate,
    }
    return {strategy: block}


class _DummyEngine:
    engine_id = "freqtrade"

    def __init__(self, env):
        self._env = env

    def prepare_backtest_run(self, payload: dict) -> dict:
        config_path = payload.get("config_path") or self._env.default_config_path
        return {
            "command": f"freqtrade backtesting --strategy {payload['strategy']} --config {config_path}",
            "raw_result_path": None,
            "config_path": config_path,
        }

    def run_backtest(self, payload: dict, prepared: dict | None = None) -> dict:
        prepared = prepared or self.prepare_backtest_run(payload)
        return {
            "command": prepared["command"],
            "log_file": os.path.join(self._env.results_dir, payload["strategy"], f"{payload['run_id']}.backtest.log"),
            "raw_result_path": prepared.get("raw_result_path"),
            "pid": 4321,
            "process": None,
        }


class _CapturingFreqtradeEngine:
    engine_id = "freqtrade"

    def __init__(self, env):
        self._env = env
        self._cli = FreqtradeCliService()

    def prepare_backtest_run(self, payload: dict) -> dict:
        prepared = self._cli.prepare_backtest_run(payload)
        self._env.last_prepared = prepared
        self._env.last_launch_payload = dict(payload)
        return prepared

    def run_backtest(self, payload: dict, prepared: dict | None = None) -> dict:
        prepared = prepared or self.prepare_backtest_run(payload)
        self._env.last_prepared = prepared
        self._env.last_launch_payload = dict(payload)
        return {
            "command": prepared["command"],
            "log_file": os.path.join(self._env.results_dir, payload["strategy"], f"{payload['run_id']}.backtest.log"),
            "raw_result_path": prepared.get("raw_result_path"),
            "pid": 4321,
            "process": None,
        }


class _PatchedEnv:
    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bt-diagnosis-")
        self.data_dir = os.path.join(self.tmpdir, "data")
        self.backtest_runs_dir = os.path.join(self.data_dir, "backtest_runs")
        self.download_runs_dir = os.path.join(self.data_dir, "download_runs")
        self.versions_root = os.path.join(self.data_dir, "versions")
        self.user_data_dir = os.path.join(self.tmpdir, "user_data")
        self.results_dir = os.path.join(self.user_data_dir, "backtest_results")
        self.strategies_dir = os.path.join(self.user_data_dir, "strategies")
        self.config_dir = os.path.join(self.user_data_dir, "config")
        self.default_config_path = os.path.join(self.user_data_dir, "config.json")
        self.last_prepared = None
        self.last_launch_payload = None
        os.makedirs(self.backtest_runs_dir, exist_ok=True)
        os.makedirs(self.download_runs_dir, exist_ok=True)
        os.makedirs(self.versions_root, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.strategies_dir, exist_ok=True)
        os.makedirs(self.config_dir, exist_ok=True)
        _write_json(self.default_config_path, {"stake_currency": "USDT"})
        self._patches = []

    def settings(self) -> dict:
        return {
            "engine": "freqtrade",
            "freqtrade_path": "",
            "user_data_path": self.user_data_dir,
            "config_path": self.default_config_path,
        }

    def _patch(self, obj, name, value) -> None:
        self._patches.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def __enter__(self):
        self._patch(persistence_module, "backtest_runs_dir", lambda: self.backtest_runs_dir)
        self._patch(results_module, "strategy_results_dir", lambda strategy: os.path.join(self.results_dir, strategy))
        self._patch(results_module, "user_data_results_dir", lambda: self.results_dir)
        self._patch(backtest_router, "user_data_results_dir", lambda: self.results_dir)
        self._patch(mutation_module, "storage_dir", lambda: self.data_dir)
        self._patch(mutation_module, "strategy_versions_dir", lambda strategy: os.path.join(self.versions_root, strategy))
        self._patch(mutation_module, "strategy_active_version_file", lambda strategy: os.path.join(self.versions_root, strategy, "active_version.json"))
        self._patch(mutation_module, "strategy_version_file", lambda strategy, version_id: os.path.join(self.versions_root, strategy, f"{version_id}.json"))
        self._patch(backtest_router, "live_strategy_file", lambda strategy_name, user_data_path=None: os.path.join(self.strategies_dir, f"{strategy_name}.py"))
        self._patch(backtest_router, "strategy_config_file", lambda strategy_name, user_data_path=None: os.path.join(self.config_dir, f"config_{strategy_name}.json"))
        self._patch(backtest_router.config_svc, "get_settings", self.settings)
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


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(backtest_router.router, prefix="/api/backtest")
    return TestClient(app)


def _make_full_client() -> TestClient:
    app = FastAPI()
    app.include_router(backtest_router.router, prefix="/api/backtest")
    app.include_router(versions_router.router, prefix="/api/versions")
    app.include_router(ai_chat_router.router, prefix="/api/ai/chat")
    return TestClient(app)


@contextmanager
def _patched_engine(env: _PatchedEnv, engine_cls=_DummyEngine):
    original = backtest_router._resolve_engine
    backtest_router._resolve_engine = lambda: engine_cls(env)
    try:
        yield
    finally:
        backtest_router._resolve_engine = original


def _create_active_version(
    strategy_name: str,
    code: str = "class Sample: pass\n",
    parameters: dict | None = None,
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
    accepted = mutation_module.mutation_service.accept_version(result.version_id, notes="Seed active version")
    assert accepted.status == "accepted", accepted
    return result.version_id


def _write_run_meta(env: _PatchedEnv, *, run_id: str, strategy: str, status: str, summary_payload: dict | None = None, summary_text: str | None = None, error: str | None = None, version_id: str | None = None, completed: bool = False, include_snapshot_fields: bool = True, raw_result_path: str | None = None, summary_path: str | None = None, pid: int | None = None, created_at: str = "2026-04-10T10:00:00+00:00") -> dict:
    strategy_dir = os.path.join(env.results_dir, strategy)
    os.makedirs(strategy_dir, exist_ok=True)

    if summary_payload is not None:
        summary_path = summary_path or os.path.join(strategy_dir, f"{run_id}.summary.json")
        _write_json(summary_path, summary_payload)
    elif summary_text is not None:
        summary_path = summary_path or os.path.join(strategy_dir, f"{run_id}.summary.json")
        _write_text(summary_path, summary_text)

    run_meta = {
        "run_id": run_id,
        "engine": "freqtrade",
        "strategy": strategy,
        "version_id": version_id,
        "trigger_source": "manual",
        "created_at": created_at,
        "updated_at": "2026-04-10T10:00:00+00:00",
        "completed_at": "2026-04-10T10:30:00+00:00" if completed else None,
        "status": status,
        "command": f"freqtrade backtesting --strategy {strategy}",
        "artifact_path": os.path.join(strategy_dir, f"{run_id}.backtest.log"),
        "raw_result_path": raw_result_path,
        "result_path": None,
        "summary_path": summary_path,
        "exit_code": 0 if status == "completed" else 1 if status == "failed" else None,
        "pid": pid,
        "error": error,
    }
    if include_snapshot_fields:
        run_meta["request_snapshot"] = {
            "strategy": strategy,
            "timeframe": "5m",
            "timerange": "20260101-20260110",
            "pairs": ["BTC/USDT", "ETH/USDT"],
            "exchange": "binance",
            "max_open_trades": 2,
            "dry_run_wallet": 1000,
            "extra_flags": [],
            "trigger_source": "manual",
            "config_path": env.default_config_path,
            "engine": "freqtrade",
        }
        run_meta["request_snapshot_schema_version"] = 1

    _write_json(os.path.join(env.backtest_runs_dir, run_id, "run_meta.json"), run_meta)
    return run_meta


def test_freqtrade_cli_resolves_launch_config_path() -> None:
    with _PatchedEnv() as env:
        cli = FreqtradeCliService()
        custom_config = os.path.join(env.tmpdir, "custom-config.json")
        prepared = cli.prepare_backtest_run({
            "run_id": "bt-cli-custom",
            "strategy": "Alpha",
            "timeframe": "5m",
            "config_path": custom_config,
        })
        assert prepared["config_path"] == custom_config
        assert custom_config in prepared["command"]

        backtest_router.config_svc.get_settings = lambda: {
            "engine": "freqtrade",
            "freqtrade_path": "",
            "user_data_path": env.user_data_dir,
            "config_path": "",
        }
        cli_module.config_svc.get_settings = backtest_router.config_svc.get_settings
        prepared_default = cli.prepare_backtest_run({
            "run_id": "bt-cli-default",
            "strategy": "Alpha",
            "timeframe": "5m",
        })
        assert prepared_default["config_path"] == env.default_config_path
        print("[PASS] Freqtrade CLI resolves launch config path")


def test_run_persists_request_snapshot_and_resolves_active_version() -> None:
    with _PatchedEnv() as env, _patched_engine(env):
        strategy = "ActiveLinkedStrategy"
        _write_text(os.path.join(env.strategies_dir, f"{strategy}.py"), "class ActiveLinkedStrategy: pass\n")
        active_version_id = _create_active_version(strategy)

        client = _make_client()
        response = client.post("/api/backtest/run", json={
            "strategy": strategy,
            "timeframe": "5m",
            "timerange": "20260101-20260110",
            "pairs": ["BTC/USDT", "ETH/USDT"],
            "exchange": "binance",
            "max_open_trades": 2,
            "dry_run_wallet": 1000,
            "config_path": os.path.join(env.tmpdir, "chosen-config.json"),
            "extra_flags": ["--cache", "none"],
        })
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["version_id"] == active_version_id

        run_meta = persistence_module.PersistenceService().load_backtest_run(payload["run_id"])
        assert run_meta["version_id"] == active_version_id
        assert run_meta["request_snapshot_schema_version"] == 1
        assert run_meta["request_snapshot"] == {
            "strategy": strategy,
            "timeframe": "5m",
            "timerange": "20260101-20260110",
            "pairs": ["BTC/USDT", "ETH/USDT"],
            "exchange": "binance",
            "max_open_trades": 2,
            "dry_run_wallet": 1000,
            "extra_flags": ["--cache", "none"],
            "trigger_source": "manual",
            "config_path": os.path.join(env.tmpdir, "chosen-config.json"),
            "engine": "freqtrade",
        }
        version = mutation_module.mutation_service.get_version_by_id(active_version_id)
        assert version.backtest_run_id == payload["run_id"]
        print("[PASS] Run launch resolves active version and persists request snapshot")


def test_run_bootstraps_minimal_initial_version() -> None:
    with _PatchedEnv() as env, _patched_engine(env):
        strategy = "BootstrappedStrategy"
        strategy_code = "class BootstrappedStrategy: pass\n"
        strategy_config = {"max_open_trades": 4, "stake_currency": "USDT"}
        _write_text(os.path.join(env.strategies_dir, f"{strategy}.py"), strategy_code)
        _write_json(os.path.join(env.config_dir, f"config_{strategy}.json"), strategy_config)

        client = _make_client()
        response = client.post("/api/backtest/run", json={
            "strategy": strategy,
            "timeframe": "5m",
            "pairs": ["BTC/USDT"],
        })
        assert response.status_code == 200, response.text
        version_id = response.json()["version_id"]
        version = mutation_module.mutation_service.get_version_by_id(version_id)
        assert version is not None
        assert version.status.value == "active"
        assert version.change_type.value == "initial"
        assert version.code_snapshot == strategy_code
        assert version.parameters_snapshot == strategy_config

        run_meta = persistence_module.PersistenceService().load_backtest_run(response.json()["run_id"])
        assert run_meta["version_id"] == version_id
        assert run_meta["request_snapshot_schema_version"] == 1
        print("[PASS] Run launch bootstraps and accepts a minimal INITIAL version")


def test_results_service_summary_states() -> None:
    with _PatchedEnv() as env:
        strategy = "StateStrategy"
        summary_path = os.path.join(env.results_dir, strategy, "bt-ready.summary.json")
        _write_json(summary_path, _make_summary(strategy))
        run = BacktestRunRecord(
            run_id="bt-ready",
            strategy=strategy,
            version_id=None,
            request_snapshot={},
            request_snapshot_schema_version=None,
            trigger_source=BacktestTriggerSource.MANUAL,
            created_at=now_iso(),
            updated_at=now_iso(),
            completed_at=None,
            status=BacktestRunStatus.COMPLETED,
            command="freqtrade backtesting",
            summary_path=summary_path,
        )
        svc = ResultsService()
        ready = svc.load_run_summary_state(run)
        assert ready["state"] == "ready"
        assert isinstance(ready["summary"], dict)

        missing = svc.load_run_summary_state(run.model_copy(update={"summary_path": os.path.join(env.results_dir, strategy, "missing.summary.json")}))
        assert missing["state"] == "missing"

        broken_path = os.path.join(env.results_dir, strategy, "bt-broken.summary.json")
        _write_text(broken_path, "{not-json}")
        broken = svc.load_run_summary_state(run.model_copy(update={"summary_path": broken_path}))
        assert broken["state"] == "load_failed"
        assert str(broken["error"]).startswith("summary_load_failed:")
        print("[PASS] ResultsService returns ready, missing, and load_failed summary states")


def test_diagnosis_rules_and_insufficient_evidence() -> None:
    run = BacktestRunRecord(
        run_id="bt-diagnosis",
        strategy="DiagStrategy",
        version_id="v-diag",
        request_snapshot={},
        request_snapshot_schema_version=None,
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at=now_iso(),
        updated_at=now_iso(),
        completed_at=now_iso(),
        status=BacktestRunStatus.COMPLETED,
        command="freqtrade backtesting",
    )
    summary_metrics = {
        "profit_total_pct": -7.0,
        "win_rate": 30.0,
        "total_trades": 8,
        "pair_count": 2,
        "max_drawdown_pct": 28.0,
        "timerange": "20260101-20260102",
    }
    summary_block = {
        "holding_avg_s": 90000.0,
        "winner_holding_avg_s": 3600.0,
        "loser_holding_avg_s": 18000.0,
    }
    results_per_pair = [
        {"key": "TOTAL", "profit_total_pct": -7.0, "trades": 8},
        {"key": "BTC/USDT", "profit_total_pct": -6.5, "trades": 5},
        {"key": "ETH/USDT", "profit_total_pct": 1.5, "trades": 3},
    ]
    trades = [
        _make_trade(0, pair="BTC/USDT", profit_ratio=-0.02, open_hour=0, duration_min=90),
        _make_trade(1, pair="BTC/USDT", profit_ratio=-0.03, open_hour=1, duration_min=120),
        _make_trade(2, pair="BTC/USDT", profit_ratio=-0.01, open_hour=2, duration_min=150),
        _make_trade(3, pair="BTC/USDT", profit_ratio=0.05, open_hour=3, duration_min=60),
        _make_trade(4, pair="BTC/USDT", profit_ratio=0.04, open_hour=4, duration_min=80),
        _make_trade(5, pair="ETH/USDT", profit_ratio=-0.02, open_hour=5, duration_min=100),
        _make_trade(6, pair="ETH/USDT", profit_ratio=0.05, open_hour=6, duration_min=70),
        _make_trade(7, pair="ETH/USDT", profit_ratio=-0.02, open_hour=7, duration_min=120),
    ]
    request_snapshot = {
        "pairs": ["BTC/USDT", "ETH/USDT"],
        "timerange": "20260101-20260102",
    }

    diagnosis = diagnosis_service.diagnose_run(
        run_record=run,
        summary_metrics=summary_metrics,
        summary_block=summary_block,
        trades=trades,
        results_per_pair=results_per_pair,
        request_snapshot=request_snapshot,
        request_snapshot_schema_version=None,
        linked_version=None,
    )
    rules = {flag["rule"] for flag in diagnosis["ranked_issues"]}
    assert {
        "negative_profit",
        "low_sample_size",
        "low_win_rate",
        "high_drawdown",
        "overtrading",
        "long_hold_time",
        "pair_dragger",
        "exit_inefficiency",
    }.issubset(rules)
    assert diagnosis["facts"]["trades_per_day_per_pair"] == 4.0
    assert diagnosis["facts"]["avg_mfe_captured_pct"] is not None
    assert diagnosis["facts"]["avg_mfe_captured_pct"] < 60.0
    assert diagnosis["facts"]["late_stop_flag"] is True
    proposal_action_types = [item["action_type"] for item in diagnosis["proposal_actions"]]
    assert proposal_action_types == [
        "tighten_entries",
        "tighten_stoploss",
        "review_exit_timing",
        "reduce_weak_pairs",
    ]

    insufficient = diagnosis_service.diagnose_run(
        run_record=run,
        summary_metrics={
            "profit_total_pct": 2.0,
            "win_rate": 55.0,
            "total_trades": 40,
            "pair_count": 2,
            "max_drawdown_pct": 4.0,
            "timerange": "20260101-20260110",
        },
        summary_block={},
        trades=[],
        results_per_pair=[],
        request_snapshot={},
        request_snapshot_schema_version=None,
        linked_version=None,
    )
    assert "pair_dragger" in insufficient["insufficient_evidence"]
    assert "exit_inefficiency" in insufficient["insufficient_evidence"]
    flagged_rules = {flag["rule"] for flag in insufficient["ranked_issues"]}
    assert "pair_dragger" not in flagged_rules
    assert "exit_inefficiency" not in flagged_rules
    print("[PASS] Deterministic diagnosis emits rule flags and insufficiency markers correctly")


def test_proposal_candidate_endpoint_supports_all_sources() -> None:
    with _PatchedEnv() as env:
        strategy = "ProposalStrategy"
        baseline_version_id = _create_active_version(strategy, code="class ProposalStrategy: pass\n")
        summary = _make_summary(
            strategy,
            profit_pct=-7.0,
            total_trades=8,
            winrate=0.30,
            drawdown_account=0.28,
            trades=[
                _make_trade(0, pair="BTC/USDT", profit_ratio=-0.02, open_hour=0, duration_min=90),
                _make_trade(1, pair="BTC/USDT", profit_ratio=-0.03, open_hour=1, duration_min=120),
                _make_trade(2, pair="BTC/USDT", profit_ratio=0.05, open_hour=2, duration_min=60),
                _make_trade(3, pair="ETH/USDT", profit_ratio=-0.02, open_hour=3, duration_min=100),
            ],
        )
        _write_run_meta(
            env,
            run_id="bt-proposal",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-proposal.backtest.zip"),
        )

        captured_calls = []

        async def _overlay_ok(**kwargs):
            return {
                "summary": "Overlay summary",
                "priorities": ["Tighten stops"],
                "rationale": ["Drawdown is elevated"],
                "parameter_suggestions": [{"name": "stoploss", "value": -0.08, "reason": "Cut losses sooner"}],
                "ai_status": "ready",
            }

        async def _fake_create_candidate(**kwargs):
            captured_calls.append(kwargs)
            mutation = mutation_module.mutation_service.create_mutation(
                MutationRequest(
                    strategy_name=kwargs["strategy_name"],
                    change_type=ChangeType.PARAMETER_CHANGE,
                    summary=f"AI proposal candidate from run {kwargs['run_id']} using {kwargs['source_kind']}[{kwargs['source_index']}]",
                    created_by="ai_apply",
                    parameters={"stoploss": -0.08},
                    parent_version_id=kwargs["linked_version"].version_id,
                    source_ref=f"backtest_run:{kwargs['run_id']}",
                )
            )
            version = mutation_module.mutation_service.get_version_by_id(mutation.version_id)
            return SimpleNamespace(
                success=True,
                message="Candidate staged",
                version_id=mutation.version_id,
                candidate_change_type=version.change_type.value,
                candidate_status=version.status.value,
                source_title=f"{kwargs['source_kind']} source",
                ai_mode="parameter_only",
                error=None,
            )

        original_overlay = backtest_router.analyze_run_diagnosis_overlay
        original_create_candidate = backtest_router.create_proposal_candidate_from_diagnosis
        client = _make_client()
        try:
            backtest_router.analyze_run_diagnosis_overlay = _overlay_ok
            backtest_router.create_proposal_candidate_from_diagnosis = _fake_create_candidate

            for source_kind in ("ranked_issue", "parameter_hint", "ai_parameter_suggestion"):
                response = client.post(
                    "/api/backtest/runs/bt-proposal/proposal-candidates",
                    json={"source_kind": source_kind, "source_index": 0, "candidate_mode": "auto"},
                )
                assert response.status_code == 200, response.text
                payload = response.json()
                assert payload["baseline_run_id"] == "bt-proposal"
                assert payload["baseline_version_id"] == baseline_version_id
                assert payload["baseline_version_source"] == "run"
                assert payload["candidate_change_type"] == "parameter_change"
                assert payload["candidate_status"] == "candidate"

                version = mutation_module.mutation_service.get_version_by_id(payload["candidate_version_id"])
                assert version is not None
                assert version.created_by == "ai_apply"
                assert version.parent_version_id == baseline_version_id
                assert version.source_ref == "backtest_run:bt-proposal"

            assert [call["source_kind"] for call in captured_calls] == [
                "ranked_issue",
                "parameter_hint",
                "ai_parameter_suggestion",
            ]
            print("[PASS] Proposal candidate endpoint supports ranked issues, parameter hints, and AI suggestions")
        finally:
            backtest_router.analyze_run_diagnosis_overlay = original_overlay
            backtest_router.create_proposal_candidate_from_diagnosis = original_create_candidate


def test_proposal_candidate_endpoint_falls_back_to_active_version_for_historical_run() -> None:
    with _PatchedEnv() as env:
        strategy = "HistoricalProposalStrategy"
        active_version_id = _create_active_version(strategy, code="class HistoricalProposalStrategy: pass\n")
        summary = _make_summary(strategy, profit_pct=-6.0, total_trades=8, winrate=0.35, drawdown_account=0.20)
        _write_run_meta(
            env,
            run_id="bt-historical",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=None,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-historical.backtest.zip"),
        )

        captured = {}

        async def _fake_create_candidate(**kwargs):
            captured.update(kwargs)
            mutation = mutation_module.mutation_service.create_mutation(
                MutationRequest(
                    strategy_name=kwargs["strategy_name"],
                    change_type=ChangeType.PARAMETER_CHANGE,
                    summary="Fallback proposal candidate",
                    created_by="ai_apply",
                    parameters={"stoploss": -0.07},
                    parent_version_id=kwargs["linked_version"].version_id if kwargs.get("linked_version") else None,
                    source_ref=f"backtest_run:{kwargs['run_id']}",
                )
            )
            version = mutation_module.mutation_service.get_version_by_id(mutation.version_id)
            return SimpleNamespace(
                success=True,
                message="Candidate staged",
                version_id=mutation.version_id,
                candidate_change_type=version.change_type.value,
                candidate_status=version.status.value,
                source_title="fallback source",
                ai_mode="parameter_only",
                error=None,
            )

        original_create_candidate = backtest_router.create_proposal_candidate_from_diagnosis
        client = _make_client()
        try:
            backtest_router.create_proposal_candidate_from_diagnosis = _fake_create_candidate
            response = client.post(
                "/api/backtest/runs/bt-historical/proposal-candidates",
                json={"source_kind": "parameter_hint", "source_index": 0, "candidate_mode": "auto"},
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["baseline_run_version_id"] is None
            assert payload["baseline_version_id"] == active_version_id
            assert payload["baseline_version_source"] == "active_fallback"
            assert captured["linked_version"].version_id == active_version_id
            print("[PASS] Proposal candidate endpoint falls back to the active version for historical runs")
        finally:
            backtest_router.create_proposal_candidate_from_diagnosis = original_create_candidate


def test_deterministic_action_creates_parameter_candidate_without_ai() -> None:
    with _PatchedEnv() as env:
        strategy = "DeterministicActionStrategy"
        baseline_version_id = _create_active_version(
            strategy,
            code="class DeterministicActionStrategy: pass\n",
            parameters={
                "stoploss": -0.10,
                "trailing_stop": False,
                "trailing_stop_positive": 0.02,
            },
        )
        summary = _make_summary(
            strategy,
            profit_pct=-6.0,
            total_trades=12,
            winrate=0.42,
            drawdown_account=0.30,
            results_per_pair=[
                {"key": "TOTAL", "profit_total_pct": -6.0, "trades": 12, "winrate": 0.42, "max_drawdown_account": 0.30},
                {"key": "BTC/USDT", "profit_total_pct": -4.0, "trades": 6},
                {"key": "ETH/USDT", "profit_total_pct": -2.0, "trades": 6},
            ],
        )
        _write_run_meta(
            env,
            run_id="bt-deterministic-action",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-deterministic-action.backtest.zip"),
        )

        client = _make_full_client()
        response = client.post(
            "/api/backtest/runs/bt-deterministic-action/proposal-candidates",
            json={
                "source_kind": "deterministic_action",
                "source_index": 0,
                "candidate_mode": "auto",
                "action_type": "tighten_stoploss",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        version = mutation_module.mutation_service.get_version_by_id(payload["candidate_version_id"])
        assert version is not None
        assert version.created_by == "deterministic_proposal"
        assert version.parent_version_id == baseline_version_id
        assert version.source_ref == "backtest_run:bt-deterministic-action"
        assert version.change_type.value == "parameter_change"
        assert version.parameters_snapshot["stoploss"] == -0.075
        assert version.parameters_snapshot["trailing_stop"] is True
        assert version.parameters_snapshot["trailing_stop_positive"] == 0.01
        print("[PASS] Deterministic proposal actions create parameter candidates without AI")


def test_ai_chat_apply_parameters_uses_unified_run_scoped_candidate_path() -> None:
    with _PatchedEnv() as env:
        strategy = "AiChatUnifiedStrategy"
        baseline_version_id = _create_active_version(
            strategy,
            code="class AiChatUnifiedStrategy: pass\n",
            parameters={"stoploss": -0.10},
        )
        summary = _make_summary(strategy, profit_pct=-4.0, total_trades=10, winrate=0.45, drawdown_account=0.12)
        _write_run_meta(
            env,
            run_id="bt-ai-chat-unified",
            strategy=strategy,
            status="completed",
            summary_payload=summary,
            version_id=baseline_version_id,
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-ai-chat-unified.backtest.zip"),
        )

        client = _make_full_client()
        response = client.post(
            "/api/ai/chat/apply-parameters",
            json={
                "run_id": "bt-ai-chat-unified",
                "strategy_name": strategy,
                "parameters": {"stoploss": -0.08},
                "summary": "AI chat suggested tighter stoploss",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        version = mutation_module.mutation_service.get_version_by_id(payload["version_id"])
        assert version is not None
        assert version.created_by == "ai_apply"
        assert version.parent_version_id == baseline_version_id
        assert version.source_ref == "backtest_run:bt-ai-chat-unified"
        assert version.change_type.value == "parameter_change"
        assert version.parameters_snapshot == {"stoploss": -0.08}
        print("[PASS] AI chat parameter candidates use the unified run-scoped proposal lifecycle")


def test_versions_reject_and_rollback_workflow() -> None:
    with _PatchedEnv() as env:
        strategy = "VersionWorkflowStrategy"
        baseline_version_id = _create_active_version(strategy, code="class VersionWorkflowStrategy: pass\n")
        rejected_candidate = mutation_module.mutation_service.create_mutation(
            MutationRequest(
                strategy_name=strategy,
                change_type=ChangeType.PARAMETER_CHANGE,
                summary="Reject me",
                created_by="ai_apply",
                parameters={"stoploss": -0.08},
                parent_version_id=baseline_version_id,
            )
        ).version_id
        accepted_candidate = mutation_module.mutation_service.create_mutation(
            MutationRequest(
                strategy_name=strategy,
                change_type=ChangeType.PARAMETER_CHANGE,
                summary="Promote me",
                created_by="ai_apply",
                parameters={"stoploss": -0.07},
                parent_version_id=baseline_version_id,
            )
        ).version_id

        client = _make_full_client()

        reject_response = client.post(
            f"/api/versions/{strategy}/reject",
            json={"version_id": rejected_candidate, "reason": "Not convincing"},
        )
        assert reject_response.status_code == 200, reject_response.text
        assert mutation_module.mutation_service.get_version_by_id(rejected_candidate).status.value == "rejected"

        accept_response = client.post(
            f"/api/versions/{strategy}/accept",
            json={"version_id": accepted_candidate, "notes": "Promote candidate"},
        )
        assert accept_response.status_code == 200, accept_response.text
        assert mutation_module.mutation_service.get_version_by_id(accepted_candidate).status.value == "active"

        rollback_response = client.post(
            f"/api/versions/{strategy}/rollback",
            json={"target_version_id": baseline_version_id, "reason": "Restore baseline"},
        )
        assert rollback_response.status_code == 200, rollback_response.text
        assert mutation_module.mutation_service.get_version_by_id(baseline_version_id).status.value == "active"
        print("[PASS] Version reject and rollback workflow updates version state correctly")



def test_run_materializes_explicit_candidate_workspace() -> None:
    with _PatchedEnv() as env, _patched_engine(env, _CapturingFreqtradeEngine):
        strategy = "WorkspaceCandidateStrategy"
        live_code = "class WorkspaceCandidateStrategy:\n    origin = 'live'\n"
        baseline_code = "class WorkspaceCandidateStrategy:\n    origin = 'baseline'\n"
        candidate_code = "class WorkspaceCandidateStrategy:\n    origin = 'candidate'\n"
        _write_text(os.path.join(env.strategies_dir, f"{strategy}.py"), live_code)
        baseline_version_id = _create_active_version(strategy, code=baseline_code)
        candidate_version_id = mutation_module.mutation_service.create_mutation(
            MutationRequest(
                strategy_name=strategy,
                change_type=ChangeType.CODE_CHANGE,
                summary="Workspace candidate",
                created_by="ai_apply",
                code=candidate_code,
                parameters={"stoploss": -0.07},
                parent_version_id=baseline_version_id,
            )
        ).version_id

        client = _make_client()
        response = client.post(
            "/api/backtest/run",
            json={
                "strategy": strategy,
                "timeframe": "5m",
                "pairs": ["BTC/USDT"],
                "version_id": candidate_version_id,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        prepared = env.last_prepared
        assert prepared is not None
        assert payload["version_id"] == candidate_version_id
        assert prepared["strategy_path"] == os.path.join(
            env.backtest_runs_dir,
            payload["run_id"],
            "workspace",
            "strategies",
        )
        assert prepared["config_paths"][0] == env.default_config_path
        assert prepared["config_paths"][1] == prepared["config_overlay_path"]
        assert "--strategy-path" in prepared["cmd"]
        assert prepared["strategy_path"] in prepared["cmd"]

        with open(prepared["strategy_file"], "r", encoding="utf-8") as handle:
            assert handle.read() == candidate_code
        with open(prepared["config_overlay_path"], "r", encoding="utf-8") as handle:
            assert json.load(handle) == {"stoploss": -0.07}

        run_meta = persistence_module.PersistenceService().load_backtest_run(payload["run_id"])
        assert run_meta["request_snapshot"]["config_path"] == env.default_config_path
        print("[PASS] Explicit candidate run materializes version-exact workspace artifacts")


def test_parameter_candidate_run_inherits_parent_code_and_merges_parameters() -> None:
    with _PatchedEnv() as env, _patched_engine(env, _CapturingFreqtradeEngine):
        strategy = "InheritedWorkspaceStrategy"
        live_code = "class InheritedWorkspaceStrategy:\n    origin = 'live'\n"
        parent_code = "class InheritedWorkspaceStrategy:\n    origin = 'parent'\n"
        _write_text(os.path.join(env.strategies_dir, f"{strategy}.py"), live_code)
        baseline_version_id = _create_active_version(
            strategy,
            code=parent_code,
            parameters={
                "max_open_trades": 1,
                "nested": {"left": 1, "right": 1},
            },
        )
        candidate_version_id = mutation_module.mutation_service.create_mutation(
            MutationRequest(
                strategy_name=strategy,
                change_type=ChangeType.PARAMETER_CHANGE,
                summary="Parameter workspace candidate",
                created_by="ai_apply",
                parameters={
                    "nested": {"right": 2},
                    "dry_run_wallet": 250,
                },
                parent_version_id=baseline_version_id,
            )
        ).version_id

        client = _make_client()
        response = client.post(
            "/api/backtest/run",
            json={
                "strategy": strategy,
                "timeframe": "5m",
                "pairs": ["BTC/USDT"],
                "version_id": candidate_version_id,
            },
        )
        assert response.status_code == 200, response.text
        prepared = env.last_prepared
        assert prepared is not None

        with open(prepared["strategy_file"], "r", encoding="utf-8") as handle:
            assert handle.read() == parent_code
        with open(prepared["config_overlay_path"], "r", encoding="utf-8") as handle:
            assert json.load(handle) == {
                "max_open_trades": 1,
                "nested": {"left": 1, "right": 2},
                "dry_run_wallet": 250,
            }
        print("[PASS] Parameter-only candidate run inherits parent code and merges parameter lineage")


def test_run_without_explicit_version_uses_active_candidate_workspace() -> None:
    with _PatchedEnv() as env, _patched_engine(env, _CapturingFreqtradeEngine):
        strategy = "AcceptedWorkspaceStrategy"
        live_code = "class AcceptedWorkspaceStrategy:\n    origin = 'live'\n"
        baseline_code = "class AcceptedWorkspaceStrategy:\n    origin = 'baseline'\n"
        candidate_code = "class AcceptedWorkspaceStrategy:\n    origin = 'accepted'\n"
        _write_text(os.path.join(env.strategies_dir, f"{strategy}.py"), live_code)
        baseline_version_id = _create_active_version(strategy, code=baseline_code)
        candidate_version_id = mutation_module.mutation_service.create_mutation(
            MutationRequest(
                strategy_name=strategy,
                change_type=ChangeType.CODE_CHANGE,
                summary="Accepted workspace candidate",
                created_by="ai_apply",
                code=candidate_code,
                parameters={"stoploss": -0.09},
                parent_version_id=baseline_version_id,
            )
        ).version_id
        accepted = mutation_module.mutation_service.accept_version(
            candidate_version_id,
            notes="Promote candidate",
        )
        assert accepted.status == "accepted", accepted

        client = _make_client()
        response = client.post(
            "/api/backtest/run",
            json={
                "strategy": strategy,
                "timeframe": "5m",
                "pairs": ["BTC/USDT"],
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        prepared = env.last_prepared
        assert prepared is not None
        assert payload["version_id"] == candidate_version_id

        with open(prepared["strategy_file"], "r", encoding="utf-8") as handle:
            assert handle.read() == candidate_code
        with open(prepared["config_overlay_path"], "r", encoding="utf-8") as handle:
            assert json.load(handle) == {"stoploss": -0.09}
        print("[PASS] Active accepted version is used for runs without an explicit version id")


def test_stream_reconciles_stale_running_run_to_completed() -> None:
    with _PatchedEnv() as env:
        strategy = "RecoveredStrategy"
        run_id = "bt-recovered-stream"
        version_id = _create_active_version(strategy, code="class RecoveredStrategy: pass\n")
        log_path = os.path.join(env.results_dir, strategy, f"{run_id}.backtest.log")
        raw_result_path = os.path.join(env.results_dir, strategy, f"{run_id}.backtest.zip")

        _write_text(log_path, "$ freqtrade backtesting\n\nBacktest finished\n")
        _write_raw_zip(
            raw_result_path,
            {
                "strategy": _make_summary(strategy, profit_pct=7.5, total_trades=8, winrate=0.625),
                "strategy_comparison": {"note": "ok"},
            },
        )
        _write_run_meta(
            env,
            run_id=run_id,
            strategy=strategy,
            status="running",
            version_id=version_id,
            raw_result_path=raw_result_path,
            pid=999999,
        )

        client = _make_client()
        response = client.get(f"/api/backtest/runs/{run_id}/logs/stream")
        assert response.status_code == 200, response.text
        assert "[done] status=completed exit_code=0" in response.text

        stored = persistence_module.PersistenceService().load_backtest_run(run_id)
        assert stored["status"] == "completed"
        assert stored["exit_code"] == 0
        assert os.path.isfile(stored["result_path"])
        assert os.path.isfile(stored["summary_path"])
        print("[PASS] Stream reconciles stale running runs and emits a terminal completion event")


def test_diagnosis_endpoint_states_and_ai_overlay() -> None:
    with _PatchedEnv() as env:
        strategy = "EndpointStrategy"
        version_id = _create_active_version(strategy)
        ready_summary = _make_summary(strategy, trades=[_make_trade(0), _make_trade(1, profit_ratio=-0.02, open_hour=2)])

        _write_run_meta(
            env,
            run_id="bt-ready",
            strategy=strategy,
            status="completed",
            summary_payload=ready_summary,
            version_id=version_id,
            completed=True,
            include_snapshot_fields=False,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-ready.backtest.zip"),
        )
        _write_run_meta(
            env,
            run_id="bt-pending",
            strategy=strategy,
            status="running",
            completed=False,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-pending.backtest.zip"),
            pid=os.getpid(),
            created_at=now_iso(),
        )
        _write_run_meta(
            env,
            run_id="bt-error",
            strategy=strategy,
            status="running",
            error="launch_failed: boom",
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-error.backtest.zip"),
        )
        _write_run_meta(
            env,
            run_id="bt-no-summary",
            strategy=strategy,
            status="completed",
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-no-summary.backtest.zip"),
        )
        _write_run_meta(
            env,
            run_id="bt-no-raw",
            strategy=strategy,
            status="completed",
            completed=True,
            include_snapshot_fields=True,
        )
        _write_run_meta(
            env,
            run_id="bt-broken-summary",
            strategy=strategy,
            status="completed",
            summary_text="{bad-json}",
            completed=True,
            include_snapshot_fields=True,
            raw_result_path=os.path.join(env.results_dir, strategy, "bt-broken-summary.backtest.zip"),
        )

        async def _overlay_ok(**kwargs):
            return {
                "summary": "Overlay summary",
                "priorities": ["Tighten exits"],
                "rationale": ["Drawdown is high"],
                "parameter_suggestions": [{"name": "stoploss", "value": -0.08}],
                "ai_status": "ready",
            }

        async def _overlay_fail(**kwargs):
            raise RuntimeError("overlay down")

        original_overlay = backtest_router.analyze_run_diagnosis_overlay
        client = _make_client()
        try:
            ready = client.get("/api/backtest/runs/bt-ready/diagnosis")
            assert ready.status_code == 200, ready.text
            ready_payload = ready.json()
            assert ready_payload["diagnosis_status"] == "ready"
            assert ready_payload["summary_available"] is True
            assert ready_payload["diagnosis"]["rule_version"] == "freqtrade-run-diagnosis-v1"

            pending = client.get("/api/backtest/runs/bt-pending/diagnosis")
            assert pending.status_code == 200
            assert pending.json()["diagnosis_status"] == "pending_summary"

            errored = client.get("/api/backtest/runs/bt-error/diagnosis")
            assert errored.status_code == 200
            assert errored.json()["diagnosis_status"] == "ingestion_failed"

            no_summary = client.get("/api/backtest/runs/bt-no-summary/diagnosis")
            assert no_summary.status_code == 200
            assert no_summary.json()["diagnosis_status"] == "ingestion_failed"

            no_raw = client.get("/api/backtest/runs/bt-no-raw/diagnosis")
            assert no_raw.status_code == 200
            assert no_raw.json()["diagnosis_status"] == "ingestion_failed"

            broken = client.get("/api/backtest/runs/bt-broken-summary/diagnosis")
            assert broken.status_code == 200
            broken_payload = broken.json()
            assert broken_payload["diagnosis_status"] == "ingestion_failed"
            assert broken_payload["summary_available"] is False
            assert str(broken_payload["error"]).startswith("summary_load_failed:")

            missing = client.get("/api/backtest/runs/does-not-exist/diagnosis")
            assert missing.status_code == 404

            backtest_router.analyze_run_diagnosis_overlay = _overlay_ok
            ai_ready = client.get("/api/backtest/runs/bt-ready/diagnosis", params={"include_ai": True})
            assert ai_ready.status_code == 200
            assert ai_ready.json()["ai"]["ai_status"] == "ready"
            assert ai_ready.json()["ai"]["summary"] == "Overlay summary"

            backtest_router.analyze_run_diagnosis_overlay = _overlay_fail
            ai_unavailable = client.get("/api/backtest/runs/bt-ready/diagnosis", params={"include_ai": True})
            assert ai_unavailable.status_code == 200
            assert ai_unavailable.json()["ai"]["ai_status"] == "unavailable"
        finally:
            backtest_router.analyze_run_diagnosis_overlay = original_overlay

        print("[PASS] Diagnosis endpoint reports readiness states and AI overlay fallback correctly")


if __name__ == "__main__":
    test_freqtrade_cli_resolves_launch_config_path()
    test_run_persists_request_snapshot_and_resolves_active_version()
    test_run_bootstraps_minimal_initial_version()
    test_results_service_summary_states()
    test_diagnosis_rules_and_insufficient_evidence()
    test_proposal_candidate_endpoint_supports_all_sources()
    test_proposal_candidate_endpoint_falls_back_to_active_version_for_historical_run()
    test_deterministic_action_creates_parameter_candidate_without_ai()
    test_ai_chat_apply_parameters_uses_unified_run_scoped_candidate_path()
    test_versions_reject_and_rollback_workflow()
    test_run_materializes_explicit_candidate_workspace()
    test_parameter_candidate_run_inherits_parent_code_and_merges_parameters()
    test_run_without_explicit_version_uses_active_candidate_workspace()
    test_stream_reconciles_stale_running_run_to_completed()
    test_diagnosis_endpoint_states_and_ai_overlay()
    print("\n[SUCCESS] Run-scoped diagnosis tests passed")
