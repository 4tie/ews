"""
Strategy Intelligence Service - AI-powered strategy analysis.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable

from app.ai.context_builder import build_run_intelligence_context, build_strategy_analysis_context
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

_TOOL_RUNTIME_INSTRUCTIONS = """
You may use the provided allowlisted tools when they materially improve grounded analysis.
Only claim an action happened if a tool call actually completed successfully.
After any tool use, still return the same strict JSON schema.
""".strip()


TimelineCallback = Callable[[dict[str, Any]], Any]
ToolAuthorize = Callable[[str, dict[str, Any]], tuple[bool, str | None]]
ToolExecutor = Callable[[str, dict[str, Any]], Any]


@dataclass
class ToolRuntime:
    tools: list[dict[str, Any]]
    authorize: ToolAuthorize
    execute: ToolExecutor
    max_rounds: int = 4


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
    tool_state: dict[str, Any] | None = None


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
    tool_runtime: ToolRuntime | None = None,
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
        tool_runtime=tool_runtime,
    )


async def analyze_metrics(
    metrics: dict[str, Any],
    context: str | None = None,
    timeline_callback: TimelineCallback | None = None,
    tool_runtime: ToolRuntime | None = None,
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
        tool_runtime=tool_runtime,
    )


async def analyze_run_diagnosis_overlay(
    strategy_name: str,
    diagnosis: dict[str, Any],
    summary_metrics: dict[str, Any] | None,
    linked_version: Any | None,
    *,
    run_id: str | None = None,
    trades: list[dict[str, Any]] | None = None,
    results_per_pair: list[dict[str, Any]] | None = None,
    request_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce an optional AI overlay for deterministic run diagnosis.

    Strict contract: only JSON, delta-based parameter suggestions, no free-form prose.
    """
    from app.services.results import strategy_intelligence_apply_service as apply_service

    version_id = getattr(linked_version, "version_id", None)
    parameter_snapshot = apply_service.resolve_parameters_snapshot(strategy_name, linked_version) or {}
    parameter_space = apply_service.resolve_parameter_space(strategy_name, linked_version) or []

    context = build_run_intelligence_context(
        strategy_name=strategy_name,
        run_id=run_id,
        version_id=str(version_id) if version_id else None,
        summary_metrics=summary_metrics or {},
        trades=trades or [],
        results_per_pair=results_per_pair or [],
        diagnosis=diagnosis or {},
        parameter_snapshot=parameter_snapshot,
        parameter_space=parameter_space,
        linked_version=linked_version,
    )

    json_instructions = """
Return strict JSON only.
Schema:
{
  \"summary\": string,
  \"suggestions\": [
    {
      \"key\": string,
      \"direction\": \"increase\" | \"decrease\",
      \"delta\": number,
      \"reason\": string,
      \"evidence\": [string],
      \"confidence\": number | null
    }
  ],
  \"confidence\": number | null
}
Rules:
- Delta-based suggestions only (no absolute values).
- Max 5 suggestions (hard).
- Evidence tokens must be drawn from diagnosis rules provided in the context.
Do not include markdown fences or extra prose outside the JSON object.
""".strip()

    dispatch = get_dispatch()
    system_prompt = "\n\n".join(
        section
        for section in (
            "You are a trading strategy diagnosis assistant. Stay grounded in the provided deterministic diagnosis.",
            "Return parameter delta suggestions only. Do not output absolute parameter maps.",
            json_instructions,
        )
        if section
    )

    try:
        response = await dispatch.complete_for_task(
            task_type="overlay",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
        )
    except Exception as exc:
        return {
            "summary": None,
            "suggestions": [],
            "parameter_suggestions": [],
            "confidence": None,
            "raw_text": str(exc),
            "provider": None,
            "model": None,
            "ai_status": "unavailable",
        }

    raw_text = str(response.content or "").strip()
    payload: dict[str, Any] | None = None
    try:
        parsed = json.loads(raw_text)
        payload = parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        payload = None

    if payload is None:
        return {
            "summary": None,
            "suggestions": [],
            "parameter_suggestions": [],
            "confidence": None,
            "raw_text": raw_text,
            "provider": response.provider,
            "model": response.model,
            "ai_status": "invalid",
        }

    summary = str(payload.get("summary") or "").strip() or None

    confidence = payload.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = None
    if confidence is not None:
        confidence = max(0.0, min(confidence, 1.0))

    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        suggestions = []

    normalized_suggestions: list[dict[str, Any]] = []
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        direction = str(item.get("direction") or "").strip().lower()
        delta = item.get("delta")
        reason = str(item.get("reason") or "").strip()
        evidence = item.get("evidence")
        item_conf = item.get("confidence")

        if direction not in {"increase", "decrease"}:
            continue
        try:
            delta = float(delta)
        except (TypeError, ValueError):
            continue
        if not key or not reason or delta == 0.0 or not math.isfinite(delta):
            continue
        if not isinstance(evidence, list) or not [token for token in evidence if str(token).strip()]:
            continue

        if item_conf is not None:
            try:
                item_conf = float(item_conf)
            except (TypeError, ValueError):
                item_conf = None
            if item_conf is not None:
                item_conf = max(0.0, min(item_conf, 1.0))

        normalized_suggestions.append(
            {
                "key": key,
                "direction": direction,
                "delta": delta,
                "reason": reason,
                "evidence": [str(token).strip() for token in evidence if str(token).strip()],
                "confidence": item_conf,
            }
        )

    if len(normalized_suggestions) > 5:
        return {
            "summary": summary,
            "suggestions": [],
            "parameter_suggestions": [],
            "confidence": confidence,
            "raw_text": raw_text,
            "provider": response.provider,
            "model": response.model,
            "ai_status": "invalid",
        }

    legacy = [
        {
            "name": item["key"],
            "value": f"{item['direction']} {item['delta']}",
            "reason": item.get("reason") or "",
        }
        for item in normalized_suggestions
    ]

    return {
        "summary": summary,
        "suggestions": normalized_suggestions,
        "parameter_suggestions": legacy,
        "confidence": confidence,
        "raw_text": raw_text,
        "provider": response.provider,
        "model": response.model,
        "ai_status": "ready",
    }

