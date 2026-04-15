"""
AI Context Builder - Builds context for AI requests from strategy data.
"""
from __future__ import annotations

import json
import re
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
_RISK_PARAMETER_SPECS: dict[str, dict[str, Any]] = {
    "stoploss": {"type": "float", "min": -1.0, "max": 0.0},
    "trailing_stop": {"type": "bool"},
    "trailing_stop_positive": {"type": "float", "min": 0.0, "max": 1.0},
    "trailing_stop_positive_offset": {"type": "float", "min": 0.0, "max": 2.0},
    "trailing_only_offset_is_reached": {"type": "bool"},
    "minimal_roi": {"type": "roi_dict"},
}


def build_run_intelligence_package(
    *,
    strategy_name: str,
    run_id: str | None,
    version_id: str | None,
    summary_metrics: dict[str, Any] | None,
    trades: list[dict[str, Any]] | None,
    results_per_pair: list[dict[str, Any]] | None,
    diagnosis: dict[str, Any] | None,
    parameter_snapshot: dict[str, Any] | None,
    parameter_space: list[dict[str, Any]] | None,
    linked_version: Any | None = None,
) -> dict[str, Any]:
    trades = trades if isinstance(trades, list) else []
    results_per_pair = results_per_pair if isinstance(results_per_pair, list) else []
    diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
    parameter_snapshot = parameter_snapshot if isinstance(parameter_snapshot, dict) else {}
    parameter_space = parameter_space if isinstance(parameter_space, list) else []

    trade_start, trade_end = _extract_trade_range(trades)
    run_summary = {
        "strategy": strategy_name,
        "run_id": run_id,
        "version_id": version_id,
        "trade_start": trade_start,
        "trade_end": trade_end,
        "summary_metrics": summary_metrics or {},
    }

    safe_keys = sorted({str(item.get("key")) for item in parameter_space if isinstance(item, dict) and item.get("key")})
    for key in _RISK_PARAMETER_SPECS:
        if key not in safe_keys:
            safe_keys.append(key)

    package = {
        "schema_version": "run-intelligence-v1",
        "run_summary": run_summary,
        "trades": _trim_trades(trades),
        "results_per_pair": _trim_results_per_pair(results_per_pair),
        "diagnosis": diagnosis,
        "ranked_issues": _augment_ranked_issues(diagnosis.get("ranked_issues") or []),
        "parameter_snapshot": parameter_snapshot,
        "parameter_space": parameter_space,
        "safe_keys": safe_keys,
        "version_context": _serialize_linked_version(linked_version),
        "risk_parameter_specs": _RISK_PARAMETER_SPECS,
    }
    return {key: value for key, value in package.items() if value not in (None, {}, [])}


def build_run_intelligence_context(**kwargs: Any) -> str:
    return json.dumps(build_run_intelligence_package(**kwargs), indent=2, sort_keys=True, default=str)


def _extract_trade_range(trades: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    entries: list[dict[str, Any]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        open_date = trade.get("open_date")
        close_date = trade.get("close_date")
        open_ts = _trade_timestamp(open_date)
        close_ts = _trade_timestamp(close_date)
        if open_ts is None and close_ts is None:
            continue
        entries.append(
            {
                "open": open_date,
                "open_ts": open_ts if open_ts is not None else close_ts,
                "close": close_date,
                "close_ts": close_ts if close_ts is not None else open_ts,
            }
        )
    if not entries:
        return None, None
    start = min(entries, key=lambda item: item["open_ts"])
    end = max(entries, key=lambda item: item["close_ts"])
    return start.get("open") or start.get("close"), end.get("close") or end.get("open")


def _trade_timestamp(value: Any) -> float | None:
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _trim_trades(trades: list[dict[str, Any]], *, top_n: int = 8, bottom_n: int = 8) -> dict[str, Any]:
    def _profit_pct(item: dict[str, Any]) -> float | None:
        value = item.get("profit_pct")
        if value is None:
            value = item.get("profit_ratio")
        try:
            num = float(value)
        except (TypeError, ValueError):
            return None
        return num

    scored = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        profit = _profit_pct(trade)
        if profit is None:
            continue
        scored.append((profit, trade))

    scored.sort(key=lambda item: item[0], reverse=True)
    winners = [trade for _, trade in scored[:top_n]]
    losers = [trade for _, trade in scored[-bottom_n:]][::-1] if bottom_n else []

    def _lite(trade: dict[str, Any]) -> dict[str, Any]:
        return {
            "pair": trade.get("pair"),
            "profit_pct": trade.get("profit_pct"),
            "profit_abs": trade.get("profit_abs"),
            "open_date": trade.get("open_date"),
            "close_date": trade.get("close_date"),
            "duration": trade.get("duration"),
            "exit_reason": trade.get("exit_reason") or trade.get("sell_reason"),
        }

    return {
        "total_trades": len([t for t in trades if isinstance(t, dict)]),
        "top_winners": [_lite(item) for item in winners],
        "top_losers": [_lite(item) for item in losers],
    }


def _trim_results_per_pair(rows: list[dict[str, Any]], *, top_n: int = 8, bottom_n: int = 8) -> dict[str, Any]:
    total_row = None
    scored: list[tuple[float, dict[str, Any]]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or row.get("pair") or "")
        if key == "TOTAL":
            total_row = row
            continue
        profit_value = row.get("profit_total_pct")
        try:
            profit = float(profit_value)
        except (TypeError, ValueError):
            continue
        scored.append((profit, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    winners = [row for _, row in scored[:top_n]]
    losers = [row for _, row in scored[-bottom_n:]][::-1] if bottom_n else []

    def _lite(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "pair": row.get("key") or row.get("pair"),
            "profit_total_pct": row.get("profit_total_pct"),
            "profit_total_abs": row.get("profit_total_abs"),
            "trades": row.get("trades"),
            "winrate": row.get("winrate"),
            "avg_profit_pct": row.get("avg_profit_pct"),
            "avg_duration": row.get("avg_duration"),
        }

    return {
        "total": _lite(total_row) if isinstance(total_row, dict) else None,
        "top_winners": [_lite(item) for item in winners],
        "top_losers": [_lite(item) for item in losers],
    }


def _augment_ranked_issues(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    augmented: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("rule") or "").strip()
        augmented.append({**item, "rule_tokens": _rule_tokens(rule)})
    return augmented


_RULE_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _rule_tokens(rule: str) -> list[str]:
    normalized = str(rule or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return []
    matches = _RULE_TOKEN_RE.findall(normalized)
    tokens = [token for token in matches if token.strip("_")]
    if normalized not in tokens:
        tokens.insert(0, normalized)
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return unique


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
    "build_run_intelligence_package",
    "build_run_intelligence_context",
    "build_analysis_context",
]

