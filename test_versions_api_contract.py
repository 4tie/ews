from fastapi.testclient import TestClient

from app.main import app
from app.models.backtest_models import BacktestRunRecord, BacktestRunStatus, BacktestTriggerSource
from app.models.optimizer_models import ChangeType, StrategyVersion, VersionStatus
from app.routers import versions as versions_router


client = TestClient(app)


def _version(
    version_id: str,
    *,
    status: VersionStatus,
    parent_version_id: str | None = None,
    promoted_from_version_id: str | None = None,
) -> StrategyVersion:
    return StrategyVersion(
        version_id=version_id,
        parent_version_id=parent_version_id,
        strategy_name="TestStrat",
        created_at="2026-01-01T00:00:00",
        created_by="tester",
        change_type=ChangeType.CODE_CHANGE,
        summary=f"summary for {version_id}",
        source_context={"title": f"title for {version_id}"},
        status=status,
        code_snapshot="class TestStrat:\n    pass\n",
        parameters_snapshot={"stoploss": -0.2},
        promoted_from_version_id=promoted_from_version_id,
    )


def _run(run_id: str, version_id: str, status: BacktestRunStatus = BacktestRunStatus.COMPLETED) -> BacktestRunRecord:
    return BacktestRunRecord(
        run_id=run_id,
        strategy="TestStrat",
        version_id=version_id,
        request_snapshot={
            "strategy": "TestStrat",
            "timeframe": "5m",
            "pairs": ["BTC/USDT", "ETH/USDT"],
            "exchange": "binance",
        },
        request_snapshot_schema_version=1,
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:05:00",
        completed_at="2026-01-01T00:10:00",
        status=status,
        command="freqtrade backtesting",
        raw_result_path=f"/tmp/{run_id}.zip",
        summary_path=f"/tmp/{run_id}.summary.json",
    )


def test_versions_page_route_renders_shell():
    response = client.get("/versions")

    assert response.status_code == 200
    assert 'id="versions-page"' in response.text
    assert "Versions List" in response.text
    assert "Lineage View" in response.text


def test_version_detail_route_returns_enriched_lifecycle_payload(monkeypatch):
    active = _version("v-live", status=VersionStatus.ACTIVE)
    candidate = _version(
        "v-candidate",
        status=VersionStatus.CANDIDATE,
        parent_version_id="v-live",
    )
    versions = {
        active.version_id: active,
        candidate.version_id: candidate,
    }
    runs = [
        _run("bt-live", "v-live"),
        _run("bt-candidate", "v-candidate"),
    ]

    class MutationStub:
        def get_version_by_id(self, version_id):
            return versions.get(version_id)

        def get_active_version(self, strategy_name):
            assert strategy_name == "TestStrat"
            return active

        def resolve_effective_artifacts(self, version_id):
            if version_id == "v-candidate":
                return {
                    "version_id": "v-candidate",
                    "strategy_name": "TestStrat",
                    "lineage": ["v-candidate", "v-live"],
                    "code_snapshot": "class TestStrat:\n    candidate = True\n",
                    "parameters_snapshot": {"stoploss": -0.1, "max_open_trades": 2},
                }
            return {
                "version_id": "v-live",
                "strategy_name": "TestStrat",
                "lineage": ["v-live"],
                "code_snapshot": "class TestStrat:\n    live = True\n",
                "parameters_snapshot": {"stoploss": -0.2, "max_open_trades": 1},
            }

        def build_version_compare_payload(self, left_version_id, right_version_id):
            assert left_version_id == "v-live"
            assert right_version_id == "v-candidate"
            return {
                "versions": {
                    "baseline_version_id": "v-live",
                    "candidate_version_id": "v-candidate",
                    "candidate_parent_version_id": "v-live",
                    "baseline_version_source": "run",
                },
                "version_diff": {
                    "parameter_diff_rows": [
                        {"path": "stoploss", "status": "changed", "before": -0.2, "after": -0.1},
                    ],
                    "code_diff": {
                        "changed": True,
                        "summary": "Persisted code snapshot changed.",
                        "preview_blocks": [
                            {
                                "header": "@@ -1 +1 @@",
                                "lines": [
                                    {"kind": "removed", "text": "    live = True"},
                                    {"kind": "added", "text": "    candidate = True"},
                                ],
                            }
                        ],
                        "preview_truncated": False,
                    },
                },
            }

    summaries = {
        "bt-live": {
            "run_id": "bt-live",
            "status": "completed",
            "trigger_source": "manual",
            "request_snapshot": {"strategy": "TestStrat", "timeframe": "5m", "pairs": ["BTC/USDT"]},
            "summary_metrics": {
                "profit_total_pct": 1.0,
                "total_trades": 12,
                "win_rate": 52.0,
                "max_drawdown_pct": 10.0,
            },
        },
        "bt-candidate": {
            "run_id": "bt-candidate",
            "status": "completed",
            "trigger_source": "manual",
            "request_snapshot": {"strategy": "TestStrat", "timeframe": "5m", "pairs": ["BTC/USDT"]},
            "summary_metrics": {
                "profit_total_pct": 2.5,
                "total_trades": 16,
                "win_rate": 56.0,
                "max_drawdown_pct": 8.0,
            },
        },
    }

    monkeypatch.setattr(versions_router, "mutation_service", MutationStub())
    monkeypatch.setattr(versions_router, "_list_freqtrade_runs", lambda strategy=None: runs)
    monkeypatch.setattr(
        versions_router.results_svc,
        "summarize_backtest_run",
        lambda run: summaries[run.run_id],
    )
    monkeypatch.setattr(
        versions_router.results_svc,
        "load_run_summary_state",
        lambda run: {"state": "ready", "summary": {}, "error": None},
    )
    monkeypatch.setattr(
        versions_router.results_svc,
        "compare_backtest_runs",
        lambda left_run, right_run: {
            "left": {"run_id": left_run.run_id},
            "right": {"run_id": right_run.run_id},
            "metrics": [
                {
                    "key": "profit_total_pct",
                    "label": "Total Profit %",
                    "format": "pct",
                    "left": 1.0,
                    "right": 2.5,
                    "delta": 1.5,
                    "classification": "improved",
                    "reason": "Higher profit is better.",
                }
            ],
        },
    )

    response = client.get("/api/versions/TestStrat/v-candidate/detail")

    assert response.status_code == 200
    payload = response.json()

    assert payload["strategy_name"] == "TestStrat"
    assert payload["active_version_id"] == "v-live"
    assert payload["compare_version_id"] == "v-live"
    assert payload["lineage_version_ids"] == ["v-candidate", "v-live"]
    assert payload["resolved_code_snapshot"] == "class TestStrat:\n    candidate = True\n"
    assert payload["resolved_parameters_snapshot"] == {"stoploss": -0.1, "max_open_trades": 2}
    assert payload["latest_run"]["run_id"] == "bt-candidate"
    assert payload["metrics"]["profit_total_pct"] == 2.5
    assert payload["linked_runs"][0]["run_id"] == "bt-candidate"
    assert payload["comparison"]["versions"]["baseline_version_id"] == "v-live"
    assert payload["comparison"]["version_diff"]["code_diff"]["changed"] is True
    assert payload["run_comparison"]["metrics"][0]["delta"] == 1.5
