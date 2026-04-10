from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from models.optimizer_models import OptimizerRunRequest
import asyncio
import json

router = APIRouter()


@router.post("/runs")
async def create_optimizer_run(payload: OptimizerRunRequest):
    """Start a new optimizer run."""
    # TODO: wire to iterative_optimizer.start(payload)
    return {"run_id": "opt-placeholder-001", "status": "started", "message": "Optimizer run queued"}


@router.get("/runs/{run_id}/logs/stream")
async def stream_logs(run_id: str):
    """Server-sent event stream for optimizer live logs."""
    async def log_generator():
        # TODO: wire to real log tail for run_id
        yield f"data: {json.dumps({'line': f'[optimizer] Run {run_id} — log stream wiring pending'})}\n\n"
        await asyncio.sleep(0.5)

    return StreamingResponse(log_generator(), media_type="text/event-stream")


@router.get("/runs/{run_id}/checkpoints")
async def get_checkpoints(run_id: str):
    """Return checkpoints for a given optimizer run."""
    # TODO: load from storage/optimizer_runs/{run_id}/checkpoints
    return {"run_id": run_id, "checkpoints": []}


@router.post("/runs/{run_id}/rollback/{checkpoint_id}")
async def rollback_to_checkpoint(run_id: str, checkpoint_id: str):
    """Roll back an optimizer run to a specific checkpoint."""
    # TODO: wire to persistence_service.rollback(run_id, checkpoint_id)
    return {"run_id": run_id, "checkpoint_id": checkpoint_id, "status": "rolled_back"}
