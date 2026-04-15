from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.models.backtest_models import BacktestRunRecord
from app.core.models.optimizer_models import StrategyVersion
from app.core.utils.datetime_utils import parse_timerange

RULE_VERSION = "freqtrade-run-diagnosis-v1"
_SEVERITY_ORDER = {"critical": 2, "warning": 1}

_HINTS: dict[str, dict[str, Any]] = {
    "negative_profit": {
        "parameters": ["minimal_roi", "stoploss", "trailing_stop"],
        "rationale": "Negative return usually points to weak exits or insufficient downside control.",
    },
    "low_sample_size": {
        "parameters": ["timeframe", "entry thresholds", "pair whitelist"],
        "rationale": "Very low trade counts make the result unstable and often indicate over-restrictive entries or narrow market coverage.",
    },
    "low_win_rate": {
        "parameters": ["entry thresholds", "stoploss", "sell signal guards"],
        "rationale": "Low win rate often reflects loose entries or exits that realize losses too frequently.",
    },
    "high_drawdown": {
        "parameters": ["stoploss", "max_open_trades", "protections"],
        "rationale": "Large drawdowns suggest position sizing or loss containment needs tightening.",
    },
    "overtrading": {
        "parameters": ["pair whitelist", "max_open_trades", "entry filters"],
        "rationale": "Too many trades per pair per day usually signals noisy entries or insufficient trade selection.",
    },
    "long_hold_time": {
        "parameters": ["minimal_roi", "exit signal timing", "unclog logic"],
        "rationale": "Long average hold times usually indicate exits are arriving too late or positions are getting stuck.",
    },
    "pair_dragger": {
        "parameters": ["pair whitelist", "protections", "entry filters"],
        "rationale": "One persistently weak pair can drag portfolio performance and often needs filtering or tailored risk controls.",
    },
    "exit_inefficiency": {
        "parameters": [
            "minimal_roi",
            "stoploss",
            "trailing_stop",
            "exit signal timing",
        ],
        "rationale": "Exit inefficiency is usually improved by faster profit capture, earlier loss cuts, or less permissive stop behavior.",
    },
}

_ACTION_SPECS: dict[str, dict[str, Any]] = {
    "tighten_entries": {
        "label": "Tighten Entries",
        "summary": "Tighten entry conditions to reduce weak or noisy trades.",
    },
    "reduce_weak_pairs": {
        "label": "Reduce Weak Pairs",
        "summary": "Reduce exposure to the diagnosed dragger pair before rerunning.",
    },
    "tighten_stoploss": {
        "label": "Tighten Stoploss",
        "summary": "Tighten downside controls to reduce drawdown and cut losses sooner.",
    },
    "review_exit_timing": {
        "label": "Review Exit Timing",
        "summary": "Review ROI and exit timing controls to avoid overstaying trades.",
    },
}

_RULE_TO_ACTIONS: dict[str, list[str]] = {
    "low_win_rate": ["tighten_entries"],
    "overtrading": ["tighten_entries"],
    "pair_dragger": ["reduce_weak_pairs"],
    "high_drawdown": ["tighten_stoploss"],
    "long_hold_time": ["review_exit_timing"],
    "exit_inefficiency": ["review_exit_timing"],
}


