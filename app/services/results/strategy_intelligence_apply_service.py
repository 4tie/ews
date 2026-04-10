"""
Strategy Intelligence Apply Service - Applies AI recommendations to strategies.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.ai_chat.apply_code_service import apply_code_patch, apply_parameters


@dataclass
class ApplyIntelligenceResult:
    success: bool
    message: str
    parameters_applied: dict | None = None
    code_applied: bool = False


async def apply_strategy_recommendations(
    strategy_name: str,
    parameters: dict | None = None,
    code: str | None = None,
    strategy_dir: str | None = None,
) -> ApplyIntelligenceResult:
    """Apply AI recommendations to strategy."""
    
    if parameters:
        result = await apply_parameters(
            strategy_name=strategy_name,
            parameters=parameters,
        )
        
        if not result.success:
            return ApplyIntelligenceResult(
                success=False,
                message=f"Failed to apply parameters: {result.error}",
                parameters_applied=None,
                code_applied=False,
            )
    
    if code:
        result = await apply_code_patch(
            strategy_name=strategy_name,
            code=code,
            strategy_dir=strategy_dir,
        )
        
        if not result.success:
            return ApplyIntelligenceResult(
                success=False,
                message=f"Failed to apply code: {result.error}",
                parameters_applied=parameters,
                code_applied=False,
            )
        
        return ApplyIntelligenceResult(
            success=True,
            message="Code and parameters applied successfully",
            parameters_applied=parameters,
            code_applied=True,
        )
    
    if parameters:
        return ApplyIntelligenceResult(
            success=True,
            message="Parameters applied successfully",
            parameters_applied=parameters,
            code_applied=False,
        )
    
    return ApplyIntelligenceResult(
        success=False,
        message="No changes to apply",
        parameters_applied=None,
        code_applied=False,
    )


__all__ = ["ApplyIntelligenceResult", "apply_strategy_recommendations"]
