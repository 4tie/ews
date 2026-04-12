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


def test_deterministic_action_creates_parameter_candidate_and_records_provenance(monkeypatch):
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
                    {
                        "action_type": "tighten_stoploss",
                        "label": "Tighten Stoploss",
                        "matched_rules": ["high_drawdown"],
                    }
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
    assert result.candidate_status == "candidate"
    request = captured["request"]
    assert request.parent_version_id == "v-linked"
    assert request.source_ref == "backtest_run:bt-1"
    assert request.source_kind == "deterministic_action"
    assert request.source_context == {
        "run_id": "bt-1",
        "source_index": 0,
        "title": "Tighten Stoploss",
        "candidate_mode": "parameter_only",
        "action_type": "tighten_stoploss",
        "matched_rules": ["high_drawdown"],
        "flag_rule": "high_drawdown",
    }
    assert request.parameters["stoploss"] == -0.15
    assert request.parameters["trailing_stop"] is True
    assert request.parameters["trailing_stop_positive"] == 0.01


def test_ranked_issue_maps_to_review_exit_timing_and_records_rule_provenance(monkeypatch):
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
    assert result.candidate_status == "candidate"
    request = captured["request"]
    assert request.source_ref == "backtest_run:bt-2"
    assert request.source_kind == "ranked_issue"
    assert request.source_context == {
        "run_id": "bt-2",
        "source_index": 0,
        "title": "high_drawdown [warning]: High drawdown",
        "candidate_mode": "parameter_only",
        "action_type": "review_exit_timing",
        "rule": "high_drawdown",
        "flag_rule": "high_drawdown",
    }
    assert request.parameters["minimal_roi"] == {"0": 0.05, "30": 0.02}
    assert request.parameters["trailing_stop_positive"] == 0.014


def test_deterministic_action_falls_back_to_code_snapshot_parameters(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        apply_service.mutation_service,
        "resolve_effective_artifacts",
        lambda version_id: {
            "strategy_name": "MultiMa",
            "code_snapshot": """
from freqtrade.strategy import IntParameter

class MultiMa:
    buy_params = {"buy_rsi": 31}
    minimal_roi = {"0": 0.5, "60": 0.1}
    stoploss = -0.345
    trailing_stop = False
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    buy_rsi = IntParameter(10, 50, default=31)
""",
            "parameters_snapshot": None,
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
            strategy_name="MultiMa",
            run_id="bt-live-fallback",
            linked_version=SimpleNamespace(version_id="v-linked"),
            request_snapshot={},
            summary_metrics={},
            diagnosis={
                "proposal_actions": [
                    {
                        "action_type": "review_exit_timing",
                        "label": "Review Exit Timing",
                        "matched_rules": ["exit_inefficiency"],
                    }
                ]
            },
            ai_payload={},
            source_kind="deterministic_action",
            source_index=0,
            candidate_mode="auto",
        )
    )

    assert result.success is True
    request = captured["request"]
    assert request.parameters["minimal_roi"] == {"0": 0.5, "30": 0.1}
    assert request.parameters["trailing_stop_positive"] == 0.014
    assert request.parameters["buy_rsi"] == 31


