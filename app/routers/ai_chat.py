"""
AI Chat Router - Endpoints for AI-powered chat with two-mode output enforcement.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from app.ai.output_format import parse_ai_response
from app.services.ai_chat.apply_code_service import apply_code_patch, apply_parameters
from app.services.ai_chat.loop_service import LoopConfig, analyze_with_two_mode, run_ai_loop


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
    strategy_name: str
    code: str
    strategy_dir: str | None = None
    create_backup: bool = True


class ApplyParamsRequest(BaseModel):
    strategy_name: str
    parameters: dict[str, Any]


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


@router.post("/apply-code")
async def apply_code(request: ApplyCodeRequest):
    """Create a candidate version from AI-generated code."""
    result = await apply_code_patch(
        strategy_name=request.strategy_name,
        code=request.code,
        strategy_dir=request.strategy_dir,
        create_backup=request.create_backup,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return {
        "success": True,
        "version_id": result.version_id,
        "message": result.message,
        "file_path": result.file_path,
        "backup_path": result.backup_path,
    }


@router.post("/apply-parameters")
async def apply_parameters_endpoint(request: ApplyParamsRequest):
    """Create a candidate version from AI-generated parameters."""
    result = await apply_parameters(
        strategy_name=request.strategy_name,
        parameters=request.parameters,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return {
        "success": True,
        "version_id": result.version_id,
        "message": result.message,
        "file_path": result.file_path,
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
