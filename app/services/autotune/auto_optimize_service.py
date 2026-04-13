from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid
from typing import Any

from app.freqtrade import runtime as freqtrade_runtime
from app.models.backtest_models import BacktestRunRecord, BacktestRunRequest, BacktestRunStatus
from app.models.optimizer_models import (
    ChangeType,
    MutationRequest,
    OptimizationCompletionReason,
    OptimizationError,
    OptimizationFinalist,
    OptimizationHardStops,
    OptimizationNearMiss,
    OptimizationNodeRecord,
    OptimizationResultKind,
    OptimizationRunCreateRequest,
    OptimizationRunRecord,
    OptimizationRunStatus,
)
from app.services.mutation_service import mutation_service
from app.services.persistence_service import PersistenceService
from app.utils.datetime_utils import now_iso


class AutoOptimizeFatalError(Exception):
    def __init__(self, error: OptimizationError):
        super().__init__(error.message)
        self.error = error


class AutoOptimizeService:
    def __init__(self) -> None:
        self._persistence = PersistenceService()
        self._tasks: dict[str, asyncio.Task] = {}

    def _persist_record(self, record: OptimizationRunRecord) -> None:
        payload = record.model_dump(mode="json")
        nodes = payload.pop("nodes", None)
        self._persistence.save_optimizer_run(record.optimizer_run_id, payload)
        self._persistence.save_optimizer_nodes(
            record.optimizer_run_id,
            {"schema_version": record.schema_version, "nodes": nodes or []},
        )

    def _emit(self, optimizer_run_id: str, event_type: str, **data: Any) -> None:
        payload = {
            "event_type": event_type,
            "created_at": now_iso(),
            "optimizer_run_id": optimizer_run_id,
            **data,
        }
        self._persistence.append_optimizer_event(optimizer_run_id, payload)

    def _start_task(self, optimizer_run_id: str) -> None:
        loop = asyncio.get_running_loop()
        task = loop.create_task(self._run_optimizer(optimizer_run_id))
        self._tasks[optimizer_run_id] = task

        def _cleanup(done: asyncio.Task) -> None:
            self._tasks.pop(optimizer_run_id, None)
            try:
                done.result()
            except Exception:
                pass

        task.add_done_callback(_cleanup)

    def _fail_baseline_validation(
        self,
        *,
        optimizer_run_id: str,
        baseline_run_id: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = now_iso()
        error = OptimizationError(
            error_code="baseline_validation_failed",
            error_stage="baseline_validation",
            message=message,
            optimizer_run_id=optimizer_run_id,
            details=details or {},
            suggested_fix="Run a completed backtest with a ready summary first, then retry Auto Optimize.",
        )
        record = OptimizationRunRecord(
            schema_version=1,
            optimizer_run_id=optimizer_run_id,
            status=OptimizationRunStatus.FAILED,
            result_kind=OptimizationResultKind.FATAL_ERROR,
            completion_reason=OptimizationCompletionReason.FATAL_ERROR,
            baseline_run_id=baseline_run_id,
            baseline_version_id=None,
            request_snapshot={},
            attempts=1,
            beam_width=1,
            branch_factor=1,
            include_ai_suggestions=False,
            thresholds={},
            hard_stops={},
            created_at=now,
            updated_at=now,
            completed_at=now,
            finalists=[],
            near_misses=[],
            nodes=[],
            error=error,
        )
        self._persist_record(record)
        self._emit(optimizer_run_id, "optimizer_failed", error=error.model_dump(mode="json"))
        raise AutoOptimizeFatalError(error)

    def create_run(self, request: OptimizationRunCreateRequest) -> OptimizationRunRecord:
        optimizer_run_id = f"aopt-{uuid.uuid4().hex[:8]}"

        baseline_data = self._persistence.load_backtest_run(request.baseline_run_id)
        if not isinstance(baseline_data, dict) or not baseline_data:
            self._fail_baseline_validation(
                optimizer_run_id=optimizer_run_id,
                baseline_run_id=request.baseline_run_id,
                message=f"Baseline run {request.baseline_run_id} not found",
            )

        try:
            baseline_run = BacktestRunRecord(**baseline_data)
        except Exception as exc:
            self._fail_baseline_validation(
                optimizer_run_id=optimizer_run_id,
                baseline_run_id=request.baseline_run_id,
                message="Baseline run metadata is invalid",
                details={"exception": str(exc)},
            )

        if baseline_run.status != BacktestRunStatus.COMPLETED:
            self._fail_baseline_validation(
                optimizer_run_id=optimizer_run_id,
                baseline_run_id=request.baseline_run_id,
                message=(
                    f"Baseline run {request.baseline_run_id} is not completed "
                    f"(status={baseline_run.status.value})"
                ),
                details={"status": baseline_run.status.value},
            )

        summary_state = freqtrade_runtime.results_svc.load_run_summary_state(baseline_run)
        if summary_state.get("state") != "ready":
            self._fail_baseline_validation(
                optimizer_run_id=optimizer_run_id,
                baseline_run_id=request.baseline_run_id,
                message=f"Baseline run {request.baseline_run_id} summary is not ready",
                details={"summary_state": summary_state},
            )

        if not baseline_run.version_id:
            self._fail_baseline_validation(
                optimizer_run_id=optimizer_run_id,
                baseline_run_id=request.baseline_run_id,
                message=f"Baseline run {request.baseline_run_id} has no version_id",
            )

        if not isinstance(baseline_run.request_snapshot, dict) or not baseline_run.request_snapshot:
            self._fail_baseline_validation(
                optimizer_run_id=optimizer_run_id,
                baseline_run_id=request.baseline_run_id,
                message=f"Baseline run {request.baseline_run_id} request_snapshot is missing or invalid",
            )

        hard_stops = OptimizationHardStops(**request.hard_stops.model_dump(mode="json"))
        if hard_stops.max_total_nodes is None:
            hard_stops.max_total_nodes = request.attempts * request.beam_width * request.branch_factor + 1
        if hard_stops.max_failed_runs is None:
            hard_stops.max_failed_runs = request.beam_width * request.branch_factor * 2

        created_at = now_iso()
        record = OptimizationRunRecord(
            schema_version=1,
            optimizer_run_id=optimizer_run_id,
            status=OptimizationRunStatus.QUEUED,
            result_kind=None,
            completion_reason=None,
            baseline_run_id=request.baseline_run_id,
            baseline_version_id=baseline_run.version_id,
            request_snapshot=dict(baseline_run.request_snapshot or {}),
            attempts=request.attempts,
            beam_width=request.beam_width,
            branch_factor=request.branch_factor,
            include_ai_suggestions=request.include_ai_suggestions,
            thresholds=request.thresholds,
            hard_stops=hard_stops,
            created_at=created_at,
            updated_at=created_at,
            completed_at=None,
            finalists=[],
            near_misses=[],
            nodes=[],
            error=None,
        )
        self._persist_record(record)
        self._emit(
            optimizer_run_id,
            "optimizer_run_created",
            baseline_run_id=request.baseline_run_id,
        )
        return record

    def start_run(self, request: OptimizationRunCreateRequest) -> OptimizationRunRecord:
        record = self.create_run(request)
        self._start_task(record.optimizer_run_id)
        return record

    def get_run(self, optimizer_run_id: str) -> OptimizationRunRecord | None:
        meta = self._persistence.load_optimizer_run(optimizer_run_id)
        if not isinstance(meta, dict) or not meta.get("optimizer_run_id"):
            return None

        nodes_payload = self._persistence.load_optimizer_nodes(optimizer_run_id)
        nodes = []
        if isinstance(nodes_payload, dict) and isinstance(nodes_payload.get("nodes"), list):
            nodes = nodes_payload.get("nodes")

        meta = dict(meta)
        meta["nodes"] = nodes
        return OptimizationRunRecord(**meta)
    def _norm_json(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _sig(self, *, parent_version_id: str, descriptor: str, parameters: dict[str, Any]) -> str:
        raw = f"{parent_version_id}|{descriptor}|{self._norm_json(parameters)}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _constraints_failed(self, metrics: dict[str, Any] | None, thresholds: Any) -> list[str]:
        m = metrics or {}
        failed: list[str] = []

        profit = m.get("profit_total_pct")
        trades = m.get("total_trades")
        dd = m.get("max_drawdown_pct")

        min_profit = float(getattr(thresholds, "min_profit_total_pct", 0.5) or 0.5)
        min_trades = int(getattr(thresholds, "min_total_trades", 30) or 30)
        max_dd = float(getattr(thresholds, "max_allowed_drawdown_pct", 35) or 35)

        if profit is None or float(profit) < min_profit:
            failed.append("min_profit_total_pct")
        if trades is None or int(trades) < min_trades:
            failed.append("min_total_trades")
        if dd is None or float(dd) > max_dd:
            failed.append("max_allowed_drawdown_pct")

        return failed

    def _score(self, metrics: dict[str, Any] | None) -> float | None:
        m = metrics or {}
        keys = ("profit_total_pct", "max_drawdown_pct", "win_rate", "total_trades")
        if any(m.get(k) is None for k in keys):
            return None
        try:
            return (
                float(m["profit_total_pct"])
                - 0.5 * float(m["max_drawdown_pct"])
                + 0.05 * float(m["win_rate"])
                + 0.01 * float(m["total_trades"])
            )
        except Exception:
            return None

    def _frontier(
        self,
        nodes: list[OptimizationNodeRecord],
        *,
        beam_width: int,
        expanded: set[str],
    ) -> list[OptimizationNodeRecord]:
        pool = [
            n
            for n in nodes
            if n.status == "completed" and n.node_id not in expanded and n.score is not None
        ]
        if not pool:
            return []
        qualifying = [n for n in pool if n.constraint_passed]
        chosen = qualifying if qualifying else pool
        chosen = sorted(chosen, key=lambda n: float(n.score or -1e9), reverse=True)
        return chosen[: max(1, int(beam_width))]

    def _finalist_nodes(self, nodes: list[OptimizationNodeRecord]) -> list[OptimizationNodeRecord]:
        qualifying = [
            n
            for n in nodes
            if n.status == "completed" and n.constraint_passed and n.run_id and n.candidate_version_id
        ]
        qualifying = sorted(qualifying, key=lambda n: float(n.score or -1e9), reverse=True)
        if not qualifying:
            return []

        picked: list[OptimizationNodeRecord] = [qualifying.pop(0)]
        if not qualifying:
            return picked

        qualifying.sort(key=lambda n: float((n.summary_metrics or {}).get("max_drawdown_pct") or 1e9))
        for node in list(qualifying):
            if node.candidate_version_id != picked[0].candidate_version_id:
                picked.append(node)
                qualifying.remove(node)
                break

        if len(picked) >= 3 or not qualifying:
            return picked[:3]

        qualifying.sort(key=lambda n: float((n.summary_metrics or {}).get("total_trades") or 0), reverse=True)
        for node in qualifying:
            if node.candidate_version_id not in {p.candidate_version_id for p in picked}:
                picked.append(node)
                break

        return picked[:3]

    def _safe_keys(self, params: dict[str, Any]) -> set[str]:
        safe: set[str] = set(str(k) for k in params.keys())
        buy = params.get("buy_params")
        if isinstance(buy, dict):
            safe.update(str(k) for k in buy.keys())
            safe.update(f"buy_params.{k}" for k in buy.keys())
        sell = params.get("sell_params")
        if isinstance(sell, dict):
            safe.update(str(k) for k in sell.keys())
            safe.update(f"sell_params.{k}" for k in sell.keys())
        return safe

    def _apply_ai_seed(
        self,
        base: dict[str, Any],
        suggestion: dict[str, Any],
        safe: set[str],
    ) -> tuple[str, dict[str, Any]] | None:
        name = str(suggestion.get("name") or "").strip()
        if not name or name not in safe:
            return None
        value = suggestion.get("value")
        if value is None:
            return None

        out = copy.deepcopy(base)
        if "." in name:
            prefix, rest = name.split(".", 1)
            bucket = out.get(prefix)
            if prefix in {"buy_params", "sell_params"} and rest and isinstance(bucket, dict):
                bucket[rest] = value
                return f"ai_seed:{name}", out
            return None

        out[name] = value
        for nested in ("buy_params", "sell_params"):
            bucket = out.get(nested)
            if isinstance(bucket, dict) and name in bucket:
                bucket[name] = value
        return f"ai_seed:{name}", out

    def _resolve_base_params(self, strategy_name: str, version_id: str) -> dict[str, Any]:
        resolved = mutation_service.resolve_effective_artifacts(version_id)
        params = resolved.get("parameters_snapshot")
        if isinstance(params, dict) and params:
            return copy.deepcopy(params)

        try:
            from app.services.results import strategy_intelligence_apply_service as apply_service

            linked = mutation_service.get_version_by_id(version_id)
            snapshot = apply_service._resolve_parameters_snapshot(strategy_name, linked)
            if isinstance(snapshot, dict) and snapshot:
                return copy.deepcopy(snapshot)
        except Exception:
            pass

        return {}

    def _action_params(self, action_type: str, base: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any] | None:
        if not base:
            return None
        params = copy.deepcopy(base)
        changed = False

        def _set_entry(key: str, value: Any) -> None:
            nonlocal changed
            params[key] = value
            buy = params.get("buy_params")
            if isinstance(buy, dict) and key in buy:
                buy[key] = value
            changed = True

        if action_type == "tighten_entries":
            for key in ("entry_trigger", "buy_rsi", "buy_threshold", "entry_threshold"):
                if key not in params or not isinstance(params[key], (int, float)) or isinstance(params[key], bool):
                    continue
                if "rsi" in key.lower():
                    _set_entry(key, min(float(params[key]) + 5.0, 100.0))
                elif float(params[key]) > 0:
                    _set_entry(key, float(params[key]) * 1.1)

            for key, ceiling_key in (("buy_ma_count", "count_max"), ("buy_ma_gap", "gap_max")):
                if key not in params or not isinstance(params[key], (int, float)) or isinstance(params[key], bool):
                    continue
                cur = float(params[key])
                if cur <= 0:
                    continue
                nxt = cur + 1.0
                ceiling = params.get(ceiling_key)
                if isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool):
                    nxt = min(nxt, float(ceiling))
                if nxt != cur:
                    _set_entry(key, int(nxt) if isinstance(params[key], int) else nxt)

        elif action_type == "reduce_weak_pairs":
            worst = None
            if isinstance((diagnosis or {}).get("facts"), dict):
                worst = diagnosis["facts"].get("worst_pair")
            if not worst:
                return None
            excluded = params.get("excluded_pairs")
            if isinstance(excluded, list):
                if worst in excluded:
                    return None
                excluded.append(worst)
            else:
                params["excluded_pairs"] = [worst]
            changed = True

        elif action_type == "tighten_stoploss":
            sl = params.get("stoploss")
            if isinstance(sl, (int, float)) and sl < 0:
                params["stoploss"] = round(max(float(sl) * 0.75, -0.5), 6)
                changed = True
            ts = params.get("trailing_stop")
            if isinstance(ts, bool) and not ts:
                params["trailing_stop"] = True
                changed = True
            tp = params.get("trailing_stop_positive")
            if isinstance(tp, (int, float)) and float(tp) > 0.001:
                params["trailing_stop_positive"] = round(max(float(tp) * 0.5, 0.001), 6)
                changed = True

        elif action_type == "review_exit_timing":
            roi = params.get("minimal_roi")
            if isinstance(roi, dict) and roi:
                reviewed: dict[str, Any] = {}
                for t, target in roi.items():
                    try:
                        reviewed[str(max(int(int(t) * 0.5), 0))] = target
                        changed = True
                    except (TypeError, ValueError):
                        reviewed[str(t)] = target
                if changed:
                    params["minimal_roi"] = reviewed

            tp = params.get("trailing_stop_positive")
            if isinstance(tp, (int, float)) and float(tp) > 0.001:
                params["trailing_stop_positive"] = round(max(float(tp) * 0.7, 0.001), 6)
                changed = True

        return params if changed else None

    def _candidate_seeds(
        self,
        *,
        base_params: dict[str, Any],
        diagnosis: dict[str, Any],
        ai_payload: dict[str, Any],
        branch_factor: int,
        include_ai: bool,
    ) -> list[tuple[str, dict[str, Any]]]:
        seeds: list[tuple[str, dict[str, Any]]] = []

        actions = (diagnosis or {}).get("proposal_actions") or []
        if isinstance(actions, list):
            for item in actions:
                if not isinstance(item, dict):
                    continue
                action_type = str(item.get("action_type") or "").strip()
                if not action_type:
                    continue
                params = self._action_params(action_type, base_params, diagnosis)
                if isinstance(params, dict) and params:
                    seeds.append((f"deterministic_action:{action_type}", params))

        if include_ai and isinstance(ai_payload, dict) and ai_payload.get("ai_status") == "ready":
            safe = self._safe_keys(base_params)
            suggestions = ai_payload.get("parameter_suggestions") or []
            if isinstance(suggestions, list):
                for suggestion in suggestions:
                    if not isinstance(suggestion, dict):
                        continue
                    applied = self._apply_ai_seed(base_params, suggestion, safe)
                    if applied is not None:
                        seeds.append(applied)

        if len(seeds) < branch_factor:
            nudge = self._action_params("tighten_stoploss", base_params, diagnosis)
            if isinstance(nudge, dict) and nudge:
                seeds.append(("nudge:tighten_stoploss", nudge))
        if len(seeds) < branch_factor:
            nudge = self._action_params("review_exit_timing", base_params, diagnosis)
            if isinstance(nudge, dict) and nudge:
                seeds.append(("nudge:review_exit_timing", nudge))

        return seeds

    async def _wait_summary_ready(
        self,
        run_id: str,
        *,
        poll_interval: float = 0.5,
        timeout_seconds: float = 3600.0,
    ) -> tuple[BacktestRunRecord | None, dict[str, Any] | None, str | None]:
        start = asyncio.get_running_loop().time()
        while True:
            data = self._persistence.load_backtest_run(run_id)
            run = None
            if isinstance(data, dict) and data.get("run_id"):
                try:
                    run = BacktestRunRecord(**data)
                    run = freqtrade_runtime._reconcile_stale_backtest_run(run)
                except Exception:
                    run = None

            if run is not None:
                state = freqtrade_runtime.results_svc.load_run_summary_state(run)
                if state.get("state") == "ready":
                    summary = state.get("summary")
                    metrics = (
                        freqtrade_runtime.results_svc._normalize_summary_metrics(summary, run.strategy)
                        if summary
                        else None
                    )
                    return run, metrics, None

                if run.status in {BacktestRunStatus.FAILED, BacktestRunStatus.STOPPED}:
                    return run, None, state.get("error") or run.error or "run_failed"

                if run.status == BacktestRunStatus.COMPLETED and state.get("state") == "load_failed":
                    return run, None, state.get("error") or "summary_load_failed"

            if asyncio.get_running_loop().time() - start > timeout_seconds:
                return run, None, "timeout_waiting_for_summary"

            await asyncio.sleep(poll_interval)
    def _finalize(
        self,
        record: OptimizationRunRecord,
        *,
        nodes: list[OptimizationNodeRecord],
        result_kind: OptimizationResultKind,
        completion_reason: OptimizationCompletionReason,
        event_type: str,
        hard_stop_reason: str | None = None,
    ) -> None:
        record.finalists = [
            OptimizationFinalist(
                version_id=str(n.candidate_version_id),
                run_id=str(n.run_id),
                summary_metrics=n.summary_metrics or {},
                score=n.score,
            )
            for n in self._finalist_nodes(nodes)
        ]

        misses = [
            n
            for n in nodes
            if n.status == "completed" and not n.constraint_passed and n.score is not None
        ]
        misses = sorted(misses, key=lambda n: float(n.score or -1e9), reverse=True)[:5]
        record.near_misses = [
            OptimizationNearMiss(
                node_id=n.node_id,
                version_id=n.candidate_version_id,
                run_id=n.run_id,
                summary_metrics=n.summary_metrics or {},
                score=n.score,
                failed_constraints=list(n.failed_constraints or []),
                candidate_descriptor=n.candidate_descriptor,
            )
            for n in misses
        ]

        record.status = OptimizationRunStatus.COMPLETED
        record.result_kind = result_kind
        record.completion_reason = completion_reason
        record.completed_at = now_iso()
        record.updated_at = record.completed_at
        record.nodes = nodes
        self._persist_record(record)
        self._emit(
            record.optimizer_run_id,
            event_type,
            result_kind=result_kind.value,
            completion_reason=completion_reason.value,
            hard_stop_reason=hard_stop_reason,
            finalists=[f.model_dump(mode="json") for f in record.finalists],
            near_misses=[m.model_dump(mode="json") for m in record.near_misses],
        )

    async def _run_optimizer(self, optimizer_run_id: str) -> None:
        record = self.get_run(optimizer_run_id)
        if record is None:
            return

        nodes: list[OptimizationNodeRecord] = []
        expanded: set[str] = set()
        seen: set[str] = set()
        failed_runs = 0
        consecutive_no_improve = 0
        best_score: float | None = None

        record.status = OptimizationRunStatus.RUNNING
        record.updated_at = now_iso()
        record.nodes = []
        self._persist_record(record)
        self._emit(
            optimizer_run_id,
            "optimizer_started",
            baseline_run_id=record.baseline_run_id,
            baseline_version_id=record.baseline_version_id,
        )

        try:
            baseline = BacktestRunRecord(**self._persistence.load_backtest_run(record.baseline_run_id))
            baseline = freqtrade_runtime._reconcile_stale_backtest_run(baseline)

            base_state = freqtrade_runtime.results_svc.load_run_summary_state(baseline)
            base_summary = base_state.get("summary") if base_state.get("state") == "ready" else None
            base_metrics = (
                freqtrade_runtime.results_svc._normalize_summary_metrics(base_summary, baseline.strategy)
                if base_summary
                else None
            )

            failed = self._constraints_failed(base_metrics, record.thresholds)
            root = OptimizationNodeRecord(
                node_id="node-root",
                depth=0,
                parent_node_id=None,
                parent_version_id=None,
                parent_run_id=None,
                candidate_descriptor="baseline",
                candidate_version_id=record.baseline_version_id,
                run_id=record.baseline_run_id,
                status="completed",
                created_at=record.created_at,
                updated_at=record.created_at,
                completed_at=baseline.completed_at,
                summary_metrics=base_metrics or {},
                score=self._score(base_metrics),
                constraint_passed=len(failed) == 0,
                failed_constraints=failed,
                dedup_signature=None,
                dedup_reason=None,
                error=None,
            )
            nodes.append(root)
            record.nodes = nodes
            record.updated_at = now_iso()
            self._persist_record(record)
            self._emit(
                optimizer_run_id,
                "optimizer_baseline_loaded",
                node_id=root.node_id,
                run_id=root.run_id,
                version_id=root.candidate_version_id,
                summary_metrics=root.summary_metrics,
                score=root.score,
                constraint_passed=root.constraint_passed,
                failed_constraints=root.failed_constraints,
            )

            for attempt_index in range(1, int(record.attempts) + 1):
                frontier = self._frontier(nodes, beam_width=int(record.beam_width), expanded=expanded)
                if not frontier:
                    break

                self._emit(
                    optimizer_run_id,
                    "optimizer_attempt_started",
                    attempt_index=attempt_index,
                    frontier_node_ids=[n.node_id for n in frontier],
                )

                best_before = best_score

                for parent in frontier:
                    if record.hard_stops.max_total_nodes is not None and len(nodes) >= int(record.hard_stops.max_total_nodes):
                        self._finalize(
                            record,
                            nodes=nodes,
                            result_kind=OptimizationResultKind.HARD_STOP_TRIGGERED,
                            completion_reason=OptimizationCompletionReason.HARD_STOP_TRIGGERED,
                            event_type="optimizer_hard_stop_triggered",
                            hard_stop_reason="max_total_nodes",
                        )
                        return

                    if record.hard_stops.max_failed_runs is not None and failed_runs >= int(record.hard_stops.max_failed_runs):
                        self._finalize(
                            record,
                            nodes=nodes,
                            result_kind=OptimizationResultKind.HARD_STOP_TRIGGERED,
                            completion_reason=OptimizationCompletionReason.HARD_STOP_TRIGGERED,
                            event_type="optimizer_hard_stop_triggered",
                            hard_stop_reason="max_failed_runs",
                        )
                        return

                    expanded.add(parent.node_id)

                    parent_run_id = parent.run_id
                    parent_version_id = parent.candidate_version_id
                    if not parent_run_id or not parent_version_id:
                        continue

                    if mutation_service.get_version_by_id(str(parent_version_id)) is None:
                        continue

                    try:
                        diag_payload = await freqtrade_runtime.get_backtest_run_diagnosis(
                            str(parent_run_id),
                            include_ai=bool(record.include_ai_suggestions),
                        )
                    except Exception as exc:
                        self._emit(
                            optimizer_run_id,
                            "optimizer_parent_diagnosis_failed",
                            parent_node_id=parent.node_id,
                            run_id=parent_run_id,
                            error=str(exc),
                        )
                        continue

                    diagnosis = diag_payload.get("diagnosis") if isinstance(diag_payload, dict) else {}
                    ai_payload = diag_payload.get("ai") if isinstance(diag_payload, dict) else {}

                    base_params = self._resolve_base_params(baseline.strategy, str(parent_version_id))
                    seeds = self._candidate_seeds(
                        base_params=base_params,
                        diagnosis=diagnosis or {},
                        ai_payload=ai_payload or {},
                        branch_factor=int(record.branch_factor),
                        include_ai=bool(record.include_ai_suggestions),
                    )

                    for seed_index, (descriptor, params) in enumerate(seeds[: int(record.branch_factor)]):
                        if record.hard_stops.max_total_nodes is not None and len(nodes) >= int(record.hard_stops.max_total_nodes):
                            break

                        try:
                            _ = self._norm_json(params)
                        except Exception:
                            continue

                        signature = self._sig(
                            parent_version_id=str(parent_version_id),
                            descriptor=descriptor,
                            parameters=params,
                        )
                        node_id = f"node-{optimizer_run_id}-{attempt_index}-{parent.node_id}-{seed_index}"
                        now = now_iso()

                        if signature in seen:
                            node = OptimizationNodeRecord(
                                node_id=node_id,
                                depth=int(parent.depth) + 1,
                                parent_node_id=parent.node_id,
                                parent_version_id=str(parent_version_id),
                                parent_run_id=str(parent_run_id),
                                candidate_descriptor=descriptor,
                                candidate_version_id=None,
                                run_id=None,
                                status="deduped",
                                created_at=now,
                                updated_at=now,
                                completed_at=now,
                                summary_metrics={},
                                score=None,
                                constraint_passed=False,
                                failed_constraints=[],
                                dedup_signature=signature,
                                dedup_reason="normalized_duplicate_candidate",
                                error=None,
                            )
                            nodes.append(node)
                            record.nodes = nodes
                            record.updated_at = now_iso()
                            self._persist_record(record)
                            self._emit(
                                optimizer_run_id,
                                "candidate_deduped",
                                node_id=node.node_id,
                                dedup_signature=signature,
                                dedup_reason=node.dedup_reason,
                                candidate_descriptor=descriptor,
                            )
                            continue

                        seen.add(signature)

                        mutation = mutation_service.create_mutation(
                            MutationRequest(
                                strategy_name=baseline.strategy,
                                change_type=ChangeType.PARAMETER_CHANGE,
                                summary=f"Auto Optimize v1: {descriptor} (parent {parent_version_id})",
                                created_by="optimizer",
                                parameters=params,
                                parent_version_id=str(parent_version_id),
                                source_ref=f"backtest_run:{record.baseline_run_id}",
                                source_kind="optimizer_auto_optimize",
                                source_context={
                                    "run_id": record.baseline_run_id,
                                    "optimizer_run_id": optimizer_run_id,
                                    "candidate_descriptor": descriptor,
                                    "parent_node_id": parent.node_id,
                                    "parent_run_id": parent_run_id,
                                    "dedup_signature": signature,
                                },
                            )
                        )

                        version_id = mutation.version_id
                        node = OptimizationNodeRecord(
                            node_id=node_id,
                            depth=int(parent.depth) + 1,
                            parent_node_id=parent.node_id,
                            parent_version_id=str(parent_version_id),
                            parent_run_id=str(parent_run_id),
                            candidate_descriptor=descriptor,
                            candidate_version_id=version_id,
                            run_id=None,
                            status="staged",
                            created_at=now,
                            updated_at=now,
                            completed_at=None,
                            summary_metrics={},
                            score=None,
                            constraint_passed=False,
                            failed_constraints=[],
                            dedup_signature=signature,
                            dedup_reason=None,
                            error=None,
                        )
                        nodes.append(node)
                        record.nodes = nodes
                        record.updated_at = now_iso()
                        self._persist_record(record)
                        self._emit(
                            optimizer_run_id,
                            "candidate_version_created",
                            node_id=node.node_id,
                            version_id=version_id,
                            candidate_descriptor=descriptor,
                            dedup_signature=signature,
                        )

                        rs = record.request_snapshot or {}
                        run_payload = {
                            "strategy": rs.get("strategy"),
                            "timeframe": rs.get("timeframe"),
                            "timerange": rs.get("timerange"),
                            "pairs": list(rs.get("pairs") or []),
                            "exchange": rs.get("exchange") or "binance",
                            "max_open_trades": rs.get("max_open_trades"),
                            "dry_run_wallet": rs.get("dry_run_wallet"),
                            "config_path": rs.get("config_path"),
                            "extra_flags": list(rs.get("extra_flags") or []),
                            "version_id": version_id,
                            "trigger_source": "optimizer",
                        }

                        run_id = None
                        try:
                            launched = await freqtrade_runtime.run_backtest(BacktestRunRequest(**run_payload))
                            run_id = launched.get("run_id")
                        except Exception as exc:
                            failed_runs += 1
                            node.status = "failed"
                            node.updated_at = now_iso()
                            node.completed_at = node.updated_at
                            node.error = OptimizationError(
                                error_code="candidate_launch_failed",
                                error_stage="candidate_launch",
                                message=str(exc),
                                optimizer_run_id=optimizer_run_id,
                                run_id=None,
                                node_id=node.node_id,
                                details={"version_id": version_id, "candidate_descriptor": descriptor},
                                suggested_fix=None,
                            )
                            record.nodes = nodes
                            record.updated_at = node.updated_at
                            self._persist_record(record)
                            self._emit(
                                optimizer_run_id,
                                "candidate_run_failed",
                                node_id=node.node_id,
                                error=node.error.model_dump(mode="json"),
                            )
                            continue

                        node.run_id = run_id
                        node.status = "running"
                        node.updated_at = now_iso()
                        record.updated_at = node.updated_at
                        record.nodes = nodes
                        self._persist_record(record)
                        self._emit(
                            optimizer_run_id,
                            "backtest_run_launched",
                            node_id=node.node_id,
                            run_id=run_id,
                            version_id=version_id,
                        )

                        _, metrics, run_error = await self._wait_summary_ready(str(run_id))
                        node.updated_at = now_iso()
                        node.completed_at = node.updated_at

                        if run_error:
                            failed_runs += 1
                            node.status = "failed"
                            node.error = OptimizationError(
                                error_code="candidate_run_failed",
                                error_stage="candidate_backtest",
                                message=str(run_error),
                                optimizer_run_id=optimizer_run_id,
                                run_id=str(run_id),
                                node_id=node.node_id,
                                details={"version_id": version_id, "candidate_descriptor": descriptor},
                                suggested_fix=None,
                            )
                            self._emit(
                                optimizer_run_id,
                                "candidate_run_failed",
                                node_id=node.node_id,
                                run_id=run_id,
                                error=node.error.model_dump(mode="json"),
                            )
                        else:
                            node.status = "completed"
                            node.summary_metrics = metrics or {}
                            node.score = self._score(metrics)
                            node.failed_constraints = self._constraints_failed(metrics, record.thresholds)
                            node.constraint_passed = len(node.failed_constraints) == 0
                            if node.constraint_passed and node.score is not None:
                                best_score = max(best_score or node.score, node.score)

                            self._emit(
                                optimizer_run_id,
                                "candidate_run_completed",
                                node_id=node.node_id,
                                run_id=run_id,
                                summary_metrics=node.summary_metrics,
                                score=node.score,
                                constraint_passed=node.constraint_passed,
                                failed_constraints=node.failed_constraints,
                            )

                        record.nodes = nodes
                        record.updated_at = now_iso()
                        self._persist_record(record)

                if best_score is not None and (best_before is None or best_score > best_before):
                    consecutive_no_improve = 0
                else:
                    consecutive_no_improve += 1

                if consecutive_no_improve >= int(record.hard_stops.max_consecutive_no_improvement_attempts or 3):
                    self._finalize(
                        record,
                        nodes=nodes,
                        result_kind=OptimizationResultKind.HARD_STOP_TRIGGERED,
                        completion_reason=OptimizationCompletionReason.HARD_STOP_TRIGGERED,
                        event_type="optimizer_hard_stop_triggered",
                        hard_stop_reason="max_consecutive_no_improvement_attempts",
                    )
                    return

            if self._finalist_nodes(nodes):
                self._finalize(
                    record,
                    nodes=nodes,
                    result_kind=OptimizationResultKind.FINALISTS_FOUND,
                    completion_reason=OptimizationCompletionReason.FINALISTS_FOUND,
                    event_type="optimizer_completed",
                )
                return

            self._finalize(
                record,
                nodes=nodes,
                result_kind=OptimizationResultKind.NO_PROFITABLE_FINALISTS,
                completion_reason=OptimizationCompletionReason.NO_PROFITABLE_FINALISTS,
                event_type="optimizer_completed_no_finalists",
            )
            return

        except Exception as exc:
            err = OptimizationError(
                error_code="optimizer_loop_failed",
                error_stage="optimizer_loop",
                message=str(exc),
                optimizer_run_id=optimizer_run_id,
                details={"exception": str(exc)},
                suggested_fix="Check events.log and ensure baseline run artifacts exist.",
            )
            record.status = OptimizationRunStatus.FAILED
            record.result_kind = OptimizationResultKind.FATAL_ERROR
            record.completion_reason = OptimizationCompletionReason.FATAL_ERROR
            record.error = err
            record.completed_at = now_iso()
            record.updated_at = record.completed_at
            record.nodes = nodes
            self._persist_record(record)
            self._emit(optimizer_run_id, "optimizer_failed", error=err.model_dump(mode="json"))
            return


auto_optimize_service = AutoOptimizeService()


__all__ = [
    "AutoOptimizeFatalError",
    "AutoOptimizeService",
    "auto_optimize_service",
]