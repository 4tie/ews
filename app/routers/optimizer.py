from __future__ import annotations

import asyncio
import json
import os
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.optimizer_models import OptimizationRunCreateRequest, OptimizerRunRequest
from app.services.autotune.auto_optimize_service import AutoOptimizeFatalError, auto_optimize_service
from app.services.autotune.iterative_optimizer import IterativeOptimizer
from app.services.persistence_service import PersistenceService

router = APIRouter()
persistence = PersistenceService()


@router.post("/runs")
async def create_optimizer_run(payload: OptimizationRunCreateRequest | OptimizerRunRequest):
    """Start a new optimizer run.

    - Auto Optimize v1: baseline explicit (OptimizationRunCreateRequest)
    - Legacy hyperopt: OptimizerRunRequest
    """
    if isinstance(payload, OptimizationRunCreateRequest):
        try:
            record = auto_optimize_service.start_run(payload)
        except AutoOptimizeFatalError as exc:
            raise HTTPException(status_code=400, detail=exc.error.model_dump(mode="json")) from exc
        return {
            "optimizer_run_id": record.optimizer_run_id,
            "status": record.status.value,
        }

    run_id = f"opt-{uuid.uuid4().hex[:8]}"
    optimizer = IterativeOptimizer(run_id)
    result = optimizer.start(payload.model_dump())
    return {
        "run_id": run_id,
        "status": result.get("status"),
        "message": "Optimizer run started",
    }


@router.post("/runs/{run_id}/stop")
async def stop_optimizer(run_id: str):
    record = auto_optimize_service.stop_run(run_id)
    if record is not None:
        return {"run_id": run_id, "status": "stopped"}

    legacy = persistence.load_optimizer_run(run_id)
    if isinstance(legacy, dict) and legacy.get("run_id"):
        optimizer = IterativeOptimizer(run_id)
        return optimizer.stop()

    raise HTTPException(status_code=404, detail=f"Optimizer run {run_id} not found")


@router.get("/runs/{optimizer_run_id}")
async def get_optimizer_run(optimizer_run_id: str):
    record = auto_optimize_service.get_run(optimizer_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Optimizer run {optimizer_run_id} not found")
    return record.model_dump(mode="json")


@router.get("/runs/{optimizer_run_id}/stream")
async def stream_optimizer_events(optimizer_run_id: str):
    """Server-sent event stream for Auto Optimize JSONL events."""

    async def event_generator():
        yield f"data: {json.dumps({'event_type': 'optimizer_stream_started', 'optimizer_run_id': optimizer_run_id})}\n\n"

        path = persistence.optimizer_events_path(optimizer_run_id)
        last_pos = 0

        while True:
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as handle:
                        handle.seek(last_pos)
                        for line in handle:
                            text = line.strip()
                            if text:
                                yield f"data: {text}\n\n"
                        last_pos = handle.tell()
                except OSError:
                    pass

            record = auto_optimize_service.get_run(optimizer_run_id)
            if record is not None and record.status.value in {"failed", "completed"}:
                if os.path.isfile(path):
                    try:
                        with open(path, "r", encoding="utf-8", errors="replace") as handle:
                            handle.seek(last_pos)
                            for line in handle:
                                text = line.strip()
                                if text:
                                    yield f"data: {text}\n\n"
                    except OSError:
                        pass

                yield f"data: {json.dumps({'event_type': 'optimizer_stream_done', 'optimizer_run_id': optimizer_run_id})}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/runs/{run_id}/logs/stream")
async def stream_logs(run_id: str):
    """Server-sent event stream for legacy optimizer live logs."""

    async def log_generator():
        yield f"data: {json.dumps({'line': f'[optimizer] Run {run_id} - streaming started'})}\n\n"
        await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")


@router.get("/runs/{run_id}/checkpoints")
async def get_checkpoints(run_id: str):
    """Return checkpoints for a legacy optimizer run."""
    optimizer = IterativeOptimizer(run_id)
    return {"run_id": run_id, "checkpoints": optimizer.list_checkpoints()}


@router.post("/runs/{run_id}/rollback/{checkpoint_id}")
async def rollback_to_checkpoint(run_id: str, checkpoint_id: str):
    """Roll back a legacy optimizer run to a specific checkpoint."""
    # Load run metadata to get strategy_name
    run_meta = persistence.load_optimizer_run(run_id)
    if not run_meta:
        raise HTTPException(status_code=404, detail=f"Optimizer run {run_id} not found")
    
    # Extract strategy from payload
    payload = run_meta.get("payload", {})
    strategy_name = payload.get("strategy")
    if not strategy_name:
        raise HTTPException(status_code=400, detail="Strategy name not found in optimizer run metadata")
    
    # Call rollback with strategy_name
    result = persistence.rollback(run_id, checkpoint_id, strategy_name)
    
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    
    return result
