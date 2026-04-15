"""
Proposal candidate creation and response building.

Orchestrates candidate creation from diagnosis and AI suggestions.
"""
from typing import Any

from fastapi import HTTPException

from app.freqtrade.backtest_diagnosis import _default_ai_payload, _resolve_linked_version_for_run
from app.freqtrade.backtest_process import _load_run_record
from app.models.backtest_models import BacktestRunRecord, ProposalCandidateRequest
from app.services.results.diagnosis_service import diagnosis_service
from app.services.results.strategy_intelligence_service import analyze_run_diagnosis_overlay
from app.services.results_service import ResultsService

results_svc = ResultsService()


def _build_proposal_candidate_response(
    result: Any,
    *,
    run_record: BacktestRunRecord,
    linked_version: Any | None,
    linked_source: str,
    source_kind: str,
    source_index: int,
) -> dict[str, Any]:
    response_payload = {}
    to_payload = getattr(result, "to_response_payload", None)
    if callable(to_payload):
        raw_payload = to_payload()
        if isinstance(raw_payload, dict):
            response_payload = dict(raw_payload)

    candidate_version_id = (
        response_payload.get("candidate_version_id")
        or response_payload.get("version_id")
        or getattr(result, "version_id", None)
    )
    candidate_change_type = (
        response_payload.get("candidate_change_type")
        or response_payload.get("change_type")
        or getattr(result, "candidate_change_type", None)
    )
    candidate_status = (
        response_payload.get("candidate_status")
        or response_payload.get("status")
        or getattr(result, "candidate_status", None)
    )
    candidate_ai_mode = (
        response_payload.get("candidate_ai_mode")
        or response_payload.get("ai_mode")
        or getattr(result, "ai_mode", None)
    )

    response_payload["baseline_run_id"] = run_record.run_id
    response_payload["baseline_version_id"] = (
        response_payload.get("baseline_version_id")
        or getattr(linked_version, "version_id", None)
    )
    response_payload["baseline_run_version_id"] = run_record.version_id
    response_payload["baseline_version_source"] = linked_source
    response_payload["source_kind"] = response_payload.get("source_kind") or source_kind
    response_payload["source_index"] = response_payload.get("source_index", source_index)
    response_payload["source_title"] = response_payload.get("source_title") or getattr(result, "source_title", None)
    response_payload["message"] = response_payload.get("message") or getattr(result, "message", "Candidate version created.")

    if candidate_version_id is not None:
        response_payload["version_id"] = candidate_version_id
        response_payload["candidate_version_id"] = candidate_version_id
    if candidate_change_type is not None:
        response_payload["change_type"] = candidate_change_type
        response_payload["candidate_change_type"] = candidate_change_type
    if candidate_status is not None:
        response_payload["status"] = candidate_status
        response_payload["candidate_status"] = candidate_status
    if candidate_ai_mode is not None:
        response_payload["ai_mode"] = candidate_ai_mode
        response_payload["candidate_ai_mode"] = candidate_ai_mode

    return response_payload


async def create_backtest_run_proposal_candidate(run_id: str, payload: ProposalCandidateRequest):
    run = _load_run_record(run_id)
    if run is None or str(getattr(run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    summary_state = results_svc.load_run_summary_state(run)
    if summary_state.get("state") != "ready":
        raise HTTPException(
            status_code=400,
            detail=summary_state.get("error") or "Summary is not ready for proposal generation yet.",
        )

    summary = summary_state.get("summary")
    summary_block = results_svc.extract_run_summary_block(summary, run.strategy) if summary else None
    summary_metrics = results_svc._normalize_summary_metrics(summary, run.strategy) if summary else None
    trades = summary_block.get("trades") if isinstance(summary_block, dict) and isinstance(summary_block.get("trades"), list) else []
    results_per_pair = (
        summary_block.get("results_per_pair")
        if isinstance(summary_block, dict) and isinstance(summary_block.get("results_per_pair"), list)
        else []
    )

    linked_version, linked_source = _resolve_linked_version_for_run(run)
    if linked_version is None:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} is not linked to a version and no active version fallback is available.",
        )

    diagnosis = diagnosis_service.diagnose_run(
        run_record=run,
        summary_metrics=summary_metrics,
        summary_block=summary_block,
        trades=trades,
        results_per_pair=results_per_pair,
        request_snapshot=run.request_snapshot or {},
        request_snapshot_schema_version=run.request_snapshot_schema_version,
        linked_version=linked_version,
    )

    ai_payload = _default_ai_payload("disabled")
    if payload.source_kind.value == "ai_parameter_suggestion":
        try:
            ai_payload = await analyze_run_diagnosis_overlay(
                strategy_name=run.strategy,
                diagnosis=diagnosis,
                summary_metrics=summary_metrics,
                linked_version=linked_version,
                run_id=run.run_id,
                trades=trades,
                results_per_pair=results_per_pair,
                request_snapshot=run.request_snapshot or {},
            )
        except Exception:
            ai_payload = _default_ai_payload("unavailable")

        if ai_payload.get("ai_status") != "ready":
            raise HTTPException(
                status_code=503,
                detail="AI parameter suggestions are unavailable for this run.",
            )

    create_candidate_fn = None
    try:
        from app.services.results.strategy_intelligence_apply_service import create_proposal_candidate_from_diagnosis
        create_candidate_fn = create_proposal_candidate_from_diagnosis
    except ImportError:
        pass

    if not callable(create_candidate_fn):
        raise HTTPException(status_code=500, detail="Proposal candidate service unavailable")

    result = await create_candidate_fn(
        strategy_name=run.strategy,
        run_id=run.run_id,
        linked_version=linked_version,
        request_snapshot=run.request_snapshot or {},
        summary_metrics=summary_metrics,
        diagnosis=diagnosis,
        ai_payload=ai_payload,
        source_kind=payload.source_kind.value,
        source_index=payload.source_index,
        candidate_mode=payload.candidate_mode.value,
        action_type=payload.action_type.value if payload.action_type else None,
        candidate_parameters=payload.parameters,
        candidate_suggestions=payload.suggestions,
        candidate_code=payload.code,
        candidate_summary=payload.summary,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or result.message)

    return _build_proposal_candidate_response(
        result,
        run_record=run,
        linked_version=linked_version,
        linked_source=linked_source,
        source_kind=payload.source_kind.value,
        source_index=payload.source_index,
    )
