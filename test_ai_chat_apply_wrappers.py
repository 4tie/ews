import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.models.backtest_models import (
    BacktestRunRecord,
    BacktestRunStatus,
    BacktestTriggerSource,
    ProposalCandidateMode,
    ProposalCandidateRequest,
    ProposalSourceKind,
)
from app.models.optimizer_models import ChangeType, MutationResult, VersionStatus
from app.routers import ai_chat as ai_chat_router
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


def _canonical_payload() -> dict:
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


def _version(change_type: ChangeType) -> SimpleNamespace:
    return SimpleNamespace(change_type=change_type, status=VersionStatus.CANDIDATE)


class AiChatApplyWrapperTests(unittest.IsolatedAsyncioTestCase):
    async def test_apply_code_wrapper_delegates_to_runtime_with_canonical_request(self):
        canonical_payload = {
            **_canonical_payload(),
            "candidate_change_type": "code_change",
            "candidate_ai_mode": "code_patch",
        }
        runtime_create = AsyncMock(return_value=canonical_payload)

        with patch("app.services.ai_chat.apply_code_service._load_run_record", return_value=_run_record()), patch(
            "app.services.ai_chat.apply_code_service.runtime.create_backtest_run_proposal_candidate",
            runtime_create,
        ):
            response = await ai_chat_router.apply_code(
                ai_chat_router.ApplyCodeRequest(
                    run_id="bt-1",
                    strategy_name="TestStrat",
                    code="class TestStrat:\n    pass\n",
                    summary="Tighten entries after pullback",
                )
            )

        runtime_create.assert_awaited_once()
        run_id, payload = runtime_create.await_args.args
        self.assertEqual(run_id, "bt-1")
        self.assertIsInstance(payload, ProposalCandidateRequest)
        self.assertEqual(payload.source_kind, ProposalSourceKind.AI_CHAT_DRAFT)
        self.assertEqual(payload.source_index, 0)
        self.assertEqual(payload.candidate_mode, ProposalCandidateMode.CODE_PATCH)
        self.assertIsNone(payload.parameters)
        self.assertEqual(payload.code, "class TestStrat:\n    pass\n")
        self.assertEqual(payload.summary, "Tighten entries after pullback")

        self.assertEqual(list(response.keys())[: len(canonical_payload)], list(canonical_payload.keys()))
        self.assertEqual(list(response.keys())[-2:], ["success", "version_id"])
        self.assertEqual(set(response.keys()), set(canonical_payload.keys()) | {"success", "version_id"})
        self.assertEqual(response["candidate_version_id"], "v-candidate")
        self.assertEqual(response["version_id"], "v-candidate")
        self.assertTrue(response["success"])

    async def test_apply_parameters_wrapper_delegates_to_runtime_with_canonical_request(self):
        canonical_payload = _canonical_payload()
        runtime_create = AsyncMock(return_value=canonical_payload)

        with patch("app.services.ai_chat.apply_code_service._load_run_record", return_value=_run_record()), patch(
            "app.services.ai_chat.apply_code_service.runtime.create_backtest_run_proposal_candidate",
            runtime_create,
        ):
            response = await ai_chat_router.apply_parameters_endpoint(
                ai_chat_router.ApplyParamsRequest(
                    run_id="bt-1",
                    strategy_name="TestStrat",
                    parameters={"stoploss": -0.12},
                    summary=None,
                )
            )

        runtime_create.assert_awaited_once()
        run_id, payload = runtime_create.await_args.args
        self.assertEqual(run_id, "bt-1")
        self.assertIsInstance(payload, ProposalCandidateRequest)
        self.assertEqual(payload.source_kind, ProposalSourceKind.AI_CHAT_DRAFT)
        self.assertEqual(payload.source_index, 0)
        self.assertEqual(payload.candidate_mode, ProposalCandidateMode.PARAMETER_ONLY)
        self.assertEqual(payload.parameters, {"stoploss": -0.12})
        self.assertIsNone(payload.code)
        self.assertIsNone(payload.summary)

        self.assertEqual(list(response.keys())[: len(canonical_payload)], list(canonical_payload.keys()))
        self.assertEqual(list(response.keys())[-2:], ["success", "version_id"])
        self.assertEqual(set(response.keys()), set(canonical_payload.keys()) | {"success", "version_id"})
        self.assertEqual(response["candidate_version_id"], "v-candidate")
        self.assertEqual(response["version_id"], "v-candidate")
        self.assertTrue(response["success"])


class AiChatDraftSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_chat_draft_without_summary_uses_canonical_run_summary(self):
        captured = {}

        def _create_mutation(request):
            captured["request"] = request
            return MutationResult(version_id="v-chat-params", status="created", message="created")

        with patch.object(apply_service.mutation_service, "create_mutation", side_effect=_create_mutation), patch.object(
            apply_service.mutation_service,
            "get_version_by_id",
            return_value=_version(ChangeType.PARAMETER_CHANGE),
        ):
            result = await apply_service.create_proposal_candidate_from_diagnosis(
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

        self.assertTrue(result.success)
        request = captured["request"]
        self.assertEqual(request.summary, "AI chat candidate from run bt-4")
        self.assertEqual(request.source_ref, "backtest_run:bt-4")
        self.assertEqual(request.source_kind, "ai_chat_draft")
        self.assertEqual(request.source_context, {"run_id": "bt-4", "candidate_mode": "parameter_only"})

    async def test_ai_chat_draft_keeps_chat_summary_supplemental(self):
        captured = {}

        def _create_mutation(request):
            captured["request"] = request
            return MutationResult(version_id="v-chat-code", status="created", message="created")

        with patch.object(apply_service.mutation_service, "create_mutation", side_effect=_create_mutation), patch.object(
            apply_service.mutation_service,
            "get_version_by_id",
            return_value=_version(ChangeType.CODE_CHANGE),
        ):
            result = await apply_service.create_proposal_candidate_from_diagnosis(
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

        self.assertTrue(result.success)
        request = captured["request"]
        self.assertEqual(request.summary, "AI chat candidate from run bt-5")
        self.assertEqual(
            request.source_context,
            {
                "run_id": "bt-5",
                "candidate_mode": "code_patch",
                "chat_summary": "Tighten entries after pullback",
            },
        )
        self.assertEqual(request.source_ref, "backtest_run:bt-5")
        self.assertEqual(request.source_kind, "ai_chat_draft")


if __name__ == "__main__":
    unittest.main()