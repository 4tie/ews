import asyncio
from types import SimpleNamespace

from app.models.optimizer_models import ChangeType, MutationResult, StrategyVersion, VersionStatus
from app.services.results import strategy_intelligence_apply_service as apply_service


def _version(version_id: str, change_type: ChangeType) -> StrategyVersion:
    return StrategyVersion(
        version_id=version_id,
        parent_version_id="v-parent",
        strategy_name="TestStrat",
        created_at="2026-01-01T00:00:00",
        created_by="tester",
        change_type=change_type,
        summary="candidate",
        status=VersionStatus.CANDIDATE,
    )


def test_deterministic_action_creates_parameter_candidate(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        apply_service.mutation_service,
        "resolve_effective_artifacts",
        lambda version_id: {
            "strategy_name": "TestStrat",
            "code_snapshot": "class TestStrat:\n    pass\n",
            "parameters_snapshot": {
                "stoploss": -0.2,
                "trailing_stop": False,
                "trailing_stop_positive": 0.02,
            },
        },
    )

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(
            version_id="v-candidate",
            status="created",
            message="created",
        )

    monkeypatch.setattr(apply_service.mutation_service, "create_mutation", _create_mutation)
    monkeypatch.setattr(
        apply_service.mutation_service,
        "get_version_by_id",
        lambda version_id: _version(version_id, ChangeType.PARAMETER_CHANGE),
    )

    result = asyncio.run(
        apply_service.create_proposal_candidate_from_diagnosis(
            strategy_name="TestStrat",
            run_id="bt-1",
            linked_version=SimpleNamespace(version_id="v-linked"),
            request_snapshot={},
            summary_metrics={},
            diagnosis={
                "proposal_actions": [
                    {"action_type": "tighten_stoploss", "label": "Tighten Stoploss"}
                ]
            },
            ai_payload={},
            source_kind="deterministic_action",
            source_index=0,
            candidate_mode="auto",
        )
    )

    assert result.success is True
    assert result.source_title == "Tighten Stoploss"
    assert result.ai_mode is None
    request = captured["request"]
    assert request.parent_version_id == "v-linked"
    assert request.parameters["stoploss"] == -0.15
    assert request.parameters["trailing_stop"] is True
    assert request.parameters["trailing_stop_positive"] == 0.01


def test_ranked_issue_maps_to_review_exit_timing(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        apply_service.mutation_service,
        "resolve_effective_artifacts",
        lambda version_id: {
            "strategy_name": "TestStrat",
            "code_snapshot": "class TestStrat:\n    pass\n",
            "parameters_snapshot": {
                "minimal_roi": {"0": 0.05, "60": 0.02},
                "trailing_stop_positive": 0.02,
            },
        },
    )

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(
            version_id="v-review",
            status="created",
            message="created",
        )

    monkeypatch.setattr(apply_service.mutation_service, "create_mutation", _create_mutation)
    monkeypatch.setattr(
        apply_service.mutation_service,
        "get_version_by_id",
        lambda version_id: _version(version_id, ChangeType.PARAMETER_CHANGE),
    )

    result = asyncio.run(
        apply_service.create_proposal_candidate_from_diagnosis(
            strategy_name="TestStrat",
            run_id="bt-2",
            linked_version=SimpleNamespace(version_id="v-linked"),
            request_snapshot={},
            summary_metrics={},
            diagnosis={
                "ranked_issues": [{"rule": "high_drawdown", "message": "High drawdown"}],
                "proposal_actions": [
                    {
                        "action_type": "review_exit_timing",
                        "label": "Review Exit Timing",
                        "matched_rules": ["high_drawdown"],
                    }
                ],
            },
            ai_payload={},
            source_kind="ranked_issue",
            source_index=0,
            candidate_mode="auto",
        )
    )

    assert result.success is True
    assert result.source_title == "Review Exit Timing"
    assert result.ai_mode is None
    request = captured["request"]
    assert request.parameters["minimal_roi"] == {"0": 0.05, "30": 0.02}
    assert request.parameters["trailing_stop_positive"] == 0.014


def test_ai_parameter_suggestion_returns_source_metadata(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        apply_service.mutation_service,
        "resolve_effective_artifacts",
        lambda version_id: {
            "strategy_name": "TestStrat",
            "code_snapshot": None,
            "parameters_snapshot": {"stoploss": -0.2},
        },
    )
    monkeypatch.setattr(apply_service, "load_live_strategy_code", lambda strategy_name: None)

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(
            version_id="v-ai-parameter",
            status="created",
            message="created",
        )

    async def _fake_run_ai_loop(**kwargs):
        return SimpleNamespace(
            success=True,
            final_parameters={"stoploss": -0.12},
            final_code=None,
            error=None,
        )

    monkeypatch.setattr(apply_service.mutation_service, "create_mutation", _create_mutation)
    monkeypatch.setattr(
        apply_service.mutation_service,
        "get_version_by_id",
        lambda version_id: _version(version_id, ChangeType.PARAMETER_CHANGE),
    )
    monkeypatch.setattr(apply_service, "run_ai_loop", _fake_run_ai_loop)

    result = asyncio.run(
        apply_service.create_proposal_candidate_from_diagnosis(
            strategy_name="TestStrat",
            run_id="bt-3",
            linked_version=SimpleNamespace(version_id="v-linked"),
            request_snapshot={"exchange": "binance"},
            summary_metrics={"profit_total_pct": 1.0},
            diagnosis={"primary_flags": [], "proposal_actions": []},
            ai_payload={
                "parameter_suggestions": [
                    {"name": "stoploss", "value": -0.12, "reason": "Cut losses sooner."}
                ]
            },
            source_kind="ai_parameter_suggestion",
            source_index=0,
            candidate_mode="auto",
        )
    )

    assert result.success is True
    assert result.source_title.startswith("stoploss = -0.12")
    assert result.ai_mode == "parameter_only"
    request = captured["request"]
    assert request.parent_version_id == "v-linked"
    assert request.parameters == {"stoploss": -0.12}


def test_ai_chat_draft_parameter_candidate_uses_stage_backtest_candidate(monkeypatch):
    captured = {}

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(
            version_id="v-chat-params",
            status="created",
            message="created",
        )

    monkeypatch.setattr(apply_service.mutation_service, "create_mutation", _create_mutation)
    monkeypatch.setattr(
        apply_service.mutation_service,
        "get_version_by_id",
        lambda version_id: _version(version_id, ChangeType.PARAMETER_CHANGE),
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
            candidate_summary="AI chat candidate",
        )
    )

    assert result.success is True
    assert result.source_title == "AI Chat Draft"
    assert result.ai_mode == "parameter_only"
    request = captured["request"]
    assert request.parent_version_id == "v-linked"
    assert request.parameters == {"stoploss": -0.11}
    assert request.code is None


def test_ai_chat_draft_code_candidate_uses_stage_backtest_candidate(monkeypatch):
    captured = {}

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(
            version_id="v-chat-code",
            status="created",
            message="created",
        )

    monkeypatch.setattr(apply_service.mutation_service, "create_mutation", _create_mutation)
    monkeypatch.setattr(
        apply_service.mutation_service,
        "get_version_by_id",
        lambda version_id: _version(version_id, ChangeType.CODE_CHANGE),
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
            candidate_summary="AI chat code candidate",
        )
    )

    assert result.success is True
    assert result.source_title == "AI Chat Draft"
    assert result.ai_mode == "code_patch"
    request = captured["request"]
    assert request.parent_version_id == "v-linked"
    assert request.code == "class TestStrat:\n    pass\n"
    assert request.parameters is None
