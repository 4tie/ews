from __future__ import annotations

import asyncio
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.optimizer_models import OptimizationRunCreateRequest
from app.services.autotune.auto_optimize_service import AutoOptimizeFatalError, auto_optimize_service
from app.services.persistence_service import PersistenceService

router = APIRouter()
persistence = PersistenceService()


@router.post("/runs")
async def create_optimizer_run(payload: OptimizationRunCreateRequest):
    """Start a new Auto Optimize v1 run from an explicit baseline run."""
    try:
        record = auto_optimize_service.start_run(payload)
    except AutoOptimizeFatalError as exc:
        raise HTTPException(status_code=400, detail=exc.error.model_dump(mode="json")) from exc
    return {
        "optimizer_run_id": record.optimizer_run_id,
        "status": record.status.value,
    }


@router.post("/runs/{optimizer_run_id}/stop")
async def stop_optimizer(optimizer_run_id: str):
    record = auto_optimize_service.stop_run(optimizer_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Optimizer run {optimizer_run_id} not found")
    return {"optimizer_run_id": optimizer_run_id, "status": "stopped"}


@router.get("/runs/{optimizer_run_id}")
async def get_optimizer_run(optimizer_run_id: str):
    record = auto_optimize_service.get_run(optimizer_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Optimizer run {optimizer_run_id} not found")
    return record.model_dump(mode="json")


@router.get("/runs/{optimizer_run_id}/stream")
async def stream_optimizer_events(optimizer_run_id: str):
    """Server-sent event stream for Auto Optimize JSONL events."""
    if auto_optimize_service.get_run(optimizer_run_id) is None:
        raise HTTPException(status_code=404, detail=f"Optimizer run {optimizer_run_id} not found")

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


@router.get("/runs/{optimizer_run_id}/checkpoints")
async def get_optimizer_checkpoints(optimizer_run_id: str):
    """Get list of checkpoints for an optimizer run."""
    record = auto_optimize_service.get_run(optimizer_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Optimizer run {optimizer_run_id} not found")
    
    checkpoints = persistence.list_checkpoints(optimizer_run_id)
    return {
        "optimizer_run_id": optimizer_run_id,
        "checkpoints": checkpoints,
    }


@router.post("/runs/{optimizer_run_id}/rollback/{checkpoint_id}")
async def rollback_to_checkpoint(optimizer_run_id: str, checkpoint_id: str):
    """Rollback to a specific checkpoint in an optimizer run.
    
    This endpoint:
    1. Loads the checkpoint data
    2. Retrieves the strategy name from run metadata
    3. Creates a ROLLBACK version via mutation_service
    4. Accepts the version to promote it to ACTIVE
    5. Returns the promoted version for UI
    """
    # Verify run exists
    record = auto_optimize_service.get_run(optimizer_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Optimizer run {optimizer_run_id} not found")
    
    # Get run metadata to extract strategy name
    run_meta = persistence.load_optimizer_run(optimizer_run_id)
    if not run_meta:
        raise HTTPException(status_code=400, detail="Optimizer run metadata not found")
    
    strategy_name = run_meta.get("baseline_strategy")
    if not strategy_name:
        raise HTTPException(status_code=400, detail="Strategy name not found in optimizer run metadata")
    
    # Perform rollback (loads checkpoint, creates ROLLBACK version, accepts it)
    try:
        from app.services.mutation_service import mutation_service
        from app.models.optimizer_models import ChangeType, MutationRequest
        from app.utils.datetime_utils import now_iso
        
        # Load checkpoint
        checkpoint = persistence.load_checkpoint(optimizer_run_id, checkpoint_id)
        if not checkpoint:
            raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")
        
        # Extract parameters following Auto Optimize pattern
        params = checkpoint.get("params", {})
        profit_pct = float(checkpoint.get("profit_pct", 0.0))
        
        wrapped_parameters = {
            "hyperopt_params": params,
            "profit_pct": profit_pct,
        }
        
        # Create ROLLBACK version
        mutation_request = MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.ROLLBACK,
            summary=f"Rollback to checkpoint {checkpoint_id} (score: {checkpoint.get('score', '?')})",
            created_by="optimizer",
            parameters=wrapped_parameters,
            source_ref=checkpoint_id,
            source_kind="checkpoint",
            source_context={
                "optimizer_run_id": optimizer_run_id,
                "node_descriptor": checkpoint.get("node_descriptor", "?"),
                "profit_pct": profit_pct,
                "epoch": checkpoint.get("epoch"),
            },
        )
        
        mutation_result = mutation_service.create_mutation(mutation_request)
        if mutation_result.status != "created":
            raise HTTPException(
                status_code=400,
                detail=f"Failed to create ROLLBACK version: {mutation_result.message}"
            )
        
        # Accept the version to promote to ACTIVE
        version_id = mutation_result.version_id
        accept_result = mutation_service.accept_version(
            version_id,
            notes=f"Rolled back to checkpoint {checkpoint_id}"
        )
        if accept_result.status != "accepted":
            raise HTTPException(
                status_code=400,
                detail=f"Failed to accept ROLLBACK version: {accept_result.message}"
            )
        
        # Get the promoted version for response
        promoted_version = mutation_service.get_version_by_id(version_id)
        if not promoted_version:
            raise HTTPException(
                status_code=500,
                detail=f"Promoted version {version_id} not found after acceptance"
            )
        
        return {
            "status": "rolled_back",
            "optimizer_run_id": optimizer_run_id,
            "checkpoint_id": checkpoint_id,
            "version_id": version_id,
            "strategy_name": strategy_name,
            "promoted_version": promoted_version.model_dump(mode="json"),
            "message": f"Successfully rolled back to checkpoint {checkpoint_id}",
        }
        
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(exc)}") from exc
