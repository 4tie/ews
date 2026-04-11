"""
Strategy Intelligence Service - AI-powered strategy analysis.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.ai.context_builder import build_strategy_analysis_context
from app.ai.models import ModelResponse, get_dispatch
from app.ai.prompts.trading import (
    ANALYST_SYSTEM_PROMPT,
    CODE_AWARE_ADVISOR_SYSTEM_PROMPT,
)


_ANALYSIS_JSON_INSTRUCTIONS = """
Return strict JSON only.
Schema:
{
  "summary": string,
  "diagnosis": {"problem": string, "cause": string, "weaknesses": [string]},
  "priorities": [string],
  "rationale": [string],
  "parameter_suggestions": [{"name": string, "value": any, "reason": string}],
  "code_change_summary": string | null,
  "recommended_next_step": string | null,
  "confidence": number | null
}
Do not include markdown fences or extra prose outside the JSON object.
""".strip()


TimelineCallback = Callable[[dict[str, Any]], Any]


@dataclass
class IntelligenceResult:
    analysis: str
    recommendations: list[str]
    parameters: dict[str, Any] | None
    code_suggestions: str | None
    is_applicable: bool
    analysis_payload: dict[str, Any] | None = None
    provider: str | None = None
    model: str | None = None
    raw_text: str | None = None


async def _emit_timeline(callback: TimelineCallback | None, payload: dict[str, Any]) -> None:
    if callback is None:
        return
    maybe_awaitable = callback(payload)
    if hasattr(maybe_awaitable, "__await__"):
        await maybe_awaitable


async def analyze_strategy(
    strategy_name: str,
    strategy_code: str,
    backtest_results: dict[str, Any],
    user_question: str | None = None,
    timeline_callback: TimelineCallback | None = None,
) -> IntelligenceResult:
    """Analyze strategy and provide AI-powered insights."""
    context = build_strategy_analysis_context(
        strategy_name=strategy_name,
        strategy_code=strategy_code,
        summary_metrics=backtest_results,
        backtest_results=backtest_results,
        user_question=user_question or "Provide general analysis and recommendations",
    )
    return await _run_structured_analysis(
        task_type="analysis",
        base_prompt=CODE_AWARE_ADVISOR_SYSTEM_PROMPT,
        context=context,
        timeline_callback=timeline_callback,
    )


async def analyze_metrics(
    metrics: dict[str, Any],
    context: str | None = None,
    timeline_callback: TimelineCallback | None = None,
) -> IntelligenceResult:
    """Analyze trading metrics and provide insights."""
    analysis_context = build_strategy_analysis_context(
        strategy_name="metrics-only",
        summary_metrics=metrics,
        backtest_results=metrics,
        user_question=context or "General analysis",
    )
    return await _run_structured_analysis(
        task_type="analysis",
        base_prompt=ANALYST_SYSTEM_PROMPT,
        context=analysis_context,
        timeline_callback=timeline_callback,
    )


async def analyze_run_diagnosis_overlay(
    strategy_name: str,
    diagnosis: dict[str, Any],
    summary_metrics: dict[str, Any] | None,
    linked_version: Any | None,
) -> dict[str, Any]:
    """Produce an optional AI overlay for deterministic run diagnosis."""
    context = build_strategy_analysis_context(
        strategy_name=strategy_name,
        summary_metrics=summary_metrics or {},
        diagnosis=diagnosis,
        linked_version=linked_version,
        user_question="Explain why this run is weak and suggest the safest next versioned move.",
    )
    result = await _run_structured_analysis(
        task_type="overlay",
        base_prompt=(
            "You are a trading strategy diagnosis assistant. Stay grounded in the provided deterministic diagnosis. "
            "Keep suggestions advisory only and suitable for versioned candidate creation."
        ),
        context=context,
    )
    payload = result.analysis_payload or _fallback_analysis_envelope(result.raw_text or "")
    return {
        "summary": payload.get("summary") or None,
        "diagnosis": payload.get("diagnosis") or {},
        "priorities": _string_list(payload.get("priorities")),
        "rationale": _string_list(payload.get("rationale")),
        "parameter_suggestions": _normalize_parameter_suggestions(payload.get("parameter_suggestions")),
        "code_change_summary": payload.get("code_change_summary") or None,
        "recommended_next_step": payload.get("recommended_next_step") or None,
        "confidence": payload.get("confidence"),
        "raw_text": payload.get("raw_text") or result.raw_text,
        "provider": result.provider,
        "model": result.model,
        "ai_status": "ready",
    }


async def _run_structured_analysis(
    *,
    task_type: str,
    base_prompt: str,
    context: str,
    timeline_callback: TimelineCallback | None = None,
) -> IntelligenceResult:
    dispatch = get_dispatch()
    messages = [
        {"role": "system", "content": _build_analysis_system_prompt(base_prompt)},
        {"role": "user", "content": context},
    ]
    policy = dispatch.get_task_policy(task_type)

    if timeline_callback is not None:
        await _emit_timeline(
            timeline_callback,
            {
                "type": "route_selected",
                "provider": policy.provider,
                "model": policy.model,
            },
        )

    if timeline_callback is not None and policy.provider == "ollama" and policy.stream_preferred:
        client = dispatch.get_client("ollama")
        if hasattr(client, "stream_chat"):
            try:
                chunks: list[str] = []
                tool_event_sent = False
                async for payload in client.stream_chat(
                    messages=messages,
                    model=policy.model,
                    temperature=policy.temperature,
                    max_tokens=policy.max_tokens,
                ):
                    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
                    delta = str(message.get("content") or "")
                    if delta:
                        chunks.append(delta)
                        await _emit_timeline(
                            timeline_callback,
                            {
                                "type": "stream_delta",
                                "provider": policy.provider,
                                "model": policy.model,
                                "delta": delta,
                            },
                        )
                    if message.get("tool_calls") and not tool_event_sent:
                        tool_event_sent = True
                        await _emit_timeline(
                            timeline_callback,
                            {
                                "type": "tool_call_detected",
                                "provider": policy.provider,
                                "model": policy.model,
                                "detail": "Model advertised a tool call. Tool execution remains disabled in this app.",
                            },
                        )
                response = ModelResponse(
                    content="".join(chunks),
                    model=policy.model,
                    provider=policy.provider,
                    task_type=task_type,
                )
                return _response_to_intelligence_result(response)
            except Exception as exc:
                if policy.fallback_provider and policy.fallback_model:
                    await _emit_timeline(
                        timeline_callback,
                        {
                            "type": "route_selected",
                            "provider": policy.fallback_provider,
                            "model": policy.fallback_model,
                            "message": f"Primary route failed, falling back: {exc}",
                        },
                    )
                    response = await dispatch.complete(
                        messages=messages,
                        provider=policy.fallback_provider,
                        model=policy.fallback_model,
                        temperature=policy.temperature,
                        max_tokens=policy.max_tokens,
                    )
                    response.task_type = task_type
                    return _response_to_intelligence_result(response)
                raise

    response = await dispatch.complete_for_task(
        task_type=task_type,
        messages=messages,
    )
    return _response_to_intelligence_result(response)


def _build_analysis_system_prompt(base_prompt: str) -> str:
    return f"{base_prompt}\n\n{_ANALYSIS_JSON_INSTRUCTIONS}"


def _response_to_intelligence_result(response: ModelResponse) -> IntelligenceResult:
    payload = _parse_analysis_envelope(response.content)
    recommendations = _extract_recommendations(payload)
    parameters = _extract_parameter_map(payload.get("parameter_suggestions"))
    code_summary = str(payload.get("code_change_summary") or "").strip() or None
    summary = str(payload.get("summary") or "").strip() or _fallback_summary(response.content)
    return IntelligenceResult(
        analysis=summary,
        recommendations=recommendations,
        parameters=parameters,
        code_suggestions=code_summary,
        is_applicable=bool(summary or recommendations or parameters or code_summary),
        analysis_payload=payload,
        provider=response.provider,
        model=response.model,
        raw_text=response.content,
    )


def _parse_analysis_envelope(content: str) -> dict[str, Any]:
    raw_text = str(content or "").strip()
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = _extract_json_object(raw_text)
    if not isinstance(payload, dict):
        return _fallback_analysis_envelope(raw_text)
    return _normalize_analysis_envelope(payload, raw_text)


def _extract_json_object(content: str) -> dict[str, Any]:
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return _fallback_analysis_envelope(content)
    try:
        payload = json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        return _fallback_analysis_envelope(content)
    return payload if isinstance(payload, dict) else _fallback_analysis_envelope(content)


def _normalize_analysis_envelope(payload: dict[str, Any], raw_text: str) -> dict[str, Any]:
    diagnosis = payload.get("diagnosis")
    if isinstance(diagnosis, str):
        diagnosis = {"problem": diagnosis}
    if not isinstance(diagnosis, dict):
        diagnosis = {}

    confidence = payload.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = None
    if confidence is not None:
        confidence = max(0.0, min(confidence, 1.0))

    return {
        "summary": str(payload.get("summary") or "").strip() or _fallback_summary(raw_text),
        "diagnosis": diagnosis,
        "priorities": _string_list(payload.get("priorities")),
        "rationale": _string_list(payload.get("rationale")),
        "parameter_suggestions": _normalize_parameter_suggestions(payload.get("parameter_suggestions")),
        "code_change_summary": str(payload.get("code_change_summary") or "").strip() or None,
        "recommended_next_step": str(payload.get("recommended_next_step") or "").strip() or None,
        "confidence": confidence,
        "raw_text": raw_text,
    }


def _fallback_analysis_envelope(raw_text: str) -> dict[str, Any]:
    return {
        "summary": _fallback_summary(raw_text),
        "diagnosis": {"problem": "Structured analysis could not be parsed.", "cause": None, "weaknesses": []},
        "priorities": [],
        "rationale": [],
        "parameter_suggestions": [],
        "code_change_summary": None,
        "recommended_next_step": None,
        "confidence": None,
        "raw_text": raw_text,
    }


def _fallback_summary(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return "AI did not return analysis text."
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) <= 280:
        return first_line
    return f"{first_line[:277]}..."


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_parameter_suggestions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    suggestions: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("parameter") or item.get("key") or "").strip()
        reason = str(item.get("reason") or item.get("rationale") or item.get("summary") or "").strip()
        value_payload = item.get("value")
        if not name and value_payload in (None, "") and not reason:
            continue
        suggestions.append({
            "name": name or "suggestion",
            "value": value_payload,
            "reason": reason,
        })
    return suggestions


def _extract_parameter_map(value: Any) -> dict[str, Any] | None:
    suggestions = _normalize_parameter_suggestions(value)
    params = {
        item["name"]: item["value"]
        for item in suggestions
        if item.get("name") and item.get("value") is not None
    }
    return params or None


def _extract_recommendations(payload: dict[str, Any]) -> list[str]:
    priorities = _string_list(payload.get("priorities"))
    if priorities:
        return priorities
    rationale = _string_list(payload.get("rationale"))
    if rationale:
        return rationale
    params = _normalize_parameter_suggestions(payload.get("parameter_suggestions"))
    return [
        f"{item['name']}: {item['value']}" if item.get("value") is not None else item["name"]
        for item in params
    ]


__all__ = ["IntelligenceResult", "analyze_strategy", "analyze_metrics", "analyze_run_diagnosis_overlay"]

