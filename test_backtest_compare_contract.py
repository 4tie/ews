import json

import pytest

from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource
from app.models.optimizer_models import ChangeType, StrategyVersion, VersionStatus
from app.services import results_service as results_module


def _run_record(run_id: str, summary_path: str | None, *, version_id: str | None = None) -> BacktestRunRecord:
    return BacktestRunRecord(
        run_id=run_id,
        strategy="TestStrat",
        version_id=version_id,
        request_snapshot={"pairs": ["BTC/USDT", "ETH/USDT"]},
        request_snapshot_schema_version=1,
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
        completed_at="2026-01-01T00:05:00",
        status=BacktestRunStatus.COMPLETED,
        command="freqtrade backtesting",
        raw_result_path=f"/tmp/{run_id}.zip",
        summary_path=summary_path,
    )


def _pair_row(pair: str, profit_total_pct: float, trades: int, wins: int) -> dict:
    return {
        "key": pair,
        "profit_total_pct": profit_total_pct,
        "profit_total": profit_total_pct / 100,
        "profit_total_abs": profit_total_pct * 10,
        "trades": trades,
        "wins": wins,
        "winrate": wins / trades if trades else 0,
        "max_drawdown_account": abs(min(profit_total_pct, 0)) / 100,
    }


def _summary_payload(
    profit_total_pct: float,
    profit_total_abs: float,
    trades: int,
    wins: int,
    *,
    pair_rows: list[dict],
) -> dict:
    return {
        "TestStrat": {
            "strategy_name": "TestStrat",
            "results_per_pair": [
                *pair_rows,
                {
                    "key": "TOTAL",
                    "profit_total_pct": profit_total_pct,
                    "profit_total_abs": profit_total_abs,
                    "trades": trades,
                    "wins": wins,
                    "winrate": wins / trades if trades else 0,
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


def _version(
    version_id: str,
    *,
    parent_version_id: str | None = None,
    change_type: ChangeType = ChangeType.CODE_CHANGE,
    summary: str = "candidate summary",
    source_kind: str | None = None,
    source_context: dict | None = None,
    diff_ref: str | None = None,
) -> StrategyVersion:
    return StrategyVersion(
        version_id=version_id,
        parent_version_id=parent_version_id,
        strategy_name="TestStrat",
        created_at="2026-01-01T00:00:00",
        created_by="tester",
        change_type=change_type,
        summary=summary,
        diff_ref=diff_ref,
        source_kind=source_kind,
        source_context=source_context or {},
        status=VersionStatus.CANDIDATE,
    )


def test_compare_backtest_runs_requires_persisted_summary(monkeypatch, tmp_path):
    strategy_dir = tmp_path / "TestStrat"
    monkeypatch.setattr(results_module, "strategy_results_dir", lambda strategy, user_data_path=None: str(strategy_dir))
    service = results_module.ResultsService()

    left_run = _run_record("bt-left", None)
    right_run = _run_record("bt-right", None)

    with pytest.raises(ValueError, match="persisted summary"):
        service.compare_backtest_runs(left_run, right_run)


def test_compare_backtest_runs_adds_version_diff_pair_deltas_and_diagnosis_delta(monkeypatch, tmp_path):
    strategy_dir = tmp_path / "TestStrat"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(results_module, "strategy_results_dir", lambda strategy, user_data_path=None: str(strategy_dir))
    service = results_module.ResultsService()

    left_summary_path = strategy_dir / "bt-left.summary.json"
    right_summary_path = strategy_dir / "bt-right.summary.json"
    left_summary_path.write_text(
        json.dumps(
            _summary_payload(
                1.5,
                100.0,
                10,
                6,
                pair_rows=[
                    _pair_row("BTC/USDT", 1.0, 6, 4),
                    _pair_row("ETH/USDT", -4.0, 4, 2),
                ],
            )
        ),
        encoding="utf-8",
    )
    right_summary_path.write_text(
        json.dumps(
            _summary_payload(
                3.0,
                130.0,
                14,
                8,
                pair_rows=[
                    _pair_row("BTC/USDT", 3.5, 8, 5),
                    _pair_row("ETH/USDT", -1.0, 5, 2),
                    _pair_row("SOL/USDT", 0.8, 1, 1),
                ],
            )
        ),
        encoding="utf-8",
    )

    left_run = _run_record("bt-left", str(left_summary_path), version_id="v-baseline")
    right_run = _run_record("bt-right", str(right_summary_path), version_id="v-candidate")

    baseline_version = _version("v-baseline", summary="Baseline")
    candidate_version = _version(
        "v-candidate",
        parent_version_id="v-baseline",
        change_type=ChangeType.CODE_CHANGE,
        summary="Candidate from diagnosis",
        source_kind="parameter_hint",
        source_context={
            "title": "Tighten Stoploss",
            "candidate_mode": "parameter_only",
            "source_index": 0,
            "rule": "low_sample_size",
        },
        diff_ref="diff://candidate",
    )
    versions = {
        baseline_version.version_id: baseline_version,
        candidate_version.version_id: candidate_version,
    }
    artifacts = {
        "v-baseline": {
            "version_id": "v-baseline",
            "strategy_name": "TestStrat",
            "lineage": ["v-baseline"],
            "code_snapshot": "class TestStrat:\n    threshold = 1\n",
            "parameters_snapshot": {"entry": {"alpha": 1, "beta": 2}, "stoploss": -0.2},
        },
        "v-candidate": {
            "version_id": "v-candidate",
            "strategy_name": "TestStrat",
            "lineage": ["v-candidate", "v-baseline"],
            "code_snapshot": "class TestStrat:\n    threshold = 2\n    enabled = True\n",
            "parameters_snapshot": {"entry": {"alpha": 2, "beta": 2}, "stoploss": -0.1},
        },
    }

    monkeypatch.setattr(results_module.mutation_service, "get_version_by_id", lambda version_id: versions.get(version_id))
    monkeypatch.setattr(results_module.mutation_service, "resolve_effective_artifacts", lambda version_id: artifacts[version_id])

    def _diagnose_run(**kwargs):
        run = kwargs["run_record"]
        if run.run_id == "bt-left":
            return {
                "facts": {
                    "worst_pair": "ETH/USDT",
                    "worst_pair_profit_pct": -4.0,
                    "worst_pair_trades": 4,
                },
                "ranked_issues": [
                    {"rule": "low_sample_size"},
                    {"rule": "pair_dragger"},
                ],
            }
        return {
            "facts": {
                "worst_pair": "ETH/USDT",
                "worst_pair_profit_pct": -1.0,
                "worst_pair_trades": 5,
            },
            "ranked_issues": [
                {"rule": "high_drawdown"},
            ],
        }

    monkeypatch.setattr(results_module.diagnosis_service, "diagnose_run", _diagnose_run)

    comparison = service.compare_backtest_runs(left_run, right_run)

    assert set(comparison.keys()) == {"left", "right", "metrics", "versions", "version_diff", "pairs", "diagnosis_delta"}

    profit_row = next(row for row in comparison["metrics"] if row["key"] == "profit_total_pct")
    trades_row = next(row for row in comparison["metrics"] if row["key"] == "total_trades")

    assert comparison["left"]["summary_available"] is True
    assert comparison["right"]["summary_available"] is True
    assert profit_row["delta"] == 1.5
    assert profit_row["classification"] == "improved"
    assert trades_row["classification"] == "improved"

    assert comparison["versions"] == {
        "baseline_version_id": "v-baseline",
        "candidate_version_id": "v-candidate",
        "candidate_parent_version_id": "v-baseline",
        "baseline_version_source": "run",
    }
    assert comparison["version_diff"]["source_kind"] == "parameter_hint"
    assert comparison["version_diff"]["source_title"] == "Tighten Stoploss"
    assert comparison["version_diff"]["candidate_mode"] == "parameter_only"
    assert comparison["version_diff"]["change_type"] == "code_change"
    assert comparison["version_diff"]["summary"] == "Candidate from diagnosis"
    assert [row["path"] for row in comparison["version_diff"]["parameter_diff_rows"]] == ["entry.alpha", "stoploss"]
    assert comparison["version_diff"]["code_diff"]["changed"] is True
    assert comparison["version_diff"]["code_diff"]["diff_ref"] == "diff://candidate"

    pair_rows = comparison["pairs"]["rows"]
    assert [row["pair"] for row in pair_rows] == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    assert comparison["pairs"]["top_improvements"][0]["pair"] == "ETH/USDT"
    assert comparison["pairs"]["pair_dragger_evidence"]["status"] == "resolved"
    assert comparison["pairs"]["worst_pair_change"]["before"]["pair"] == "ETH/USDT"
    assert comparison["pairs"]["worst_pair_change"]["after"]["profit_total_pct"] == -1.0

    assert comparison["diagnosis_delta"] == {
        "resolved_rules": ["low_sample_size", "pair_dragger"],
        "new_rules": ["high_drawdown"],
        "persistent_rules": [],
        "worst_pair_before": "ETH/USDT",
        "worst_pair_after": "ETH/USDT",
    }


def test_compare_backtest_runs_falls_back_to_candidate_parent_only_when_run_version_is_unavailable(monkeypatch, tmp_path):
    strategy_dir = tmp_path / "TestStrat"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(results_module, "strategy_results_dir", lambda strategy, user_data_path=None: str(strategy_dir))
    service = results_module.ResultsService()

    left_summary_path = strategy_dir / "bt-left.summary.json"
    right_summary_path = strategy_dir / "bt-right.summary.json"
    payload = _summary_payload(1.0, 10.0, 5, 3, pair_rows=[_pair_row("BTC/USDT", 1.0, 5, 3)])
    left_summary_path.write_text(json.dumps(payload), encoding="utf-8")
    right_summary_path.write_text(json.dumps(payload), encoding="utf-8")

    left_run = _run_record("bt-left", str(left_summary_path), version_id="v-missing")
    right_run = _run_record("bt-right", str(right_summary_path), version_id="v-candidate")

    baseline_version = _version("v-baseline", summary="Baseline")
    candidate_version = _version(
        "v-candidate",
        parent_version_id="v-baseline",
        source_kind="parameter_hint",
        source_context={"title": "Fallback Candidate", "candidate_mode": "parameter_only"},
    )
    versions = {
        baseline_version.version_id: baseline_version,
        candidate_version.version_id: candidate_version,
    }
    artifacts = {
        "v-baseline": {
            "version_id": "v-baseline",
            "strategy_name": "TestStrat",
            "lineage": ["v-baseline"],
            "code_snapshot": "class TestStrat:\n    pass\n",
            "parameters_snapshot": {"stoploss": -0.2},
        },
        "v-candidate": {
            "version_id": "v-candidate",
            "strategy_name": "TestStrat",
            "lineage": ["v-candidate", "v-baseline"],
            "code_snapshot": "class TestStrat:\n    pass\n",
            "parameters_snapshot": {"stoploss": -0.1},
        },
    }

    monkeypatch.setattr(results_module.mutation_service, "get_version_by_id", lambda version_id: versions.get(version_id))
    monkeypatch.setattr(results_module.mutation_service, "resolve_effective_artifacts", lambda version_id: artifacts[version_id])
    monkeypatch.setattr(results_module.diagnosis_service, "diagnose_run", lambda **kwargs: {"facts": {}, "ranked_issues": []})

    comparison = service.compare_backtest_runs(left_run, right_run)

    assert set(comparison.keys()) == {"left", "right", "metrics", "versions", "version_diff", "pairs", "diagnosis_delta"}
    assert comparison["versions"]["baseline_version_id"] == "v-baseline"
    assert comparison["versions"]["baseline_version_source"] == "candidate_parent"
