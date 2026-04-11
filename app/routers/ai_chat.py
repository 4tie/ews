"""
AI Chat Router - Endpoints for AI-powered chat with unified run-scoped candidate creation.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.ai.output_format import parse_ai_response
from app.models.backtest_models import BacktestRunRecord
from app.services.ai_chat.loop_service import LoopConfig, analyze_with_two_mode, run_ai_loop
from app.services.ai_chat.persistent_chat_service import TERMINAL_JOB_STATUSES, persistent_ai_chat_service
from app.services.mutation_service import mutation_service
from app.services.persistence_service import PersistenceService
from app.services.results.diagnosis_service import diagnosis_service
from app.services.results.strategy_intelligence_apply_service import create_proposal_candidate_from_diagnosis
from app.services.results_service import ResultsService


router = APIRouter()
persistence = PersistenceService()
results_svc = ResultsService()


class ChatRequest(BaseModel):
    message: str
    strategy_name: str | None = None
    strategy_code: str | None = None
    backtest_results: dict[str, Any] | None = None
    optimizer_results: dict[str, Any] | None = None
    max_iterations: int = 5
    temperature: float = 0.3


class AnalyzeRequest(BaseModel):
    message: str
    context: str | None = None
    strategy_code: str | None = None


class ApplyCodeRequest(BaseModel):
    run_id: str
    strategy_name: str
    code: str
    summary: str | None = None


class ApplyParamsRequest(BaseModel):
    run_id: str
    strategy_name: str
    parameters: dict[str, Any]
    summary: str | None = None


class PersistentThreadContext(BaseModel):
    run_id: str | None = None
    version_id: str | None = None
    diagnosis_status: str | None = None
    summary_available: bool = False
    version_source: str | None = None


class PersistentThreadMessageRequest(BaseModel):
    message: str
    context: PersistentThreadContext | None = None


@router.post("/chat")
async def chat(request: ChatRequest):
    """Run AI chat loop with two-mode output enforcement."""
    config = LoopConfig(
        max_iterations=request.max_iterations,
        temperature=request.temperature,
    )

    result = await run_ai_loop(
        user_message=request.message,
        strategy_name=request.strategy_name,
        strategy_code=request.strategy_code,
        backtest_results=request.backtest_results,
        optimizer_results=request.optimizer_results,
        config=config,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return {
        "success": True,
        "mode": result.final_parameters and "parameter_only" or "code_patch",
        "parameters": result.final_parameters,
        "code": result.final_code,
        "iterations": len(result.iterations),
    }


@router.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """Analyze request with two-mode output (single turn)."""
    parsed = await analyze_with_two_mode(
        user_message=request.message,
        context=request.context,
        strategy_code=request.strategy_code,
    )

    return {
        "mode": parsed.mode,
        "is_applicable": parsed.is_applicable,
        "parameters": parsed.parameters,
        "code": parsed.code[:500] if parsed.code else None,
        "validation_errors": parsed.validation_errors,
    }


@router.get("/threads/{strategy_name}")
async def get_strategy_thread(strategy_name: str):
    return persistent_ai_chat_service.get_thread(strategy_name)


@router.post("/threads/{strategy_name}/messages")
async def create_strategy_thread_message(strategy_name: str, request: PersistentThreadMessageRequest):
    try:
        return await persistent_ai_chat_service.enqueue_message(
            strategy_name=strategy_name,
            message_text=request.message,
            context=request.context.model_dump(mode="json") if request.context else None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
async def get_ai_job(job_id: str):
    payload = persistent_ai_chat_service.get_job(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail=f"AI job {job_id} not found")
    return payload


@router.get("/jobs/{job_id}/stream")
async def stream_ai_job(job_id: str, request: Request):
    payload = persistent_ai_chat_service.get_job(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail=f"AI job {job_id} not found")

    try:
        last_event_id = int(str(request.headers.get("last-event-id") or "0"))
    except ValueError:
        last_event_id = 0

    async def event_generator():
        delivered = last_event_id
        while True:
            current = persistent_ai_chat_service.get_job(job_id)
            job = current.get("job") if isinstance(current, dict) else None
            if not isinstance(job, dict) or not job:
                failure_payload = {
                    "id": f"{job_id}:missing",
                    "seq": delivered,
                    "type": "failed",
                    "message": f"AI job {job_id} not found",
                }
                yield _sse(failure_payload)
                return

            events = job.get("timeline_events") if isinstance(job.get("timeline_events"), list) else []
            for event in events:
                seq = int(event.get("seq") or 0)
                if seq <= delivered:
                    continue
                delivered = seq
                yield _sse(event)

            if str(job.get("status") or "") in TERMINAL_JOB_STATUSES:
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/apply-code")
async def apply_code(request: ApplyCodeRequest):
    """Create a run-scoped code candidate through the unified proposal lifecycle."""
    result = await _create_run_scoped_ai_candidate(
        run_id=request.run_id,
        strategy_name=request.strategy_name,
        code=request.code,
        summary=request.summary,
    )
    return {
        "success": True,
        "version_id": result["candidate_version_id"],
        "message": result["message"],
        "candidate_change_type": result["candidate_change_type"],
        "candidate_status": result["candidate_status"],
    }


@router.post("/apply-parameters")
async def apply_parameters_endpoint(request: ApplyParamsRequest):
    """Create a run-scoped parameter candidate through the unified proposal lifecycle."""
    result = await _create_run_scoped_ai_candidate(
        run_id=request.run_id,
        strategy_name=request.strategy_name,
        parameters=request.parameters,
        summary=request.summary,
    )
    return {
        "success": True,
        "version_id": result["candidate_version_id"],
        "message": result["message"],
        "candidate_change_type": result["candidate_change_type"],
        "candidate_status": result["candidate_status"],
    }


@router.get("/validate-output")
async def validate_output(text: str):
    """Validate AI output follows two-mode format."""
    parsed = parse_ai_response(text)
    return {
        "mode": parsed.mode,
        "is_applicable": parsed.is_applicable,
        "validation_errors": parsed.validation_errors,
    }


def _sse(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    event_id = data.get("seq")
    if event_id is not None:
        return f"id: {event_id}\ndata: {payload}\n\n"
    return f"data: {payload}\n\n"
def _load_run_record(run_id: str) -> BacktestRunRecord:
    data = persistence.load_backtest_run(run_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    try:
        run = BacktestRunRecord(**data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Run {run_id} could not be loaded: {exc}") from exc
    if str(getattr(run, "engine", "freqtrade")) != "freqtrade":
        raise HTTPException(status_code=400, detail=f"Run {run_id} is not a freqtrade run")
    return run


def _resolve_linked_version_for_run(run: BacktestRunRecord):
    if run.version_id:
        linked_version = mutation_service.get_version_by_id(run.version_id)
        if linked_version is not None:
            return linked_version, "run"

    active_version = mutation_service.get_active_version(run.strategy)
    if active_version is not None:
        return active_version, "active_fallback"

    return None, "unavailable"


async def _create_run_scoped_ai_candidate(
    *,
    run_id: str,
    strategy_name: str,
    parameters: dict[str, Any] | None = None,
    code: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    run = _load_run_record(run_id)
    if run.strategy != strategy_name:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} belongs to {run.strategy}, not {strategy_name}",
        )

    summary_state = results_svc.load_run_summary_state(run)
    if summary_state.get("state") != "ready":
        raise HTTPException(
            status_code=400,
            detail=summary_state.get("error") or "Summary is not ready for proposal generation yet.",
        )

    summary_payload = summary_state.get("summary")
    summary_block = results_svc.extract_run_summary_block(summary_payload, run.strategy) if summary_payload else None
    summary_metrics = results_svc._normalize_summary_metrics(summary_payload, run.strategy) if summary_payload else None
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

    result = await create_proposal_candidate_from_diagnosis(
        strategy_name=run.strategy,
        run_id=run.run_id,
        linked_version=linked_version,
        request_snapshot=run.request_snapshot or {},
        summary_metrics=summary_metrics,
        diagnosis=diagnosis,
        ai_payload={},
        source_kind="ai_chat_draft",
        source_index=0,
        candidate_mode="code_patch" if code else "parameter_only",
        candidate_parameters=parameters,
        candidate_code=code,
        candidate_summary=summary,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or result.message)

    return {
        "baseline_run_id": run.run_id,
        "baseline_version_id": getattr(linked_version, "version_id", None),
        "baseline_run_version_id": run.version_id,
        "baseline_version_source": linked_source,
        "candidate_version_id": result.version_id,
        "candidate_change_type": result.candidate_change_type,
        "candidate_status": result.candidate_status,
        "message": result.message,
    }



