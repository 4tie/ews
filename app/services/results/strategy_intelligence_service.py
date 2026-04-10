"""
Strategy Intelligence Service - AI-powered strategy analysis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ai.models import get_dispatch
from app.ai.prompts.trading import (
    CODE_AWARE_ADVISOR_SYSTEM_PROMPT,
    ANALYST_SYSTEM_PROMPT,
)
from app.ai.output_format import parse_ai_response


@dataclass
class IntelligenceResult:
    analysis: str
    recommendations: list[str]
    parameters: dict[str, Any] | None
    code_suggestions: str | None
    is_applicable: bool


async def analyze_strategy(
    strategy_name: str,
    strategy_code: str,
    backtest_results: dict[str, Any],
    user_question: str | None = None,
) -> IntelligenceResult:
    """Analyze strategy and provide AI-powered insights."""
    dispatch = get_dispatch()
    
    metrics_summary = _format_metrics(backtest_results)
    
    context = f"""Strategy: {strategy_name}

Metrics:
{metrics_summary}

User Question: {user_question or 'Provide general analysis and recommendations'}
"""
    
    system_prompt = f"{CODE_AWARE_ADVISOR_SYSTEM_PROMPT}\n\n{context}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": strategy_code[:3000]},
    ]
    
    response = await dispatch.complete(
        messages=messages,
        model="openai/gpt-4o",
        temperature=0.3,
        max_tokens=4000,
    )
    
    parsed = parse_ai_response(response.content)
    
    recommendations = []
    if parsed.is_applicable and parsed.parameters:
        recommendations = [f"{k}: {v}" for k, v in parsed.parameters.items()]
    
    return IntelligenceResult(
        analysis=response.content,
        recommendations=recommendations,
        parameters=parsed.parameters if parsed.is_applicable else None,
        code_suggestions=parsed.code if parsed.mode == "code_patch" else None,
        is_applicable=parsed.is_applicable,
    )


async def analyze_metrics(
    metrics: dict[str, Any],
    context: str | None = None,
) -> IntelligenceResult:
    """Analyze trading metrics and provide insights."""
    dispatch = get_dispatch()
    
    metrics_summary = _format_metrics(metrics)
    
    messages = [
        {"role": "system", "content": ANALYST_SYSTEM_PROMPT},
        {"role": "user", "content": f"{metrics_summary}\n\nContext: {context or 'General analysis'}"},
    ]
    
    response = await dispatch.complete(
        messages=messages,
        model="openai/gpt-4o",
        temperature=0.4,
        max_tokens=3000,
    )
    
    return IntelligenceResult(
        analysis=response.content,
        recommendations=[],
        parameters=None,
        code_suggestions=None,
        is_applicable=True,
    )


def _format_metrics(results: dict[str, Any]) -> str:
    key_metrics = [
        "total_profit",
        "profit_ratio",
        "profit_factor",
        "win_rate",
        "max_drawdown",
        "sharpe",
        "sortino",
        "total_trades",
        "avg_trade",
        "calmar",
    ]
    
    lines = []
    for metric in key_metrics:
        if metric in results:
            value = results[metric]
            lines.append(f"{metric}: {value}")
    
    return "\n".join(lines)


__all__ = ["IntelligenceResult", "analyze_strategy", "analyze_metrics"]