def test_tighten_entries_supports_buy_ma_controls_from_code_snapshot(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        apply_service.mutation_service,
        "resolve_effective_artifacts",
        lambda version_id: {
            "strategy_name": "MultiMa",
            "code_snapshot": """
class MultiMa:
    buy_params = {"buy_ma_count": 5, "buy_ma_gap": 13}
    count_max = 20
    gap_max = 100
    buy_ma_count = 5
    buy_ma_gap = 13
""",
            "parameters_snapshot": None,
        },
    )

    def _create_mutation(request):
        captured["request"] = request
        return MutationResult(
            version_id="v-tighten",
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
            strategy_name="MultiMa",
            run_id="bt-tighten",
            linked_version=SimpleNamespace(version_id="v-linked"),
            request_snapshot={},
            summary_metrics={},
            diagnosis={
                "proposal_actions": [
                    {
                        "action_type": "tighten_entries",
                        "label": "Tighten Entries",
                        "matched_rules": ["low_win_rate"],
                    }
                ]
            },
            ai_payload={},
            source_kind="deterministic_action",
            source_index=0,
            candidate_mode="auto",
        )
    )

    assert result.success is True
    request = captured["request"]
    assert request.parameters["buy_ma_count"] == 6
    assert request.parameters["buy_ma_gap"] == 14
    assert request.parameters["buy_params"] == {"buy_ma_count": 6, "buy_ma_gap": 14}


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
    assert request.source_ref == "backtest_run:bt-3"
    assert request.source_kind == "ai_parameter_suggestion"
    assert request.source_context == {
        "run_id": "bt-3",
        "candidate_mode": "parameter_only",
        "source_index": 0,
        "title": "stoploss = -0.12: Cut losses sooner.",
    }


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
    assert request.source_ref == "backtest_run:bt-4"
    assert request.source_kind == "ai_chat_draft"
    assert request.summary == "AI chat candidate from run bt-4"
    assert request.source_context == {
        "run_id": "bt-4",
        "source_index": 0,
        "title": "AI Chat Draft",
        "candidate_mode": "parameter_only",
        "chat_summary": "AI chat candidate",
    }


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
    assert request.source_ref == "backtest_run:bt-5"
    assert request.source_kind == "ai_chat_draft"
    assert request.summary == "AI chat candidate from run bt-5"
    assert request.source_context == {
        "run_id": "bt-5",
        "source_index": 0,
        "title": "AI Chat Draft",
        "candidate_mode": "code_patch",
        "chat_summary": "AI chat code candidate",
    }

def test_stage_backtest_candidate_returns_additive_canonical_response(monkeypatch):
    monkeypatch.setattr(
        apply_service.mutation_service,
        "create_mutation",
        lambda request: MutationResult(version_id="v-stage", status="created", message="created"),
    )
    monkeypatch.setattr(
        apply_service.mutation_service,
        "get_version_by_id",
        lambda version_id: _version(version_id, ChangeType.PARAMETER_CHANGE),
    )

    result = apply_service.stage_backtest_candidate(
        strategy_name="TestStrat",
        linked_version=SimpleNamespace(version_id="v-linked"),
        summary="AI chat candidate from run bt-stage",
        created_by="ai_apply",
        parameters={"stoploss": -0.11},
        source_ref="backtest_run:bt-stage",
        source_kind="ai_chat_draft",
        source_context={"run_id": "bt-stage", "source_index": 0, "title": "AI Chat Draft"},
        source_title="AI Chat Draft",
        ai_mode="parameter_only",
    )

    payload = result.to_response_payload()
    assert payload["baseline_run_id"] == "bt-stage"
    assert payload["baseline_version_id"] == "v-linked"
    assert payload["baseline_run_version_id"] == "v-linked"
    assert payload["version_id"] == "v-stage"
    assert payload["candidate_version_id"] == "v-stage"
    assert payload["change_type"] == "parameter_change"
    assert payload["candidate_change_type"] == "parameter_change"
    assert payload["status"] == "candidate"
    assert payload["candidate_status"] == "candidate"
    assert payload["source_kind"] == "ai_chat_draft"
    assert payload["source_index"] == 0
    assert payload["source_title"] == "AI Chat Draft"
    assert payload["ai_mode"] == "parameter_only"
    assert payload["candidate_ai_mode"] == "parameter_only"


def test_apply_strategy_recommendations_uses_stage_backtest_candidate(monkeypatch):
    calls = []

    def _stage(**kwargs):
        calls.append(kwargs)
        return apply_service.ProposalCandidateResult(success=True, message="created", version_id="v-stage")

    monkeypatch.setattr(apply_service, "stage_backtest_candidate", _stage)
    monkeypatch.setattr(apply_service.mutation_service, "get_active_version", lambda strategy_name: SimpleNamespace(version_id="v-live"))

    result = asyncio.run(
        apply_service.apply_strategy_recommendations(
            strategy_name="TestStrat",
            parameters={"stoploss": -0.11},
        )
    )

    assert result.success is True
    assert calls == [
        {
            "strategy_name": "TestStrat",
            "linked_version": SimpleNamespace(version_id="v-live"),
            "summary": "AI parameter recommendation for TestStrat",
            "created_by": "ai_apply",
            "parameters": {"stoploss": -0.11},
        }
    ]
