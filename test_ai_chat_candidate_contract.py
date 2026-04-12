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


def test_create_run_scoped_candidate_delegates_to_runtime(monkeypatch):
    captured = {}

    monkeypatch.setattr(ai_apply_service, "_load_run_record", lambda run_id: _run_record())

    async def _fake_create_backtest_run_proposal_candidate(run_id, payload):
        captured["run_id"] = run_id
        captured["payload"] = payload
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

    monkeypatch.setattr(ai_apply_service.runtime, "create_backtest_run_proposal_candidate", _fake_create_backtest_run_proposal_candidate)

    response = asyncio.run(
        ai_apply_service.create_run_scoped_candidate(
            run_id="bt-1",
            strategy_name="TestStrat",
            parameters={"stoploss": -0.12},
            summary="AI chat candidate",
        )
    )

    assert response["candidate_version_id"] == "v-candidate"
    assert captured["run_id"] == "bt-1"
    assert isinstance(captured["payload"], ProposalCandidateRequest)
    assert captured["payload"].source_kind == ProposalSourceKind.AI_CHAT_DRAFT
    assert captured["payload"].candidate_mode == ProposalCandidateMode.PARAMETER_ONLY
    assert captured["payload"].parameters == {"stoploss": -0.12}
    assert captured["payload"].summary == "AI chat candidate"

def test_ai_chat_apply_route_keeps_canonical_payload_and_only_adds_compat_alias(monkeypatch):
    canonical_payload = {
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

    async def _fake_create_run_scoped_candidate(**kwargs):
        return canonical_payload

    monkeypatch.setattr(ai_chat_router, "create_run_scoped_candidate", _fake_create_run_scoped_candidate)

    payload = asyncio.run(
        ai_chat_router.apply_parameters_endpoint(
            ai_chat_router.ApplyParamsRequest(
                run_id="bt-1",
                strategy_name="TestStrat",
                parameters={"stoploss": -0.12},
                summary="AI chat candidate",
            )
        )
    )

    assert list(payload.keys())[: len(canonical_payload)] == list(canonical_payload.keys())
    assert list(payload.keys())[-2:] == ["success", "version_id"]
    assert set(payload.keys()) == set(canonical_payload.keys()) | {"success", "version_id"}
    assert payload["success"] is True
    assert payload["version_id"] == "v-candidate"
    assert payload["candidate_version_id"] == "v-candidate"
    assert payload["source_kind"] == "ai_chat_draft"
    assert payload["source_title"] == "AI Chat Draft"
    assert payload["candidate_ai_mode"] == "parameter_only"
