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
from app.services.ai_chat.apply_code_service import create_run_scoped_candidate
from app.services.ai_chat.loop_service import LoopConfig, analyze_with_two_mode, run_ai_loop
from app.services.ai_chat.persistent_chat_service import TERMINAL_JOB_STATUSES, persistent_ai_chat_service


router = APIRouter()


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
    allow_run_actions: bool = False


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
    canonical_payload = await create_run_scoped_candidate(
        run_id=request.run_id,
        strategy_name=request.strategy_name,
        code=request.code,
        summary=request.summary,
    )
    return {
        **canonical_payload,
        "success": True,
        "version_id": canonical_payload["candidate_version_id"],
    }

@router.post("/apply-parameters")
async def apply_parameters_endpoint(request: ApplyParamsRequest):
    """Create a run-scoped parameter candidate through the unified proposal lifecycle."""
    canonical_payload = await create_run_scoped_candidate(
        run_id=request.run_id,
        strategy_name=request.strategy_name,
        parameters=request.parameters,
        summary=request.summary,
    )
    return {
        **canonical_payload,
        "success": True,
        "version_id": canonical_payload["candidate_version_id"],
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
