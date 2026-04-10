from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.models.optimizer_models import OptimizerRunRequest
from app.services.autotune.iterative_optimizer import IterativeOptimizer
from app.services.persistence_service import PersistenceService
import asyncio
import json
import uuid

router = APIRouter()
persistence = PersistenceService()


@router.post("/runs")
async def create_optimizer_run(payload: OptimizerRunRequest):
    """Start a new optimizer run."""
    run_id = f"opt-{uuid.uuid4().hex[:8]}"
    optimizer = IterativeOptimizer(run_id)
    result = optimizer.start(payload.model_dump())
    return {"run_id": run_id, "status": result.get("status"), "message": "Optimizer run started"}


@router.get("/runs/{run_id}/logs/stream")
async def stream_logs(run_id: str):
    """Server-sent event stream for optimizer live logs."""
    async def log_generator():
        yield f"data: {json.dumps({'line': f'[optimizer] Run {run_id} — streaming started'})}\n\n"
        await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")


@router.get("/runs/{run_id}/checkpoints")
async def get_checkpoints(run_id: str):
    """Return checkpoints for a given optimizer run."""
    optimizer = IterativeOptimizer(run_id)
    return {"run_id": run_id, "checkpoints": optimizer.list_checkpoints()}


@router.post("/runs/{run_id}/rollback/{checkpoint_id}")
async def rollback_to_checkpoint(run_id: str, checkpoint_id: str):
    """Roll back an optimizer run to a specific checkpoint."""
    result = persistence.rollback(run_id, checkpoint_id)
    return {"run_id": run_id, "checkpoint_id": checkpoint_id, "status": "rolled_back", "data": result}
