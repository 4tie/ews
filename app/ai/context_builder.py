"""
AI Context Builder - Builds context for AI requests from strategy data.
"""
from __future__ import annotations

import json
from typing import Any


def build_strategy_context(
    strategy_name: str,
    code: str | None = None,
    backtest_results: dict[str, Any] | None = None,
    optimizer_results: dict[str, Any] | None = None,
) -> str:
    """Build context string from strategy data."""
    parts = []

    if strategy_name:
        parts.append(f"Strategy: {strategy_name}")

    if code:
        parts.append(f"\n--- Strategy Code ---\n{code[:2000]}")

    if backtest_results:
        results_summary = _format_backtest_summary(backtest_results)
        parts.append(f"\n--- Backtest Results ---\n{results_summary}")

    if optimizer_results:
        opt_summary = _format_optimizer_summary(optimizer_results)
        parts.append(f"\n--- Optimizer Results ---\n{opt_summary}")

    return "\n".join(parts)


def build_strategy_analysis_payload(
    *,
    strategy_name: str,
    strategy_code: str | None = None,
    summary_metrics: dict[str, Any] | None = None,
    diagnosis: dict[str, Any] | None = None,
    request_snapshot: dict[str, Any] | None = None,
    linked_version: Any | None = None,
    backtest_results: dict[str, Any] | None = None,
    optimizer_results: dict[str, Any] | None = None,
    user_question: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "strategy_name": strategy_name,
        "user_question": str(user_question or "").strip() or None,
        "summary_metrics": summary_metrics or backtest_results or {},
        "diagnosis": diagnosis or {},
        "request_snapshot": request_snapshot or {},
        "linked_version": _serialize_linked_version(linked_version),
    }

    if strategy_code:
        payload["strategy_code"] = strategy_code[:6000]
    if backtest_results and backtest_results is not payload["summary_metrics"]:
        payload["backtest_results"] = backtest_results
    if optimizer_results:
        payload["optimizer_results"] = optimizer_results

    return {key: value for key, value in payload.items() if value not in (None, {}, [])}


def build_strategy_analysis_context(**kwargs: Any) -> str:
    return json.dumps(build_strategy_analysis_payload(**kwargs), indent=2, sort_keys=True, default=str)


def _serialize_linked_version(linked_version: Any | None) -> dict[str, Any]:
    if linked_version is None:
        return {}
    change_type = getattr(linked_version, "change_type", None)
    status = getattr(linked_version, "status", None)
    return {
        "version_id": getattr(linked_version, "version_id", None),
        "parent_version_id": getattr(linked_version, "parent_version_id", None),
        "change_type": getattr(change_type, "value", change_type),
        "summary": getattr(linked_version, "summary", None),
        "status": getattr(status, "value", status),
        "has_code_snapshot": bool(getattr(linked_version, "code_snapshot", None)),
        "has_parameters_snapshot": bool(getattr(linked_version, "parameters_snapshot", None)),
    }


def _format_backtest_summary(results: dict[str, Any]) -> str:
    """Format backtest results as context string."""
    key_metrics = [
        "total_profit",
        "profit_ratio",
        "win_rate",
        "max_drawdown",
        "drawdown_end",
        "profit_factor",
        "sharpe",
        "sortino",
        "total_trades",
    ]

    lines = []
    for metric in key_metrics:
        if metric in results:
            value = results[metric]
            lines.append(f"  {metric}: {value}")

    return "\n".join(lines) if lines else json.dumps(results, indent=2)


def _format_optimizer_results(results: dict[str, Any]) -> str:
    """Format optimizer results as context string."""
    lines = []

    if "best_params" in results:
        lines.append("Best Parameters:")
        for k, v in results["best_params"].items():
            lines.append(f"  {k}: {v}")

    if "best_metrics" in results:
        lines.append("\nBest Metrics:")
        for k, v in results["best_metrics"].items():
            lines.append(f"  {k}: {v}")

    return "\n".join(lines) if lines else json.dumps(results, indent=2)


def _format_optimizer_summary(results: dict[str, Any]) -> str:
    return _format_optimizer_results(results)


def build_analysis_context(
    metric_name: str,
    value: float,
    benchmark: float | None = None,
    comparison: dict[str, Any] | None = None,
) -> str:
    """Build context for metric analysis."""
    parts = [f"{metric_name}: {value}"]

    if benchmark:
        parts.append(f"Benchmark: {benchmark}")
        diff = value - benchmark
        parts.append(f"Difference: {diff:+.2f}")

    if comparison:
        parts.append("Comparison:")
        for k, v in comparison.items():
            parts.append(f"  {k}: {v}")

    return "\n".join(parts)


__all__ = [
    "build_strategy_context",
    "build_strategy_analysis_payload",
    "build_strategy_analysis_context",
    "build_analysis_context",
]
