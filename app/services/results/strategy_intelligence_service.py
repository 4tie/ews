"""
Strategy Intelligence Service - AI-powered strategy analysis.
"""
from __future__ import annotations

import json
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


async def analyze_run_diagnosis_overlay(
    strategy_name: str,
    diagnosis: dict[str, Any],
    summary_metrics: dict[str, Any] | None,
    linked_version: Any | None,
) -> dict[str, Any]:
    """Produce an optional AI overlay for deterministic run diagnosis."""
    dispatch = get_dispatch()

    context = {
        "strategy": strategy_name,
        "summary_metrics": summary_metrics or {},
        "diagnosis": {
            "facts": diagnosis.get("facts") or {},
            "primary_flags": diagnosis.get("primary_flags") or [],
            "parameter_hints": diagnosis.get("parameter_hints") or [],
            "rule_version": diagnosis.get("rule_version"),
        },
        "linked_version": {
            "version_id": getattr(linked_version, "version_id", None),
            "parent_version_id": getattr(linked_version, "parent_version_id", None),
            "change_type": getattr(getattr(linked_version, "change_type", None), "value", getattr(linked_version, "change_type", None)),
            "summary": getattr(linked_version, "summary", None),
            "has_code_snapshot": bool(getattr(linked_version, "code_snapshot", None)),
            "has_parameters_snapshot": bool(getattr(linked_version, "parameters_snapshot", None)),
        },
    }

    messages = [
        {
            "role": "system",
            "content": (
                "You are a trading strategy diagnosis assistant. Return strict JSON only with keys "
                "summary, priorities, rationale, parameter_suggestions. "
                "Keep all suggestions advisory and grounded in the provided deterministic diagnosis."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(context, indent=2, sort_keys=True),
        },
    ]

    response = await dispatch.complete(
        messages=messages,
        model="openai/gpt-4o",
        temperature=0.2,
        max_tokens=1800,
    )

    payload = _extract_overlay_payload(response.content)
    return {
        "summary": str(payload.get("summary") or "").strip() or None,
        "priorities": _string_list(payload.get("priorities")),
        "rationale": _string_list(payload.get("rationale")),
        "parameter_suggestions": _object_list(payload.get("parameter_suggestions")),
        "ai_status": "ready",
    }


def _extract_overlay_payload(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("AI overlay did not return valid JSON")
        payload = json.loads(content[start:end + 1])

    if not isinstance(payload, dict):
        raise ValueError("AI overlay payload must be a JSON object")
    return payload


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _object_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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


__all__ = ["IntelligenceResult", "analyze_strategy", "analyze_metrics", "analyze_run_diagnosis_overlay"]