class DiagnosisService:
    def empty_diagnosis(self) -> dict[str, Any]:
        return {
            "facts": {
                "profit_total_pct": None,
                "win_rate_pct": None,
                "total_trades": None,
                "pair_count": None,
                "drawdown_pct": None,
                "avg_duration_hours": None,
                "trades_per_day": None,
                "trades_per_day_per_pair": None,
                "worst_pair": None,
                "worst_pair_profit_pct": None,
                "worst_pair_trades": None,
                "avg_win_duration_hours": None,
                "avg_loss_duration_hours": None,
                "avg_mfe_captured_pct": None,
                "late_stop_flag": None,
            },
            "flags": [],
            "primary_flags": [],
            "ranked_issues": [],
            "evidence": {},
            "parameter_hints": [],
            "proposal_actions": [],
            "insufficient_evidence": {},
            "rule_version": RULE_VERSION,
        }

    def diagnose_run(
        self,
        run_record: BacktestRunRecord,
        summary_metrics: dict[str, Any] | None,
        summary_block: dict[str, Any] | None,
        trades: list[dict[str, Any]] | None,
        results_per_pair: list[dict[str, Any]] | None,
        request_snapshot: dict[str, Any] | None,
        request_snapshot_schema_version: int | None,
        linked_version: StrategyVersion | None,
    ) -> dict[str, Any]:
        diagnosis = self.empty_diagnosis()
        facts = diagnosis["facts"]
        evidence = diagnosis["evidence"]
        insufficient = diagnosis["insufficient_evidence"]
        flags: list[dict[str, Any]] = []

        request_snapshot = request_snapshot or {}
        schema_version = (
            request_snapshot_schema_version
            if request_snapshot_schema_version is not None
            else 0
        )
        summary_metrics = summary_metrics or {}
        summary_block = summary_block or {}
        trades = [trade for trade in trades or [] if isinstance(trade, dict)]
        results_per_pair = [
            row for row in results_per_pair or [] if isinstance(row, dict)
        ]

        total_trades = self._to_int(summary_metrics.get("total_trades"))
        pair_count = self._to_int(summary_metrics.get("pair_count"))
        if pair_count is None:
            pair_count = self._count_pairs(results_per_pair)
        if pair_count is None:
            pairs = request_snapshot.get("pairs")
            if isinstance(pairs, list):
                pair_count = len([pair for pair in pairs if pair])

        facts["profit_total_pct"] = self._rounded(
            summary_metrics.get("profit_total_pct")
        )
        facts["win_rate_pct"] = self._rounded(summary_metrics.get("win_rate"))
        facts["total_trades"] = total_trades
        facts["pair_count"] = pair_count
        facts["drawdown_pct"] = self._rounded(summary_metrics.get("max_drawdown_pct"))
        facts["avg_duration_hours"] = self._derive_avg_duration_hours(
            summary_block, trades
        )
        facts["avg_win_duration_hours"], facts["avg_loss_duration_hours"] = (
            self._derive_win_loss_duration_hours(summary_block, trades)
        )

        worst_pair = self._derive_worst_pair(results_per_pair)
        facts["worst_pair"] = worst_pair.get("pair")
        facts["worst_pair_profit_pct"] = worst_pair.get("profit_pct")
        facts["worst_pair_trades"] = worst_pair.get("trades")

        backtest_days = self._derive_backtest_days(
            trades, summary_metrics, request_snapshot
        )
        facts["trades_per_day"] = self._divide(total_trades, backtest_days)
        facts["trades_per_day_per_pair"] = (
            self._divide(facts["trades_per_day"], max(pair_count or 0, 1))
            if facts["trades_per_day"] is not None
            else None
        )

        mfe_stats = self._derive_mfe_capture(trades)
        facts["avg_mfe_captured_pct"] = mfe_stats.get("avg_mfe_captured_pct")

        stop_stats = self._derive_late_stop(trades)
        facts["late_stop_flag"] = stop_stats.get("late_stop_flag")

        evidence["context"] = {
            "run_id": run_record.run_id,
            "strategy": run_record.strategy,
            "version_id": run_record.version_id,
            "request_snapshot_schema_version": schema_version,
            "request_snapshot": request_snapshot,
            "linked_version_available": linked_version is not None,
        }

        self._evaluate_negative_profit(facts, flags, evidence, insufficient)
        self._evaluate_low_sample_size(facts, flags, evidence, insufficient)
        self._evaluate_low_win_rate(facts, flags, evidence, insufficient)
        self._evaluate_high_drawdown(facts, flags, evidence, insufficient)
        self._evaluate_overtrading(facts, backtest_days, flags, evidence, insufficient)
        self._evaluate_long_hold_time(facts, flags, evidence, insufficient)
        self._evaluate_pair_dragger(facts, flags, evidence, insufficient)
        self._evaluate_exit_inefficiency(
            facts, mfe_stats, stop_stats, flags, evidence, insufficient
        )

        ranked = sorted(
            flags,
            key=lambda item: (
                _SEVERITY_ORDER.get(str(item.get("severity")), 0),
                float(item.get("threshold_distance") or 0.0),
            ),
            reverse=True,
        )
        diagnosis["flags"] = flags
        diagnosis["ranked_issues"] = ranked
        diagnosis["primary_flags"] = ranked[:3]
        diagnosis["parameter_hints"] = [
            {
                "rule": item["rule"],
                "parameters": _HINTS[item["rule"]]["parameters"],
                "rationale": _HINTS[item["rule"]]["rationale"],
            }
            for item in ranked
            if item["rule"] in _HINTS
        ]
        diagnosis["proposal_actions"] = self._build_proposal_actions(
            ranked_issues=ranked,
            parameter_hints=diagnosis["parameter_hints"],
        )
        return diagnosis

    def _build_proposal_actions(
        self,
        ranked_issues: list[dict[str, Any]],
        parameter_hints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        hints_by_rule = {
            str(item.get("rule")): item
            for item in parameter_hints
            if isinstance(item, dict) and item.get("rule")
        }
        actions: list[dict[str, Any]] = []
        action_index: dict[str, dict[str, Any]] = {}

        for issue in ranked_issues:
            if not isinstance(issue, dict):
                continue

            rule = str(issue.get("rule") or "").strip()
            if not rule:
                continue

            for action_type in _RULE_TO_ACTIONS.get(rule, []):
                hint = hints_by_rule.get(rule) or {}
                spec = _ACTION_SPECS.get(action_type) or {}
                existing = action_index.get(action_type)
                if existing is None:
                    existing = {
                        "action_type": action_type,
                        "label": spec.get("label")
                        or action_type.replace("_", " ").title(),
                        "summary": spec.get("summary") or issue.get("message") or rule,
                        "message": issue.get("message") or spec.get("summary") or rule,
                        "severity": issue.get("severity") or "warning",
                        "matched_rules": [],
                        "parameters": [],
                    }
                    action_index[action_type] = existing
                    actions.append(existing)

                if rule not in existing["matched_rules"]:
                    existing["matched_rules"].append(rule)

                for parameter in hint.get("parameters") or []:
                    parameter_text = str(parameter).strip()
                    if parameter_text and parameter_text not in existing["parameters"]:
                        existing["parameters"].append(parameter_text)

        return actions

    def _evaluate_negative_profit(self, facts, flags, evidence, insufficient) -> None:
        actual = self._to_number(facts.get("profit_total_pct"))
        evidence["negative_profit"] = {"profit_total_pct": actual}
        if actual is None:
            insufficient["negative_profit"] = self._insufficient(
                ["profit_total_pct"],
                "Persisted summary metrics did not expose total profit percent.",
            )
            return
        if actual < -5:
            flags.append(
                self._flag(
                    "negative_profit",
                    "critical",
                    actual,
                    0.0,
                    -5.0,
                    -5.0 - actual,
                    f"Total profit is {actual:.2f}% and is below the critical threshold.",
                )
            )
        elif actual < 0:
            flags.append(
                self._flag(
                    "negative_profit",
                    "warning",
                    actual,
                    0.0,
                    -5.0,
                    0.0 - actual,
                    f"Total profit is {actual:.2f}% and is below break-even.",
                )
            )

    def _evaluate_low_sample_size(self, facts, flags, evidence, insufficient) -> None:
        actual = self._to_number(facts.get("total_trades"))
        evidence["low_sample_size"] = {"total_trades": actual}
        if actual is None:
            insufficient["low_sample_size"] = self._insufficient(
                ["total_trades"],
                "Persisted summary metrics did not expose total trade count.",
            )
            return
        if actual < 10:
            flags.append(
                self._flag(
                    "low_sample_size",
                    "critical",
                    actual,
                    30.0,
                    10.0,
                    10.0 - actual,
                    f"Only {int(actual)} trades were recorded, which is critically undersampled.",
                )
            )
        elif actual < 30:
            flags.append(
                self._flag(
                    "low_sample_size",
                    "warning",
                    actual,
                    30.0,
                    10.0,
                    30.0 - actual,
                    f"Only {int(actual)} trades were recorded, which is a weak sample.",
                )
            )

    def _evaluate_low_win_rate(self, facts, flags, evidence, insufficient) -> None:
        actual = self._to_number(facts.get("win_rate_pct"))
        evidence["low_win_rate"] = {"win_rate_pct": actual}
        if actual is None:
            insufficient["low_win_rate"] = self._insufficient(
                ["win_rate_pct"],
                "Persisted summary metrics did not expose win rate percent.",
            )
            return
        if actual < 35:
            flags.append(
                self._flag(
                    "low_win_rate",
                    "critical",
                    actual,
                    45.0,
                    35.0,
                    35.0 - actual,
                    f"Win rate is {actual:.2f}% and is below the critical threshold.",
                )
            )
        elif actual < 45:
            flags.append(
                self._flag(
                    "low_win_rate",
                    "warning",
                    actual,
                    45.0,
                    35.0,
                    45.0 - actual,
                    f"Win rate is {actual:.2f}% and is below the preferred range.",
                )
            )

    def _evaluate_high_drawdown(self, facts, flags, evidence, insufficient) -> None:
        actual = self._to_number(facts.get("drawdown_pct"))
        evidence["high_drawdown"] = {"drawdown_pct": actual}
        if actual is None:
            insufficient["high_drawdown"] = self._insufficient(
                ["drawdown_pct"],
                "Persisted summary metrics did not expose max drawdown percent.",
            )
            return
        if actual > 25:
            flags.append(
                self._flag(
                    "high_drawdown",
                    "critical",
                    actual,
                    15.0,
                    25.0,
                    actual - 25.0,
                    f"Max drawdown reached {actual:.2f}% and breached the critical threshold.",
                )
            )
        elif actual > 15:
            flags.append(
                self._flag(
                    "high_drawdown",
                    "warning",
                    actual,
                    15.0,
                    25.0,
                    actual - 15.0,
                    f"Max drawdown reached {actual:.2f}% and is elevated.",
                )
            )

    def _evaluate_overtrading(
        self, facts, backtest_days, flags, evidence, insufficient
    ) -> None:
        actual = self._to_number(facts.get("trades_per_day_per_pair"))
        evidence["overtrading"] = {
            "trades_per_day": facts.get("trades_per_day"),
            "trades_per_day_per_pair": actual,
            "pair_count": facts.get("pair_count"),
            "backtest_days": self._rounded(backtest_days),
        }
        missing = []
        if facts.get("total_trades") is None:
            missing.append("total_trades")
        if facts.get("pair_count") is None:
            missing.append("pair_count")
        if backtest_days is None:
            missing.append("backtest_days")
        if missing:
            insufficient["overtrading"] = self._insufficient(
                missing,
                "Overtrading requires trade count, pair count, and an observable backtest date range.",
            )
            return
        if actual is None:
            insufficient["overtrading"] = self._insufficient(
                ["trades_per_day_per_pair"],
                "Overtrading ratio could not be derived from the available run data.",
            )
            return
        if actual > 3.0:
            flags.append(
                self._flag(
                    "overtrading",
                    "critical",
                    actual,
                    1.5,
                    3.0,
                    actual - 3.0,
                    f"Trades per day per pair is {actual:.2f}, which is critically high.",
                )
            )
        elif actual > 1.5:
            flags.append(
                self._flag(
                    "overtrading",
                    "warning",
                    actual,
                    1.5,
                    3.0,
                    actual - 1.5,
                    f"Trades per day per pair is {actual:.2f}, which is above the preferred pace.",
                )
            )

    def _evaluate_long_hold_time(self, facts, flags, evidence, insufficient) -> None:
        actual = self._to_number(facts.get("avg_duration_hours"))
        evidence["long_hold_time"] = {"avg_duration_hours": actual}
        if actual is None:
            insufficient["long_hold_time"] = self._insufficient(
                ["avg_duration_hours"],
                "Average hold time could not be derived from the persisted summary or trades.",
            )
            return
        if actual > 24:
            flags.append(
                self._flag(
                    "long_hold_time",
                    "critical",
                    actual,
                    12.0,
                    24.0,
                    actual - 24.0,
                    f"Average hold time is {actual:.2f} hours and is critically long.",
                )
            )
        elif actual > 12:
            flags.append(
                self._flag(
                    "long_hold_time",
                    "warning",
                    actual,
                    12.0,
                    24.0,
                    actual - 12.0,
                    f"Average hold time is {actual:.2f} hours and is longer than preferred.",
                )
            )

    def _evaluate_pair_dragger(self, facts, flags, evidence, insufficient) -> None:
        profit_pct = self._to_number(facts.get("worst_pair_profit_pct"))
        trades = self._to_number(facts.get("worst_pair_trades"))
        evidence["pair_dragger"] = {
            "worst_pair": facts.get("worst_pair"),
            "worst_pair_profit_pct": profit_pct,
            "worst_pair_trades": trades,
        }
        missing = []
        if facts.get("worst_pair") is None:
            missing.append("worst_pair")
        if profit_pct is None:
            missing.append("worst_pair_profit_pct")
        if trades is None:
            missing.append("worst_pair_trades")
        if missing:
            insufficient["pair_dragger"] = self._insufficient(
                missing,
                "Per-pair breakdown data is required to identify a consistent dragger pair.",
            )
            return
        if profit_pct <= -5 and trades >= 5:
            flags.append(
                self._flag(
                    "pair_dragger",
                    "warning",
                    profit_pct,
                    -5.0,
                    None,
                    abs(profit_pct + 5.0),
                    f"{facts.get('worst_pair')} is down {profit_pct:.2f}% across {int(trades)} trades and is dragging the run.",
                )
            )

    def _evaluate_exit_inefficiency(
        self, facts, mfe_stats, stop_stats, flags, evidence, insufficient
    ) -> None:
        avg_win = self._to_number(facts.get("avg_win_duration_hours"))
        avg_loss = self._to_number(facts.get("avg_loss_duration_hours"))
        avg_mfe_captured = self._to_number(facts.get("avg_mfe_captured_pct"))
        late_stop_flag = facts.get("late_stop_flag")
        evidence["exit_inefficiency"] = {
            "avg_win_duration_hours": avg_win,
            "avg_loss_duration_hours": avg_loss,
            "avg_mfe_captured_pct": avg_mfe_captured,
            "late_stop_flag": late_stop_flag,
            "avg_adverse_excursion_pct": stop_stats.get("avg_adverse_excursion_pct"),
            "avg_stop_loss_pct": stop_stats.get("avg_stop_loss_pct"),
            "mfe_trade_count": mfe_stats.get("trade_count"),
            "late_stop_trade_count": stop_stats.get("trade_count"),
        }

        missing = []
        duration_trigger = False
        mfe_trigger = False
        stop_trigger = False
        distances = []

        if avg_win is None or avg_loss is None:
            missing.append("winner_loser_duration")
        elif avg_win > 0 and avg_loss > (1.3 * avg_win):
            duration_trigger = True
            distances.append(avg_loss - (1.3 * avg_win))

        if avg_mfe_captured is None:
            missing.append("avg_mfe_captured_pct")
        elif avg_mfe_captured < 60:
            mfe_trigger = True
            distances.append(60.0 - avg_mfe_captured)

        if late_stop_flag is None:
            missing.append("late_stop_flag")
        elif late_stop_flag:
            stop_trigger = True
            distances.append(1.0)

        if missing:
            insufficient["exit_inefficiency"] = self._insufficient(
                missing,
                "Exit inefficiency uses win/loss duration split, MFE capture, and late-stop evidence when available.",
            )

        if not (duration_trigger or mfe_trigger or stop_trigger):
            return

        reasons = []
        if duration_trigger:
            reasons.append(f"losers average {avg_loss:.2f}h vs winners {avg_win:.2f}h")
        if mfe_trigger:
            reasons.append(f"only {avg_mfe_captured:.2f}% of available MFE is captured")
        if stop_trigger:
            reasons.append("losing trades exceed the configured stop depth before exit")
        flags.append(
            self._flag(
                "exit_inefficiency",
                "warning",
                {
                    "avg_loss_duration_hours": avg_loss,
                    "avg_win_duration_hours": avg_win,
                    "avg_mfe_captured_pct": avg_mfe_captured,
                    "late_stop_flag": late_stop_flag,
                },
                {
                    "loss_vs_win_duration_ratio": 1.3,
                    "avg_mfe_captured_pct": 60.0,
                    "late_stop_flag": True,
                },
                None,
                max(distances) if distances else 0.0,
                "Exit behavior looks inefficient because " + "; ".join(reasons) + ".",
            )
        )

    def _derive_avg_duration_hours(
        self, summary_block: dict[str, Any], trades: list[dict[str, Any]]
    ) -> float | None:
        summary_seconds = self._to_number(summary_block.get("holding_avg_s"))
        if summary_seconds is not None:
            return self._rounded(summary_seconds / 3600.0)
        summary_text = summary_block.get("holding_avg")
        if summary_text:
            hours = self._parse_duration_hours(summary_text)
            if hours is not None:
                return self._rounded(hours)
        durations = [self._trade_duration_hours(trade) for trade in trades]
        durations = [duration for duration in durations if duration is not None]
        if not durations:
            return None
        return self._rounded(sum(durations) / len(durations))

    def _derive_win_loss_duration_hours(
        self, summary_block: dict[str, Any], trades: list[dict[str, Any]]
    ) -> tuple[float | None, float | None]:
        win_seconds = self._to_number(summary_block.get("winner_holding_avg_s"))
        loss_seconds = self._to_number(summary_block.get("loser_holding_avg_s"))
        if win_seconds is not None or loss_seconds is not None:
            return (
                self._rounded(
                    (win_seconds / 3600.0) if win_seconds is not None else None
                ),
                self._rounded(
                    (loss_seconds / 3600.0) if loss_seconds is not None else None
                ),
            )

        win_text = summary_block.get("winner_holding_avg")
        loss_text = summary_block.get("loser_holding_avg")
        if win_text or loss_text:
            return (
                self._rounded(self._parse_duration_hours(win_text)),
                self._rounded(self._parse_duration_hours(loss_text)),
            )

        winners = []
        losers = []
        for trade in trades:
            duration = self._trade_duration_hours(trade)
            profit_pct = self._trade_profit_pct(trade)
            if duration is None or profit_pct is None:
                continue
            if profit_pct > 0:
                winners.append(duration)
            elif profit_pct < 0:
                losers.append(duration)

        win_avg = (sum(winners) / len(winners)) if winners else None
        loss_avg = (sum(losers) / len(losers)) if losers else None
        return self._rounded(win_avg), self._rounded(loss_avg)

    def _derive_worst_pair(
        self, results_per_pair: list[dict[str, Any]]
    ) -> dict[str, Any]:
        worst = {"pair": None, "profit_pct": None, "trades": None}
        for row in results_per_pair:
            pair = row.get("key") or row.get("pair")
            if pair == "TOTAL":
                continue
            profit_pct = self._to_number(row.get("profit_total_pct"))
            if profit_pct is None:
                profit_total = self._to_number(row.get("profit_total"))
                if profit_total is not None:
                    profit_pct = profit_total * 100.0
            if profit_pct is None:
                continue
            if worst["profit_pct"] is None or profit_pct < worst["profit_pct"]:
                worst = {
                    "pair": pair,
                    "profit_pct": self._rounded(profit_pct),
                    "trades": self._to_int(row.get("trades")),
                }
        return worst

    def _derive_backtest_days(
        self, trades, summary_metrics, request_snapshot
    ) -> float | None:
        timestamps = []
        for trade in trades:
            open_ts = self._trade_timestamp(trade, "open")
            close_ts = self._trade_timestamp(trade, "close")
            if open_ts is not None:
                timestamps.append(open_ts)
            if close_ts is not None:
                timestamps.append(close_ts)

        if len(timestamps) >= 2:
            return max((max(timestamps) - min(timestamps)) / 86400.0, 1.0)

        timerange = request_snapshot.get("timerange") or summary_metrics.get(
            "timerange"
        )
        if isinstance(timerange, str) and timerange:
            try:
                start_token, end_token = parse_timerange(timerange)
                start = datetime.strptime(start_token, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
                end = datetime.strptime(end_token, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
                return max((end - start).total_seconds() / 86400.0, 1.0)
            except ValueError:
                return None
        return None

    def _derive_mfe_capture(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        captures = []
        for trade in trades:
            if trade.get("is_short"):
                continue
            open_rate = self._to_number(trade.get("open_rate"))
            max_rate = self._to_number(trade.get("max_rate"))
            profit_ratio = self._trade_profit_ratio(trade)
            if (
                open_rate is None
                or max_rate is None
                or profit_ratio is None
                or open_rate <= 0
                or max_rate <= open_rate
            ):
                continue
            available_pct = ((max_rate - open_rate) / open_rate) * 100.0
            if available_pct <= 0:
                continue
            realized_pct = profit_ratio * 100.0
            captures.append((realized_pct / available_pct) * 100.0)

        if not captures:
            return {"avg_mfe_captured_pct": None, "trade_count": 0}

        return {
            "avg_mfe_captured_pct": self._rounded(sum(captures) / len(captures)),
            "trade_count": len(captures),
        }

    def _derive_late_stop(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        adverse_moves = []
        stop_losses = []
        for trade in trades:
            if trade.get("is_short"):
                continue
            profit_ratio = self._trade_profit_ratio(trade)
            open_rate = self._to_number(trade.get("open_rate"))
            min_rate = self._to_number(trade.get("min_rate"))
            stop_loss_ratio = self._to_number(trade.get("stop_loss_ratio"))
            if profit_ratio is None or profit_ratio >= 0:
                continue
            if (
                open_rate is None
                or min_rate is None
                or stop_loss_ratio is None
                or open_rate <= 0
            ):
                continue
            adverse_pct = abs(((min_rate - open_rate) / open_rate) * 100.0)
            stop_loss_pct = abs(stop_loss_ratio * 100.0)
            adverse_moves.append(adverse_pct)
            stop_losses.append(stop_loss_pct)

        if not adverse_moves or not stop_losses:
            return {
                "late_stop_flag": None,
                "avg_adverse_excursion_pct": None,
                "avg_stop_loss_pct": None,
                "trade_count": 0,
            }

        avg_adverse = sum(adverse_moves) / len(adverse_moves)
        avg_stop = sum(stop_losses) / len(stop_losses)
        return {
            "late_stop_flag": avg_adverse > avg_stop,
            "avg_adverse_excursion_pct": self._rounded(avg_adverse),
            "avg_stop_loss_pct": self._rounded(avg_stop),
            "trade_count": len(adverse_moves),
        }

    def _count_pairs(self, results_per_pair: list[dict[str, Any]]) -> int | None:
        count = len(
            [
                row
                for row in results_per_pair
                if str(row.get("key") or row.get("pair") or "") != "TOTAL"
            ]
        )
        return count or None

    def _trade_timestamp(self, trade: dict[str, Any], mode: str) -> float | None:
        ts_key = "open_timestamp" if mode == "open" else "close_timestamp"
        if trade.get(ts_key) is not None:
            timestamp = self._to_number(trade.get(ts_key))
            if timestamp is not None:
                return timestamp / 1000.0
        date_key = "open_date" if mode == "open" else "close_date"
        value = trade.get(date_key)
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    def _trade_duration_hours(self, trade: dict[str, Any]) -> float | None:
        minutes = self._to_number(trade.get("trade_duration"))
        if minutes is not None:
            return minutes / 60.0
        return self._parse_duration_hours(trade.get("duration"))

    def _trade_profit_ratio(self, trade: dict[str, Any]) -> float | None:
        ratio = self._to_number(trade.get("profit_ratio"))
        if ratio is not None:
            return ratio
        profit_pct = self._to_number(trade.get("profit_pct"))
        if profit_pct is not None:
            return profit_pct / 100.0
        return None

    def _trade_profit_pct(self, trade: dict[str, Any]) -> float | None:
        ratio = self._trade_profit_ratio(trade)
        return ratio * 100.0 if ratio is not None else None

    def _parse_duration_hours(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        text = str(value).strip().lower()
        day_count = 0.0
        if "day" in text:
            day_part, _, remainder = text.partition("day")
            day_token = "".join(ch for ch in day_part if ch.isdigit())
            if day_token:
                day_count = float(day_token)
            text = remainder.lstrip("s ").strip()
        elif "d " in text:
            day_part, _, remainder = text.partition("d ")
            if day_part.isdigit():
                day_count = float(day_part)
            text = remainder.strip()

        if not text:
            return day_count * 24.0

        parts = text.split(":")
        try:
            if len(parts) == 3:
                hours, minutes, seconds = [float(part) for part in parts]
            elif len(parts) == 2:
                hours = 0.0
                minutes, seconds = [float(part) for part in parts]
            else:
                return None
        except ValueError:
            return None

        return day_count * 24.0 + hours + (minutes / 60.0) + (seconds / 3600.0)

    def _flag(
        self,
        rule,
        severity,
        actual,
        warning_threshold,
        critical_threshold,
        threshold_distance,
        message,
    ) -> dict[str, Any]:
        return {
            "rule": rule,
            "severity": severity,
            "message": message,
            "actual": actual,
            "warning_threshold": warning_threshold,
            "critical_threshold": critical_threshold,
            "threshold_distance": self._rounded(threshold_distance),
        }

    def _insufficient(self, missing_fields: list[str], reason: str) -> dict[str, Any]:
        return {"missing": missing_fields, "reason": reason}

    def _divide(self, numerator: Any, denominator: Any) -> float | None:
        left = self._to_number(numerator)
        right = self._to_number(denominator)
        if left is None or right in (None, 0):
            return None
        return self._rounded(left / right)

    def _rounded(self, value: Any, digits: int = 4) -> float | None:
        number = self._to_number(value)
        if number is None:
            return None
        return round(number, digits)

    def _to_number(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number:
            return None
        return number

    def _to_int(self, value: Any) -> int | None:
        number = self._to_number(value)
        return int(number) if number is not None else None


diagnosis_service = DiagnosisService()


__all__ = ["DiagnosisService", "diagnosis_service", "RULE_VERSION"]