async def _run_structured_analysis(
    *,
    task_type: str,
    base_prompt: str,
    context: str,
    timeline_callback: TimelineCallback | None = None,
    tool_runtime: ToolRuntime | None = None,
) -> IntelligenceResult:
    dispatch = get_dispatch()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _build_analysis_system_prompt(base_prompt, tool_runtime=tool_runtime)},
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
        try:
            return await _run_streaming_ollama_analysis(
                dispatch=dispatch,
                policy=policy,
                messages=messages,
                task_type=task_type,
                timeline_callback=timeline_callback,
                tool_runtime=tool_runtime,
            )
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


async def _run_streaming_ollama_analysis(
    *,
    dispatch,
    policy,
    messages: list[dict[str, Any]],
    task_type: str,
    timeline_callback: TimelineCallback | None,
    tool_runtime: ToolRuntime | None,
) -> IntelligenceResult:
    client = dispatch.get_client("ollama")
    conversation = [dict(message) for message in messages]
    tool_state: dict[str, Any] = {}
    tool_rounds = 0

    while True:
        chunks: list[str] = []
        pending_tool_calls: list[dict[str, Any]] = []
        seen_tool_call_ids: set[str] = set()
        tool_event_sent = False

        async for payload in client.stream_chat(
            messages=conversation,
            model=policy.model,
            temperature=policy.temperature,
            max_tokens=policy.max_tokens,
            tools=tool_runtime.tools if tool_runtime else None,
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

            tool_calls = _normalize_tool_calls(message.get("tool_calls"))
            if tool_calls and not tool_event_sent:
                tool_event_sent = True
                await _emit_timeline(
                    timeline_callback,
                    {
                        "type": "tool_call_detected",
                        "provider": policy.provider,
                        "model": policy.model,
                        "detail": "Model requested an allowlisted tool call.",
                    },
                )
            for tool_call in tool_calls:
                tool_call_id = str(tool_call.get("id") or "").strip()
                if not tool_call_id or tool_call_id in seen_tool_call_ids:
                    continue
                seen_tool_call_ids.add(tool_call_id)
                pending_tool_calls.append(tool_call)

        assistant_text = "".join(chunks)
        if not pending_tool_calls:
            response = ModelResponse(
                content=assistant_text,
                model=policy.model,
                provider=policy.provider,
                task_type=task_type,
            )
            result = _response_to_intelligence_result(response)
            result.tool_state = tool_state or None
            return result

        if tool_runtime is None:
            response = ModelResponse(
                content=assistant_text,
                model=policy.model,
                provider=policy.provider,
                task_type=task_type,
                tool_calls=pending_tool_calls,
            )
            result = _response_to_intelligence_result(response)
            result.tool_state = tool_state or None
            return result

        if tool_rounds >= max(int(tool_runtime.max_rounds or 0), 1):
            raise RuntimeError("Ollama tool loop exceeded the maximum number of rounds")

        conversation.append(
            {
                "role": "assistant",
                "content": assistant_text,
                "tool_calls": pending_tool_calls,
            }
        )
        for tool_call in pending_tool_calls:
            tool_result = await _execute_tool_call(
                tool_call=tool_call,
                tool_runtime=tool_runtime,
                timeline_callback=timeline_callback,
                provider=policy.provider,
                model=policy.model,
            )
            tool_state.update(tool_result.pop("tool_state", {}) or {})
            conversation.append(
                {
                    "role": "tool",
                    "name": str(tool_result.get("tool_name") or "tool"),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )
        tool_rounds += 1


async def _execute_tool_call(
    *,
    tool_call: dict[str, Any],
    tool_runtime: ToolRuntime,
    timeline_callback: TimelineCallback | None,
    provider: str,
    model: str,
) -> dict[str, Any]:
    tool_name, arguments = _extract_tool_call(tool_call)
    tool_call_id = str(tool_call.get("id") or f"tool:{tool_name or 'unknown'}")

    await _emit_timeline(
        timeline_callback,
        {
            "type": "tool_call_requested",
            "provider": provider,
            "model": model,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
        },
    )

    allowed, denial_reason = tool_runtime.authorize(tool_name, arguments)
    if not allowed:
        blocked_result = {
            "ok": False,
            "blocked": True,
            "tool_name": tool_name,
            "arguments": arguments,
            "message": denial_reason or "Tool call is not allowed in this session.",
        }
        await _emit_timeline(
            timeline_callback,
            {
                "type": "tool_call_failed",
                "provider": provider,
                "model": model,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "message": blocked_result["message"],
                "blocked": True,
            },
        )
        return blocked_result

    await _emit_timeline(
        timeline_callback,
        {
            "type": "tool_call_started",
            "provider": provider,
            "model": model,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
        },
    )

    try:
        execution_result = tool_runtime.execute(tool_name, arguments)
        if hasattr(execution_result, "__await__"):
            execution_result = await execution_result
        normalized = execution_result if isinstance(execution_result, dict) else {"ok": True, "result": execution_result}
    except Exception as exc:
        failure_result = {
            "ok": False,
            "tool_name": tool_name,
            "arguments": arguments,
            "message": str(exc),
        }
        await _emit_timeline(
            timeline_callback,
            {
                "type": "tool_call_failed",
                "provider": provider,
                "model": model,
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "message": str(exc),
            },
        )
        return failure_result

    ok = bool(normalized.get("ok", True))
    event_type = "tool_call_completed" if ok else "tool_call_failed"
    await _emit_timeline(
        timeline_callback,
        {
            "type": event_type,
            "provider": provider,
            "model": model,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "message": str(normalized.get("message") or normalized.get("summary") or "Tool call completed."),
            "blocked": bool(normalized.get("blocked", False)),
        },
    )
    normalized.setdefault("tool_name", tool_name)
    normalized.setdefault("arguments", arguments)
    return normalized


def _build_analysis_system_prompt(base_prompt: str, *, tool_runtime: ToolRuntime | None = None) -> str:
    sections = [base_prompt]
    if tool_runtime and tool_runtime.tools:
        sections.append(_TOOL_RUNTIME_INSTRUCTIONS)
    sections.append(_ANALYSIS_JSON_INSTRUCTIONS)
    return "\n\n".join(section for section in sections if section)


def _extract_tool_call(tool_call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function_payload = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
    name = str(function_payload.get("name") or "").strip()
    arguments = function_payload.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {}
    return name, arguments


def _normalize_tool_calls(tool_calls: Any) -> list[dict[str, Any]]:
    if not isinstance(tool_calls, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, tool_call in enumerate(tool_calls):
        if not isinstance(tool_call, dict):
            continue
        name, arguments = _extract_tool_call(tool_call)
        normalized.append(
            {
                "id": str(tool_call.get("id") or f"tool-call-{index + 1}"),
                "type": str(tool_call.get("type") or "function"),
                "function": {
                    "name": name,
                    "arguments": arguments,
                },
            }
        )
    return normalized


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


__all__ = [
    "ToolRuntime",
    "IntelligenceResult",
    "analyze_strategy",
    "analyze_metrics",
    "analyze_run_diagnosis_overlay",
]

