"""
Evolution Router - Endpoints for AI-powered strategy evolution.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from app.services.results.strategy_intelligence_service import analyze_strategy, analyze_metrics, IntelligenceResult
from app.services.results.strategy_intelligence_apply_service import apply_strategy_recommendations


router = APIRouter()


class StrategyAnalysisRequest(BaseModel):
    strategy_name: str
    strategy_code: str
    backtest_results: dict[str, Any]
    user_question: str | None = None


class MetricsAnalysisRequest(BaseModel):
    metrics: dict[str, Any]
    context: str | None = None


class ApplyRecommendationsRequest(BaseModel):
    strategy_name: str
    parameters: dict[str, Any] | None = None
    code: str | None = None
    strategy_dir: str | None = None


@router.post("/analyze-strategy")
async def analyze_strategy_endpoint(request: StrategyAnalysisRequest):
    """Analyze strategy with AI and get recommendations."""
    result = await analyze_strategy(
        strategy_name=request.strategy_name,
        strategy_code=request.strategy_code,
        backtest_results=request.backtest_results,
        user_question=request.user_question,
    )
    
    return {
        "analysis": result.analysis,
        "recommendations": result.recommendations,
        "parameters": result.parameters,
        "code_suggestions": result.code_suggestions[:500] if result.code_suggestions else None,
        "is_applicable": result.is_applicable,
    }


@router.post("/analyze-metrics")
async def analyze_metrics_endpoint(request: MetricsAnalysisRequest):
    """Analyze trading metrics with AI."""
    result = await analyze_metrics(
        metrics=request.metrics,
        context=request.context,
    )
    
    return {
        "analysis": result.analysis,
        "recommendations": result.recommendations,
    }


@router.post("/apply-recommendations")
async def apply_recommendations_endpoint(request: ApplyRecommendationsRequest):
    """Apply AI recommendations to strategy."""
    result = await apply_strategy_recommendations(
        strategy_name=request.strategy_name,
        parameters=request.parameters,
        code=request.code,
        strategy_dir=request.strategy_dir,
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    
    return {
        "success": True,
        "message": result.message,
        "parameters_applied": result.parameters_applied,
        "code_applied": result.code_applied,
    }


@router.get("/health")
async def health():
    """Health check for AI services."""
    return {"status": "ok", "service": "evolution"}
