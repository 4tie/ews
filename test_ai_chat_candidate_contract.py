import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.freqtrade import runtime
from app.main import app
from app.models.backtest_models import (
    BacktestRunRecord,
    BacktestRunStatus,
    BacktestTriggerSource,
    ProposalCandidateMode,
    ProposalCandidateRequest,
    ProposalSourceKind,
)
from app.routers import ai_chat as ai_chat_router
from app.services.ai_chat import apply_code_service as ai_apply_service
from app.services.results import strategy_intelligence_apply_service as apply_service


client = TestClient(app)


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

    for module in (runtime, ai_apply_service):
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
    assert response["candidate_version_id"] == "v-candidate"
    assert response["candidate_status"] == "candidate"
    assert response["source_kind"] == "ai_chat_draft"
    assert response["source_title"] == "AI Chat Draft"
    assert response["candidate_ai_mode"] == "parameter_only"

    assert captured["run_id"] == "bt-1"
    assert captured["linked_version"].version_id == "v-linked"
    assert captured["source_kind"] == "ai_chat_draft"
    assert captured["candidate_mode"] == "parameter_only"
    assert captured["candidate_parameters"] == {"stoploss": -0.12}
    assert captured["candidate_code"] is None


def test_backtest_candidate_wrappers_use_stage_backtest_candidate(monkeypatch):
    linked_version = SimpleNamespace(version_id="v-linked")
    calls = []

    _patch_ready_summary(monkeypatch)
    monkeypatch.setattr(runtime, "_load_run_record", lambda run_id: _run_record())
    monkeypatch.setattr(ai_apply_service, "_load_run_record", lambda run_id: _run_record())
    monkeypatch.setattr(runtime, "_resolve_linked_version_for_run", lambda run: (linked_version, "run"))
    monkeypatch.setattr(ai_apply_service, "_resolve_linked_version_for_run", lambda run: (linked_version, "run"))
    monkeypatch.setattr(runtime.diagnosis_service, "diagnose_run", lambda **kwargs: {"primary_flags": []})
    monkeypatch.setattr(ai_apply_service.diagnosis_service, "diagnose_run", lambda **kwargs: {"primary_flags": []})

    def _forbidden_create_mutation(*args, **kwargs):
        raise AssertionError("Backtest wrappers must route through stage_backtest_candidate().")

    monkeypatch.setattr(runtime.mutation_service, "create_mutation", _forbidden_create_mutation)
    monkeypatch.setattr(ai_apply_service.mutation_service, "create_mutation", _forbidden_create_mutation)

    def _fake_stage_backtest_candidate(**kwargs):
        calls.append(kwargs)
        return apply_service.ProposalCandidateResult(
            success=True,
            message="Candidate version created.",
            version_id=f"v-candidate-{len(calls)}",
            candidate_change_type="parameter_change",
            candidate_status="candidate",
            source_title=kwargs.get("source_title") or "AI Chat Draft",
            ai_mode=kwargs.get("ai_mode") or kwargs.get("candidate_mode"),
        )

    monkeypatch.setattr(apply_service, "stage_backtest_candidate", _fake_stage_backtest_candidate)
    monkeypatch.setattr(runtime, "create_proposal_candidate_from_diagnosis", apply_service.create_proposal_candidate_from_diagnosis)

    runtime_payload = ProposalCandidateRequest(
        source_kind=ProposalSourceKind.AI_CHAT_DRAFT,
        candidate_mode=ProposalCandidateMode.PARAMETER_ONLY,
        parameters={"stoploss": -0.12},
        summary="AI chat candidate",
    )
    runtime_response = asyncio.run(runtime.create_backtest_run_proposal_candidate("bt-1", runtime_payload))
    scoped_response = asyncio.run(
        ai_apply_service.create_run_scoped_candidate(
            run_id="bt-1",
            strategy_name="TestStrat",
            parameters={"stoploss": -0.12},
            summary="AI chat candidate",
        )
    )

    assert len(calls) == 2
    assert [call["source_kind"] for call in calls] == ["ai_chat_draft", "ai_chat_draft"]
    assert [call["candidate_mode"] for call in calls] == ["parameter_only", "parameter_only"]
    assert all(call["strategy_name"] == "TestStrat" for call in calls)

    assert runtime_response["candidate_version_id"] == "v-candidate-1"
    assert runtime_response["source_title"] == "AI Chat Draft"
    assert runtime_response["candidate_ai_mode"] == "parameter_only"

    assert scoped_response["candidate_version_id"] == "v-candidate-2"
    assert scoped_response["source_kind"] == "ai_chat_draft"
    assert scoped_response["source_index"] == 0
    assert scoped_response["source_title"] == "AI Chat Draft"
    assert scoped_response["candidate_ai_mode"] == "parameter_only"


def test_ai_chat_apply_route_keeps_legacy_version_id_alias(monkeypatch):
    async def _fake_create_run_scoped_candidate(**kwargs):
        return {
            "baseline_run_id": "bt-1",
            "baseline_version_id": "v-linked",
            "baseline_run_version_id": "v-linked",
            "baseline_version_source": "run",
            "candidate_version_id": "v-candidate",
            "candidate_change_type": "parameter_change",
            "candidate_status": "candidate",
            "source_kind": "ai_chat_draft",
            "source_index": 0,
            "source_title": "AI Chat Draft",
            "candidate_ai_mode": "parameter_only",
            "message": "Candidate version created.",
        }

    monkeypatch.setattr(ai_chat_router, "create_run_scoped_candidate", _fake_create_run_scoped_candidate)

    response = client.post(
        "/api/ai/chat/apply-parameters",
        json={
            "run_id": "bt-1",
            "strategy_name": "TestStrat",
            "parameters": {"stoploss": -0.12},
            "summary": "AI chat candidate",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["version_id"] == "v-candidate"
    assert payload["candidate_version_id"] == "v-candidate"
    assert payload["source_kind"] == "ai_chat_draft"
    assert payload["source_title"] == "AI Chat Draft"
    assert payload["candidate_ai_mode"] == "parameter_only"
