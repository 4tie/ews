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
    "build_analysis_context",
]