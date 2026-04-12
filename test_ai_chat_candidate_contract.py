import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.freqtrade import runtime
from app.models.backtest_models import (
    BacktestRunRecord,
    BacktestRunStatus,
    BacktestTriggerSource,
    ProposalCandidateMode,
    ProposalCandidateRequest,
    ProposalSourceKind,
)
from app.services.results import strategy_intelligence_apply_service as apply_service



def _run_record() -> BacktestRunRecord:
    return BacktestRunRecord(
        run_id="bt-1",
        engine="freqtrade",
        strategy="TestStrat",
        version_id="v-linked",
        request_snapshot={"exchange": "binance"},
        request_snapshot_schema_version=1,
        trigger_source=BacktestTriggerSource.MANUAL,
        created_at="2026-04-11T00:00:00+00:00",
        updated_at="2026-04-11T00:00:00+00:00",
        completed_at="2026-04-11T00:10:00+00:00",
        status=BacktestRunStatus.COMPLETED,
        command="freqtrade backtesting",
    )


def _patch_ready_summary(monkeypatch):
    def _load_summary(run):
        return {"state": "ready", "summary": {"TestStrat": {}}}

    def _summary_block(summary, strategy):
        return {"trades": [], "results_per_pair": []}

    def _metrics(summary, strategy):
        return {"profit_total_pct": 1.0}

    for module in (runtime,):
        monkeypatch.setattr(module.results_svc, "load_run_summary_state", _load_summary)
        monkeypatch.setattr(module.results_svc, "extract_run_summary_block", _summary_block)
        monkeypatch.setattr(module.results_svc, "_normalize_summary_metrics", _metrics)


def test_backtest_proposal_candidate_requires_ready_summary(monkeypatch):
    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: _run_record())
    monkeypatch.setattr(runtime.results_svc, "load_run_summary_state", lambda run: {"state": "missing", "summary": None, "error": None})

    payload = ProposalCandidateRequest(
        source_kind=ProposalSourceKind.AI_CHAT_DRAFT,
        candidate_mode=ProposalCandidateMode.PARAMETER_ONLY,
        parameters={"stoploss": -0.12},
        summary="AI chat candidate",
    )

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(runtime.create_backtest_run_proposal_candidate("bt-1", payload))

    assert excinfo.value.status_code == 400
    assert "Summary is not ready" in excinfo.value.detail


def test_backtest_proposal_candidate_keeps_run_version_linkage(monkeypatch):
    captured = {}
    linked_version = SimpleNamespace(version_id="v-linked")

    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: _run_record())
    monkeypatch.setattr(runtime.results_svc, "load_run_summary_state", lambda run: {"state": "ready", "summary": {"TestStrat": {}}})
    monkeypatch.setattr(runtime.results_svc, "extract_run_summary_block", lambda summary, strategy: {"trades": [], "results_per_pair": []})
    monkeypatch.setattr(runtime.results_svc, "_normalize_summary_metrics", lambda summary, strategy: {"profit_total_pct": 1.0})
    monkeypatch.setattr(runtime, "_resolve_linked_version_for_run", lambda run: (linked_version, "run"))
    monkeypatch.setattr(runtime.diagnosis_service, "diagnose_run", lambda **kwargs: {"primary_flags": []})

    async def _fake_create_candidate(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            success=True,
            version_id="v-candidate",
            candidate_change_type="parameter_change",
            candidate_status="candidate",
            source_title="AI Chat Draft",
            ai_mode="parameter_only",
            message="Candidate version created.",
        )

    monkeypatch.setattr(runtime, "create_proposal_candidate_from_diagnosis", _fake_create_candidate)

    payload = ProposalCandidateRequest(
        source_kind=ProposalSourceKind.AI_CHAT_DRAFT,
        candidate_mode=ProposalCandidateMode.PARAMETER_ONLY,
        parameters={"stoploss": -0.12},
        summary="AI chat candidate",
    )

    response = asyncio.run(runtime.create_backtest_run_proposal_candidate("bt-1", payload))

    assert response["baseline_run_id"] == "bt-1"
    assert response["baseline_version_id"] == "v-linked"
    assert response["baseline_run_version_id"] == "v-linked"
    assert response["baseline_version_source"] == "run"
    assert response["version_id"] == "v-candidate"
    assert response["candidate_version_id"] == "v-candidate"
    assert response["change_type"] == "parameter_change"
    assert response["candidate_change_type"] == "parameter_change"
    assert response["status"] == "candidate"
    assert response["candidate_status"] == "candidate"
    assert response["source_kind"] == "ai_chat_draft"
    assert response["source_title"] == "AI Chat Draft"
    assert response["ai_mode"] == "parameter_only"
    assert response["candidate_ai_mode"] == "parameter_only"

    assert captured["run_id"] == "bt-1"
    assert captured["linked_version"].version_id == "v-linked"
    assert captured["source_kind"] == "ai_chat_draft"
    assert captured["candidate_mode"] == "parameter_only"
    assert captured["candidate_parameters"] == {"stoploss": -0.12}
    assert captured["candidate_code"] is None
