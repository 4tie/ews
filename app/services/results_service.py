import glob
import json
import os
from typing import Any, Optional

from app.engines.resolver import result_parser_from_id
from app.models.backtest_models import BacktestRunRecord
from app.freqtrade.paths import strategy_results_dir, user_data_results_dir
from app.services.mutation_service import mutation_service
from app.services.results.diagnosis_service import diagnosis_service
from app.utils.json_io import read_json, write_json


class ResultsService:
    def _run_result_paths(self, strategy: str, run_id: str) -> dict:
        base = strategy_results_dir(strategy)
        os.makedirs(base, exist_ok=True)
        return {
            "result_path": os.path.join(base, f"{run_id}.result.json"),
            "summary_path": os.path.join(base, f"{run_id}.summary.json"),
            "latest_summary_path": os.path.join(base, "latest.summary.json"),
        }

    def _is_object(self, value: Any) -> bool:
        return isinstance(value, dict)

    def _to_number(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number else None

    def _first_number(self, *values: Any) -> float | None:
        for value in values:
            number = self._to_number(value)
            if number is not None:
                return number
        return None

    def _resolve_strategy_block(self, summary: dict | None, strategy: str | None = None) -> tuple[str | None, dict | None]:
        if not isinstance(summary, dict):
            return None, None

        if strategy and isinstance(summary.get(strategy), dict):
            return strategy, summary[strategy]

        for key, value in summary.items():
            if key == "strategy_comparison":
                continue
            if isinstance(value, dict):
                return key, value

        return strategy, None

    def _find_total_row(self, strategy_block: dict | None) -> dict | None:
        rows = strategy_block.get("results_per_pair") if isinstance(strategy_block, dict) else None
        if not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("key") or row.get("pair") or "") == "TOTAL":
                return row
        return None

    def _extract_trade_range(self, trades: list | None) -> tuple[str | None, str | None]:
        if not isinstance(trades, list) or not trades:
            return None, None

        entries = []
        for trade in trades:
            if not isinstance(trade, dict):
                continue
            open_date = trade.get("open_date")
            close_date = trade.get("close_date")
            open_ts = self._trade_timestamp(open_date)
            close_ts = self._trade_timestamp(close_date)
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

    def _trade_timestamp(self, value: Any) -> float | None:
        if not value:
            return None
        try:
            from datetime import datetime

            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    def _assert_within_strategy_results(self, strategy: str, path: str) -> str:
        base = os.path.normcase(os.path.realpath(strategy_results_dir(strategy)))
        target = os.path.normcase(os.path.realpath(path))
        try:
            common = os.path.commonpath([base, target])
        except ValueError as exc:
            raise ValueError(f"summary path is outside strategy results directory: {path}") from exc
        if common != base:
            raise ValueError(f"summary path is outside strategy results directory: {path}")
        return os.path.realpath(path)

    def _read_json_strict(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("summary payload must be a JSON object")
        return payload

    def load_run_summary_state(self, run_record: BacktestRunRecord) -> dict[str, Any]:
        if not run_record.summary_path:
            return {"state": "missing", "summary": None, "error": None}

        try:
            summary_path = self._assert_within_strategy_results(run_record.strategy, run_record.summary_path)
        except ValueError as exc:
            return {
                "state": "load_failed",
                "summary": None,
                "error": f"summary_load_failed: {exc}",
            }

        if not os.path.isfile(summary_path):
            return {"state": "missing", "summary": None, "error": None}

        try:
            summary = self._read_json_strict(summary_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return {
                "state": "load_failed",
                "summary": None,
                "error": f"summary_load_failed: {exc}",
            }

        return {"state": "ready", "summary": summary, "error": None}

    def _load_run_summary(self, run_record: BacktestRunRecord) -> Optional[dict]:
        state = self.load_run_summary_state(run_record)
        return state.get("summary") if state.get("state") == "ready" else None

    def extract_run_summary_block(self, summary: dict | None, strategy: str | None = None) -> dict | None:
        _, block = self._resolve_strategy_block(summary, strategy)
        return block if isinstance(block, dict) else None

    def _normalize_summary_metrics(self, summary: dict | None, strategy: str | None = None) -> dict | None:
        strategy_name, block = self._resolve_strategy_block(summary, strategy)
        if not isinstance(block, dict):
            return None

        total = self._find_total_row(block)
        rows = block.get("results_per_pair") if isinstance(block.get("results_per_pair"), list) else []
        trades = block.get("trades") if isinstance(block.get("trades"), list) else []

        profit_total_pct = self._to_number(total.get("profit_total_pct") if total else None)
        if profit_total_pct is None:
            profit_total_pct = self._to_number(block.get("profit_total_pct"))
        if profit_total_pct is None:
            ratio = self._to_number(total.get("profit_total") if total else None)
            if ratio is None:
                ratio = self._to_number(block.get("profit_total"))
            profit_total_pct = ratio * 100 if ratio is not None else None

        profit_total_abs = self._to_number(total.get("profit_total_abs") if total else None)
        if profit_total_abs is None:
            profit_total_abs = self._to_number(block.get("profit_total_abs"))

        win_rate = None
        win_rate_ratio = self._to_number(total.get("winrate") if total else None)
        if win_rate_ratio is None:
            win_rate_ratio = self._to_number(block.get("winrate"))
        if win_rate_ratio is not None:
            win_rate = win_rate_ratio * 100
        else:
            wins = self._to_number(total.get("wins") if total else None)
            if wins is None:
                wins = self._to_number(block.get("wins"))
            total_trades = self._to_number(total.get("trades") if total else None)
            if total_trades is None:
                total_trades = self._to_number(block.get("total_trades"))
            if wins is not None and total_trades not in (None, 0):
                win_rate = (wins / total_trades) * 100

        max_drawdown_pct = None
        drawdown_account = self._to_number(total.get("max_drawdown_account") if total else None)
        if drawdown_account is None:
            drawdown_account = self._to_number(block.get("max_drawdown_account"))
        if drawdown_account is not None:
            max_drawdown_pct = abs(drawdown_account * 100)
        else:
            drawdown_pct = self._to_number(block.get("max_drawdown_pct"))
            if drawdown_pct is not None:
                max_drawdown_pct = abs(drawdown_pct)
            else:
                drawdown_ratio = self._to_number(block.get("max_drawdown"))
                if drawdown_ratio is not None:
                    max_drawdown_pct = abs(drawdown_ratio * 100)

        max_drawdown_abs = self._to_number(total.get("max_drawdown_abs") if total else None)
        if max_drawdown_abs is None:
            max_drawdown_abs = self._to_number(block.get("max_drawdown_abs"))

        total_trades = self._to_number(total.get("trades") if total else None)
        if total_trades is None:
            total_trades = self._to_number(block.get("total_trades"))

        pair_count = len(
            [
                row
                for row in rows
                if isinstance(row, dict) and str(row.get("key") or row.get("pair") or "") != "TOTAL"
            ]
        )

        trade_start, trade_end = self._extract_trade_range(trades)

        return {
            "strategy": block.get("strategy_name") or strategy_name or strategy,
            "timeframe": block.get("timeframe"),
            "timerange": block.get("timerange"),
            "stake_currency": block.get("stake_currency"),
            "profit_total_pct": profit_total_pct,
            "profit_total_abs": profit_total_abs,
            "win_rate": win_rate,
            "total_trades": int(total_trades) if total_trades is not None else None,
            "pair_count": pair_count,
            "max_drawdown_pct": max_drawdown_pct,
            "max_drawdown_abs": max_drawdown_abs,
            "sharpe": self._first_number(total.get("sharpe") if total else None, block.get("sharpe"), block.get("sharpe_ratio")),
            "sortino": self._first_number(total.get("sortino") if total else None, block.get("sortino"), block.get("sortino_ratio")),
            "calmar": self._first_number(total.get("calmar") if total else None, block.get("calmar")),
            "avg_duration": (total or {}).get("duration_avg") or block.get("holding_avg"),
            "trade_start": trade_start,
            "trade_end": trade_end,
        }

    def summarize_backtest_run(self, run_record: BacktestRunRecord, progress: dict[str, Any] | None = None) -> dict:
        payload = run_record.model_dump(mode="json")
        summary_metrics = None
        summary_state = {"state": "missing", "summary": None, "error": None}
        if getattr(run_record, "engine", "freqtrade") == "freqtrade":
            summary_state = self.load_run_summary_state(run_record)
            if summary_state.get("state") == "ready":
                summary_metrics = self._normalize_summary_metrics(summary_state.get("summary"), run_record.strategy)
        payload["summary_available"] = summary_state.get("state") == "ready"
        payload["summary_metrics"] = summary_metrics
        payload["progress"] = progress
        return payload

    def _build_compare_run_context(self, run_record: BacktestRunRecord) -> dict[str, Any]:
        summary_state = {"state": "missing", "summary": None, "error": None}
        summary = None
        summary_block = None
        summary_metrics = None
        if getattr(run_record, "engine", "freqtrade") == "freqtrade":
            summary_state = self.load_run_summary_state(run_record)
            if summary_state.get("state") == "ready":
                summary = summary_state.get("summary")
                summary_block = self.extract_run_summary_block(summary, run_record.strategy)
                summary_metrics = self._normalize_summary_metrics(summary, run_record.strategy)

        view = run_record.model_dump(mode="json")
        view["summary_available"] = summary_state.get("state") == "ready"
        view["summary_metrics"] = summary_metrics
        view["progress"] = None
        return {
            "run": run_record,
            "summary_state": summary_state,
            "summary": summary,
            "summary_block": summary_block,
            "summary_metrics": summary_metrics,
            "view": view,
        }

    def _build_compare_diagnosis(self, context: dict[str, Any]) -> dict[str, Any]:
        run_record = context["run"]
        summary_block = context.get("summary_block") if isinstance(context.get("summary_block"), dict) else {}
        summary_metrics = context.get("summary_metrics") if isinstance(context.get("summary_metrics"), dict) else {}
        trades = summary_block.get("trades") if isinstance(summary_block.get("trades"), list) else []
        results_per_pair = summary_block.get("results_per_pair") if isinstance(summary_block.get("results_per_pair"), list) else []
        linked_version = mutation_service.get_version_by_id(run_record.version_id) if run_record.version_id else None
        return diagnosis_service.diagnose_run(
            run_record=run_record,
            summary_metrics=summary_metrics,
            summary_block=summary_block,
            trades=trades,
            results_per_pair=results_per_pair,
            request_snapshot=run_record.request_snapshot or {},
            request_snapshot_schema_version=run_record.request_snapshot_schema_version,
            linked_version=linked_version,
        )

    def _extract_rule_set(self, diagnosis: dict[str, Any] | None) -> set[str]:
        rules: set[str] = set()
        for item in (diagnosis or {}).get("ranked_issues") or []:
            if not isinstance(item, dict):
                continue
            rule = str(item.get("rule") or "").strip()
            if rule:
                rules.add(rule)
        return rules

    def _classify_metric_delta(
        self,
        key: str,
        delta: float | None,
        left_rules: set[str],
        right_rules: set[str],
    ) -> str:
        number = self._to_number(delta)
        if number is None or number == 0:
            return "neutral"

        if key in {"profit_total_pct", "profit_total_abs", "win_rate", "sharpe", "sortino", "calmar"}:
            return "improved" if number > 0 else "regressed"
        if key == "max_drawdown_pct":
            return "improved" if number < 0 else "regressed"
        if key == "total_trades":
            rules = set(left_rules) | set(right_rules)
            if "low_sample_size" in rules:
                return "improved" if number > 0 else "regressed"
            if "overtrading" in rules:
                return "improved" if number < 0 else "regressed"
            return "changed"
        return "changed"

    def _describe_metric_delta(
        self,
        key: str,
        classification: str,
        left_rules: set[str],
        right_rules: set[str],
    ) -> str:
        if classification == "neutral":
            return "No persisted change detected."
        if key in {"profit_total_pct", "profit_total_abs"}:
            return "Higher profit is better."
        if key == "win_rate":
            return "Higher win rate is better."
        if key == "max_drawdown_pct":
            return "Lower drawdown is better."
        if key == "total_trades":
            rules = set(left_rules) | set(right_rules)
            if "low_sample_size" in rules:
                return "More trades help reduce low-sample-size risk."
            if "overtrading" in rules:
                return "Fewer trades help reduce overtrading risk."
            return "Trade count changed without a deterministic rule preference."
        if key in {"sharpe", "sortino", "calmar"}:
            return "Higher risk-adjusted return is better."
        return "Persisted metric changed between baseline and candidate."

    def _normalize_pair_metrics(self, row: dict[str, Any]) -> dict[str, Any]:
        profit_total_pct = self._to_number(row.get("profit_total_pct"))
        if profit_total_pct is None:
            profit_total = self._to_number(row.get("profit_total"))
            profit_total_pct = profit_total * 100 if profit_total is not None else None

        win_rate = self._to_number(row.get("winrate"))
        if win_rate is not None:
            win_rate *= 100
        else:
            wins = self._to_number(row.get("wins"))
            trades = self._to_number(row.get("trades"))
            if wins is not None and trades not in (None, 0):
                win_rate = (wins / trades) * 100

        trades = self._to_number(row.get("trades"))
        return {
            "profit_total_pct": profit_total_pct,
            "win_rate": win_rate,
            "trades": int(trades) if trades is not None else None,
        }

    def _build_pair_compare(
        self,
        left_block: dict[str, Any] | None,
        right_block: dict[str, Any] | None,
        left_diagnosis: dict[str, Any],
        right_diagnosis: dict[str, Any],
    ) -> dict[str, Any]:
        def collect(block: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
            rows = block.get("results_per_pair") if isinstance(block, dict) and isinstance(block.get("results_per_pair"), list) else []
            pairs: dict[str, dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                pair = str(row.get("key") or row.get("pair") or "").strip()
                if not pair or pair == "TOTAL":
                    continue
                pairs[pair] = self._normalize_pair_metrics(row)
            return pairs

        left_pairs = collect(left_block)
        right_pairs = collect(right_block)
        rows: list[dict[str, Any]] = []
        for pair in sorted(set(left_pairs) | set(right_pairs)):
            left_metrics = left_pairs.get(pair, {})
            right_metrics = right_pairs.get(pair, {})
            profit_delta = None
            left_profit = self._to_number(left_metrics.get("profit_total_pct"))
            right_profit = self._to_number(right_metrics.get("profit_total_pct"))
            if left_profit is not None and right_profit is not None:
                profit_delta = right_profit - left_profit
            win_rate_delta = None
            left_win_rate = self._to_number(left_metrics.get("win_rate"))
            right_win_rate = self._to_number(right_metrics.get("win_rate"))
            if left_win_rate is not None and right_win_rate is not None:
                win_rate_delta = right_win_rate - left_win_rate
            trades_delta = None
            left_trades = self._to_number(left_metrics.get("trades"))
            right_trades = self._to_number(right_metrics.get("trades"))
            if left_trades is not None and right_trades is not None:
                trades_delta = right_trades - left_trades
            pair_classification = "neutral"
            pair_reason = "No persisted pair delta was detected."
            if profit_delta not in (None, 0):
                pair_classification = "improved" if profit_delta > 0 else "regressed"
                pair_reason = "Per-pair profit improved." if profit_delta > 0 else "Per-pair profit regressed."
            elif win_rate_delta not in (None, 0) or trades_delta not in (None, 0):
                pair_classification = "changed"
                pair_reason = "Per-pair win rate or trade count changed without a profit delta."

            rows.append(
                {
                    "pair": pair,
                    "left": left_metrics,
                    "right": right_metrics,
                    "delta": {
                        "profit_total_pct": profit_delta,
                        "win_rate": win_rate_delta,
                        "trades": trades_delta,
                    },
                    "classification": pair_classification,
                    "reason": pair_reason,
                }
            )

        scored_rows = [row for row in rows if self._to_number(row.get("delta", {}).get("profit_total_pct")) is not None]
        top_improvements = sorted(
            [row for row in scored_rows if self._to_number(row["delta"]["profit_total_pct"]) not in (None, 0) and float(row["delta"]["profit_total_pct"]) > 0],
            key=lambda item: (-float(item["delta"]["profit_total_pct"]), item["pair"]),
        )[:5]
        top_regressions = sorted(
            [row for row in scored_rows if self._to_number(row["delta"]["profit_total_pct"]) not in (None, 0) and float(row["delta"]["profit_total_pct"]) < 0],
            key=lambda item: (float(item["delta"]["profit_total_pct"]), item["pair"]),
        )[:5]

        left_rules = self._extract_rule_set(left_diagnosis)
        right_rules = self._extract_rule_set(right_diagnosis)
        if "pair_dragger" in left_rules and "pair_dragger" not in right_rules:
            pair_dragger_status = "resolved"
        elif "pair_dragger" not in left_rules and "pair_dragger" in right_rules:
            pair_dragger_status = "new"
        elif "pair_dragger" in left_rules and "pair_dragger" in right_rules:
            pair_dragger_status = "persistent"
        else:
            pair_dragger_status = "none"

        summary = {
            "improved_count": sum(1 for row in rows if row.get("classification") == "improved"),
            "regressed_count": sum(1 for row in rows if row.get("classification") == "regressed"),
            "changed_count": sum(1 for row in rows if row.get("classification") == "changed"),
            "neutral_count": sum(1 for row in rows if row.get("classification") == "neutral"),
        }

        return {
            "rows": rows,
            "summary": summary,
            "top_improvements": top_improvements,
            "top_regressions": top_regressions,
            "worst_pair_change": {
                "before": {
                    "pair": left_diagnosis.get("facts", {}).get("worst_pair"),
                    "profit_total_pct": left_diagnosis.get("facts", {}).get("worst_pair_profit_pct"),
                    "trades": left_diagnosis.get("facts", {}).get("worst_pair_trades"),
                },
                "after": {
                    "pair": right_diagnosis.get("facts", {}).get("worst_pair"),
                    "profit_total_pct": right_diagnosis.get("facts", {}).get("worst_pair_profit_pct"),
                    "trades": right_diagnosis.get("facts", {}).get("worst_pair_trades"),
                },
            },
            "pair_dragger_evidence": {
                "status": pair_dragger_status,
                "before": {
                    "pair": left_diagnosis.get("facts", {}).get("worst_pair"),
                    "profit_total_pct": left_diagnosis.get("facts", {}).get("worst_pair_profit_pct"),
                    "trades": left_diagnosis.get("facts", {}).get("worst_pair_trades"),
                },
                "after": {
                    "pair": right_diagnosis.get("facts", {}).get("worst_pair"),
                    "profit_total_pct": right_diagnosis.get("facts", {}).get("worst_pair_profit_pct"),
                    "trades": right_diagnosis.get("facts", {}).get("worst_pair_trades"),
                },
            },
        }

    def _build_diagnosis_delta(self, left_diagnosis: dict[str, Any], right_diagnosis: dict[str, Any]) -> dict[str, Any]:
        left_rules = self._extract_rule_set(left_diagnosis)
        right_rules = self._extract_rule_set(right_diagnosis)
        return {
            "resolved_rules": sorted(left_rules - right_rules),
            "new_rules": sorted(right_rules - left_rules),
            "persistent_rules": sorted(left_rules & right_rules),
            "worst_pair_before": left_diagnosis.get("facts", {}).get("worst_pair"),
            "worst_pair_after": right_diagnosis.get("facts", {}).get("worst_pair"),
        }

    def compare_backtest_runs(self, left_run: BacktestRunRecord, right_run: BacktestRunRecord) -> dict:
        if getattr(left_run, "engine", "freqtrade") != "freqtrade":
            raise ValueError(f"Run {left_run.run_id} is not a freqtrade backtest run")
        if getattr(right_run, "engine", "freqtrade") != "freqtrade":
            raise ValueError(f"Run {right_run.run_id} is not a freqtrade backtest run")

        left_context = self._build_compare_run_context(left_run)
        right_context = self._build_compare_run_context(right_run)
        left_view = left_context["view"]
        right_view = right_context["view"]
        left_metrics = left_context.get("summary_metrics")
        right_metrics = right_context.get("summary_metrics")

        if not left_metrics:
            raise ValueError(f"Run {left_run.run_id} does not have a persisted summary available for compare")
        if not right_metrics:
            raise ValueError(f"Run {right_run.run_id} does not have a persisted summary available for compare")

        left_diagnosis = self._build_compare_diagnosis(left_context)
        right_diagnosis = self._build_compare_diagnosis(right_context)
        left_rules = self._extract_rule_set(left_diagnosis)
        right_rules = self._extract_rule_set(right_diagnosis)

        metric_specs = [
            ("profit_total_pct", "Total Profit %", "pct"),
            ("profit_total_abs", "Total Profit Abs", "money"),
            ("win_rate", "Win Rate", "pct"),
            ("total_trades", "Total Trades", "count"),
            ("pair_count", "Pairs", "count"),
            ("max_drawdown_pct", "Max Drawdown %", "pct"),
            ("sharpe", "Sharpe", "ratio"),
            ("sortino", "Sortino", "ratio"),
            ("calmar", "Calmar", "ratio"),
        ]

        rows = []
        for key, label, value_format in metric_specs:
            left_value = left_metrics.get(key)
            right_value = right_metrics.get(key)
            if left_value is None and right_value is None:
                continue

            left_number = self._to_number(left_value)
            right_number = self._to_number(right_value)
            delta = None
            if left_number is not None and right_number is not None:
                delta = right_number - left_number

            classification = self._classify_metric_delta(key, delta, left_rules, right_rules)
            rows.append(
                {
                    "key": key,
                    "label": label,
                    "format": value_format,
                    "left": left_value,
                    "right": right_value,
                    "delta": delta,
                    "classification": classification,
                    "reason": self._describe_metric_delta(key, classification, left_rules, right_rules),
                }
            )

        version_compare = mutation_service.build_version_compare_payload(left_run.version_id, right_run.version_id)
        pair_compare = self._build_pair_compare(
            left_context.get("summary_block"),
            right_context.get("summary_block"),
            left_diagnosis,
            right_diagnosis,
        )
        diagnosis_delta = self._build_diagnosis_delta(left_diagnosis, right_diagnosis)

        return {
            "left": left_view,
            "right": right_view,
            "metrics": rows,
            "versions": version_compare.get("versions") or {},
            "version_diff": version_compare.get("version_diff") or {},
            "pairs": pair_compare,
            "diagnosis_delta": diagnosis_delta,
        }

    def ingest_backtest_run(self, run_record: BacktestRunRecord) -> dict:
        parser = result_parser_from_id(getattr(run_record, "engine", None))
        parsed = parser.parse_backtest_run(run_record)

        paths = self._run_result_paths(run_record.strategy, run_record.run_id)

        normalized_result = {
            "run_id": run_record.run_id,
            "strategy": run_record.strategy,
            "profit_total_pct": parsed.profit_pct,
            "result": parsed.strategy_result,
        }
        if parsed.strategy_comparison is not None:
            normalized_result["strategy_comparison"] = parsed.strategy_comparison

        summary_payload = {run_record.strategy: parsed.strategy_result}
        if parsed.strategy_comparison is not None:
            summary_payload["strategy_comparison"] = parsed.strategy_comparison

        write_json(paths["result_path"], normalized_result)
        write_json(paths["summary_path"], summary_payload)
        write_json(paths["latest_summary_path"], summary_payload)

        return {
            "raw_result_path": run_record.raw_result_path,
            "result_path": paths["result_path"],
            "summary_path": paths["summary_path"],
            "profit_pct": parsed.profit_pct,
        }

    def load_latest_summary(self, strategy: str) -> Optional[dict]:
        """Load the latest backtest summary JSON for a strategy."""
        base = strategy_results_dir(strategy)
        latest_path = os.path.join(base, "latest.summary.json")
        if os.path.isfile(latest_path):
            return read_json(latest_path)

        pattern = os.path.join(base, "*.summary.json")
        files = sorted(glob.glob(pattern), reverse=True)
        if files:
            return read_json(files[0])

        return None

    def load_trades(self, strategy: str) -> list:
        """Extract trades array from the latest summary."""
        summary = self.load_latest_summary(strategy)
        if not summary:
            return []
        for key, val in summary.items():
            if isinstance(val, dict) and "trades" in val:
                return val["trades"]
        return summary.get("trades", [])

    def load_results_per_pair(self, strategy: str) -> list:
        """Extract per-pair results from the latest summary."""
        summary = self.load_latest_summary(strategy)
        if not summary:
            return []
        for key, val in summary.items():
            if isinstance(val, dict) and "results_per_pair" in val:
                return val["results_per_pair"]
        return summary.get("results_per_pair", [])

    def list_summaries(self, strategy: str) -> list[str]:
        """List all summary files for a strategy."""
        base = strategy_results_dir(strategy)
        if not os.path.isdir(base):
            return []
        return sorted(
            [f for f in os.listdir(base) if f.endswith(".summary.json")],
            reverse=True,
        )

    def list_strategies_with_results(self) -> list[str]:
        """Return all strategies that have at least one result directory."""
        base = user_data_results_dir()
        if not os.path.isdir(base):
            return []
        return [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]


