import asyncio
import importlib.util
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.optimizer_models import ChangeType, MutationResult, VersionStatus
from app.services import ai_chat as ai_chat_services
from app.services.results import strategy_intelligence_apply_service as apply_service


client = TestClient(app)


def _version(change_type: ChangeType) -> SimpleNamespace:
    return SimpleNamespace(change_type=change_type, status=VersionStatus.CANDIDATE)


def test_ai_chat_apply_routes_are_removed():
    for path, payload in (
        (
            "/api/ai/chat/apply-code",
            {
                "run_id": "bt-1",
                "strategy_name": "TestStrat",
                "code": "class TestStrat:\n    pass\n",
                "summary": "legacy wrapper",
            },
        ),
        (
            "/api/ai/chat/apply-parameters",
            {
                "run_id": "bt-1",
                "strategy_name": "TestStrat",
                "parameters": {"stoploss": -0.12},
                "summary": "legacy wrapper",
            },
        ),
    ):
        response = client.post(path, json=payload)
        assert response.status_code == 404


def test_legacy_apply_service_is_not_exported_or_importable():
    assert importlib.util.find_spec("app.services.ai_chat.apply_code_service") is None
    assert "ApplyResult" not in ai_chat_services.__all__
    assert "apply_code_patch" not in ai_chat_services.__all__
    assert "apply_parameters" not in ai_chat_services.__all__

    for name in ("ApplyResult", "apply_code_patch", "apply_parameters"):
        with pytest.raises(AttributeError):
            getattr(ai_chat_services, name)


def test_ai_chat_draft_without_summary_uses_canonical_run_summary(monkeypatch):
    captured = {}

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(version_id="v-chat-params", status="created", message="created")

    monkeypatch.setattr(apply_service.mutation_service, "create_mutation", _create_mutation)
    monkeypatch.setattr(
        apply_service.mutation_service,
        "get_version_by_id",
        lambda version_id: _version(ChangeType.PARAMETER_CHANGE),
    )

    result = asyncio.run(
        apply_service.create_proposal_candidate_from_diagnosis(
            strategy_name="TestStrat",
            run_id="bt-4",
            linked_version=SimpleNamespace(version_id="v-linked"),
            request_snapshot={},
            summary_metrics={},
            diagnosis={},
            ai_payload={},
            source_kind="ai_chat_draft",
            source_index=0,
            candidate_mode="parameter_only",
            candidate_parameters={"stoploss": -0.11},
            candidate_summary=None,
        )
    )

    assert result.success
    request = captured["request"]
    assert request.summary == "AI chat candidate from run bt-4"
    assert request.source_ref == "backtest_run:bt-4"
    assert request.source_kind == "ai_chat_draft"
    assert request.source_context == {
        "run_id": "bt-4",
        "source_index": 0,
        "title": "AI Chat Draft",
        "candidate_mode": "parameter_only",
    }


def test_ai_chat_draft_keeps_chat_summary_supplemental(monkeypatch):
    captured = {}

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(version_id="v-chat-code", status="created", message="created")

    monkeypatch.setattr(apply_service.mutation_service, "create_mutation", _create_mutation)
    monkeypatch.setattr(
        apply_service.mutation_service,
        "get_version_by_id",
        lambda version_id: _version(ChangeType.CODE_CHANGE),
    )

    result = asyncio.run(
        apply_service.create_proposal_candidate_from_diagnosis(
            strategy_name="TestStrat",
            run_id="bt-5",
            linked_version=SimpleNamespace(version_id="v-linked"),
            request_snapshot={},
            summary_metrics={},
            diagnosis={},
            ai_payload={},
            source_kind="ai_chat_draft",
            source_index=0,
            candidate_mode="code_patch",
            candidate_code="class TestStrat:\n    pass\n",
            candidate_summary="Tighten entries after pullback",
        )
    )

    assert result.success
    request = captured["request"]
    assert request.summary == "AI chat candidate from run bt-5"
    assert request.source_context == {
        "run_id": "bt-5",
        "candidate_mode": "code_patch",
        "chat_summary": "Tighten entries after pullback",
    }
    assert request.source_ref == "backtest_run:bt-5"
    assert request.source_kind == "ai_chat_draft"