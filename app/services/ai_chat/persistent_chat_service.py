"""Persistent AI chat orchestration for the shared drawer."""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.ai.pipelines.classifier import classify_with_fallback
from app.freqtrade import runtime as freqtrade_runtime
from app.services.ai_chat.loop_service import LoopConfig, run_ai_loop
from app.services.mutation_service import mutation_service
from app.services.persistence_service import PersistenceService
from app.services.results.strategy_intelligence_service import analyze_metrics, analyze_strategy
from app.utils.datetime_utils import now_iso


ACTIVE_JOB_STATUSES = {"queued", "running"}
TERMINAL_JOB_STATUSES = {"completed", "failed", "interrupted"}
MAX_HISTORY_ITEMS = 6


class PersistentAiChatService:
    def __init__(self) -> None:
        self.persistence = PersistenceService()
        self._tasks: dict[str, asyncio.Task] = {}

    def get_thread(self, strategy_name: str) -> dict[str, Any]:
        strategy = str(strategy_name or "").strip()
        thread = self._load_thread(strategy)
        active_job = None

        active_job_id = thread.get("active_job_id")
        if active_job_id:
            job = self._load_job(active_job_id)
            if job:
                job = self._reconcile_job(thread, job)
                if job.get("status") in ACTIVE_JOB_STATUSES:
                    active_job = job
            else:
                thread["active_job_id"] = None
                thread["updated_at"] = now_iso()
                self._save_thread(thread)

        return {
            "strategy_name": strategy,
            "messages": thread.get("messages", []),
            "latest_context": thread.get("latest_context", {}),
            "active_job": active_job,
        }

    async def enqueue_message(self, strategy_name: str, message_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        strategy = str(strategy_name or "").strip()
        message = str(message_text or "").strip()
        if not strategy:
            raise ValueError("Strategy name is required")
        if not message:
            raise ValueError("Message is required")

        thread = self._load_thread(strategy)
        active_job_id = thread.get("active_job_id")
        if active_job_id:
            active_job = self._load_job(active_job_id)
            if active_job:
                active_job = self._reconcile_job(thread, active_job)
                if active_job.get("status") in ACTIVE_JOB_STATUSES:
                    raise RuntimeError("An AI request is already running for this strategy")

        normalized_context = self._normalize_context(strategy, context or thread.get("latest_context") or {})
        job_id = self._new_job_id()

        user_message = self._build_message(
            role="user",
            strategy_name=strategy,
            text=message,
            title="You",
            meta="analysis request",
            context=normalized_context,
            job_id=job_id,
            resolved_mode="auto",
        )

        now = now_iso()
        thread.setdefault("messages", []).append(user_message)
        thread["latest_context"] = normalized_context
        thread["active_job_id"] = job_id
        thread["updated_at"] = now
        self._save_thread(thread)

        job = {
            "job_id": job_id,
            "strategy_name": strategy,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
            "user_message_id": user_message["id"],
            "assistant_message_id": None,
            "run_id": normalized_context.get("run_id"),
            "version_id": normalized_context.get("version_id"),
            "version_source": normalized_context.get("version_source"),
            "resolved_mode": "auto",
            "resolved_provider": None,
            "resolved_model": None,
            "error": None,
            "timeline_events": [],
            "event_seq": 0,
        }
        self._save_job(job)
        self._append_job_event(job, "queued", message="AI request queued.")
        self._start_job(job_id)
        return {"job_id": job_id}

    def get_job(self, job_id: str) -> dict[str, Any]:
        job = self._load_job(job_id)
        if not job:
            return {}

        thread = self._load_thread(job.get("strategy_name") or "")
        job = self._reconcile_job(thread, job)
        assistant_message = self._find_message(thread, job.get("assistant_message_id")) if job.get("assistant_message_id") else None
        return {
            "job": job,
            "assistant_message": assistant_message,
        }

    def get_job_timeline(self, job_id: str) -> list[dict[str, Any]]:
        job = self.get_job(job_id).get("job") or {}
        events = job.get("timeline_events")
        return events if isinstance(events, list) else []

    def _start_job(self, job_id: str) -> None:
        loop = asyncio.get_running_loop()
        task = loop.create_task(self._run_job(job_id))
        self._tasks[job_id] = task

        def _cleanup(completed: asyncio.Task) -> None:
            self._tasks.pop(job_id, None)
            try:
                completed.result()
            except Exception:
                pass

        task.add_done_callback(_cleanup)

    async def _run_job(self, job_id: str) -> None:
        job = self._load_job(job_id)
        if not job:
            return

        strategy = str(job.get("strategy_name") or "").strip()
        thread = self._load_thread(strategy)
        user_message = self._find_message(thread, job.get("user_message_id"))
        if not user_message:
            self._fail_job(job, thread, "The queued AI request could not be reconstructed.")
            return

        job["status"] = "running"
        job["updated_at"] = now_iso()
        self._save_job(job)
        job = self._append_job_event(job, "started", message="AI request started.")

        try:
            classification = await classify_with_fallback(user_message.get("text") or "")
            job = self._append_job_event(
                job_id,
                "classified",
                task_types=list(getattr(classification, "task_types", []) or []),
                complexity=str(getattr(classification, "complexity", "medium") or "medium"),
                recommended_pipeline=str(getattr(classification, "recommended_pipeline", "simple") or "simple"),
                requires_code=bool(getattr(classification, "requires_code", False)),
                requires_structured_out=bool(getattr(classification, "requires_structured_out", False)),
            )

            requested_mode = self._resolve_requested_mode(user_message.get("text") or "", classification)
            resolved_context = await self._resolve_runtime_context(strategy, thread.get("latest_context") or {})
            prompt = self._build_conversation_prompt(
                thread=thread,
                latest_request=user_message.get("text") or "",
                current_message_id=user_message.get("id") or "",
                context=resolved_context,
                mode=requested_mode,
            )

            async def _timeline_callback(payload: dict[str, Any]) -> None:
                event_type = str(payload.get("type") or "route_selected")
                data = {key: value for key, value in payload.items() if key != "type"}
                self._append_job_event(job_id, event_type, **data)

            if requested_mode == "candidate":
                loop_result = await run_ai_loop(
                    user_message=prompt,
                    strategy_name=strategy,
                    strategy_code=resolved_context.get("strategy_code"),
                    backtest_results=resolved_context.get("backtest_results"),
                    config=LoopConfig(max_iterations=4, temperature=0.25),
                    timeline_callback=_timeline_callback,
                )
                if not loop_result.success:
                    raise RuntimeError(loop_result.error or "AI could not produce a valid candidate.")

                resolved_mode = "parameter_only" if loop_result.final_parameters else "code_patch"
                assistant_message = self._build_message(
                    role="assistant",
                    strategy_name=strategy,
                    text=(
                        "AI returned a parameter-only candidate. Review it before creating a candidate version."
                        if resolved_mode == "parameter_only"
                        else "AI returned a code candidate. Review it before creating a candidate version."
                    ),
                    title="AI Candidate",
                    meta=f"{self._labelize(resolved_mode)} | {len(loop_result.iterations)} iteration(s)",
                    parameters=loop_result.final_parameters,
                    code=loop_result.final_code,
                    context=resolved_context,
                    job_id=job_id,
                    resolved_mode=resolved_mode,
                )
            else:
                strategy_code = resolved_context.get("strategy_code")
                backtest_results = resolved_context.get("backtest_results") or {}
                if strategy_code:
                    result = await analyze_strategy(
                        strategy_name=strategy,
                        strategy_code=strategy_code,
                        backtest_results=backtest_results,
                        user_question=prompt,
                        timeline_callback=_timeline_callback,
                    )
                    assistant_message = self._build_message(
                        role="assistant",
                        strategy_name=strategy,
                        text=str(result.analysis or "AI did not return analysis text.").strip() or "AI did not return analysis text.",
                        title="AI Analysis",
                        meta="code-aware analysis",
                        recommendations=result.recommendations,
                        parameters=result.parameters,
                        note=(
                            "AI referenced code changes. Ask for a candidate to stage a versioned patch safely."
                            if result.code_suggestions
                            else ""
                        ),
                        context=resolved_context,
                        job_id=job_id,
                        resolved_mode="analysis",
                    )
                else:
                    result = await analyze_metrics(
                        metrics=backtest_results,
                        context=prompt,
                        timeline_callback=_timeline_callback,
                    )
                    assistant_message = self._build_message(
                        role="assistant",
                        strategy_name=strategy,
                        text=str(result.analysis or "AI did not return analysis text.").strip() or "AI did not return analysis text.",
                        title="AI Analysis",
                        meta="metrics-aware analysis",
                        recommendations=result.recommendations,
                        parameters=result.parameters,
                        context=resolved_context,
                        job_id=job_id,
                        resolved_mode="analysis",
                    )
                resolved_mode = "analysis"

            thread = self._load_thread(strategy)
            thread.setdefault("messages", []).append(assistant_message)
            thread["active_job_id"] = None
            thread["latest_context"] = self._context_snapshot(resolved_context)
            thread["updated_at"] = now_iso()
            self._save_thread(thread)

            job = self._load_job(job_id)
            if not job:
                return
            job["status"] = "completed"
            job["updated_at"] = now_iso()
            job["completed_at"] = job["updated_at"]
            job["assistant_message_id"] = assistant_message["id"]
            job["run_id"] = assistant_message.get("run_id")
            job["version_id"] = assistant_message.get("version_id")
            job["version_source"] = assistant_message.get("version_source")
            job["resolved_mode"] = resolved_mode
            job["error"] = None
            self._save_job(job)
            self._append_job_event(
                job,
                "completed",
                message="AI response ready.",
                resolved_mode=resolved_mode,
                provider=job.get("resolved_provider"),
                model=job.get("resolved_model"),
            )
        except Exception as exc:
            thread = self._load_thread(strategy)
            job = self._load_job(job_id)
            if job:
                self._fail_job(job, thread, str(exc))

    def _fail_job(self, job: dict[str, Any], thread: dict[str, Any], error_text: str, *, interrupted: bool = False) -> dict[str, Any]:
        message = self._build_message(
            role="system",
            strategy_name=job.get("strategy_name") or thread.get("strategy_name") or "",
            text=str(error_text or "AI request failed."),
            title="AI Interrupted" if interrupted else "AI Error",
            context=thread.get("latest_context") or {},
            job_id=job.get("job_id"),
            resolved_mode=job.get("resolved_mode") or "auto",
        )

        thread.setdefault("messages", []).append(message)
        if thread.get("active_job_id") == job.get("job_id"):
            thread["active_job_id"] = None
        thread["updated_at"] = now_iso()
        self._save_thread(thread)

        job["status"] = "interrupted" if interrupted else "failed"
        job["updated_at"] = now_iso()
        job["completed_at"] = job["updated_at"]
        job["assistant_message_id"] = message["id"]
        job["error"] = str(error_text or "AI request failed.")
        self._save_job(job)
        self._append_job_event(
            job,
            "failed",
            message=str(error_text or "AI request failed."),
            interrupted=interrupted,
            provider=job.get("resolved_provider"),
            model=job.get("resolved_model"),
        )
        return job

    def _append_job_event(self, job_or_id: dict[str, Any] | str, event_type: str, **payload: Any) -> dict[str, Any]:
        if isinstance(job_or_id, dict):
            job = job_or_id
        else:
            job = self._load_job(job_or_id)
        if not job:
            return {}

        job_id = str(job.get("job_id") or "").strip()
        if not job_id:
            return job

        sequence = int(job.get("event_seq") or 0) + 1
        event = {
            "id": f"{job_id}:{sequence}",
            "seq": sequence,
            "type": str(event_type or "status").strip() or "status",
            "created_at": now_iso(),
        }
        for key, value in payload.items():
            if value is None:
                continue
            event[key] = value

        job.setdefault("timeline_events", []).append(event)
        job["event_seq"] = sequence
        if event.get("provider"):
            job["resolved_provider"] = event.get("provider")
        if event.get("model"):
            job["resolved_model"] = event.get("model")
        job["updated_at"] = now_iso()
        self._save_job(job)
        return job

    async def _resolve_runtime_context(self, strategy_name: str, context: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_context(strategy_name, context)
        response = None
        run_id = normalized.get("run_id")
        if run_id:
            try:
                response = await freqtrade_runtime.get_backtest_run_diagnosis(run_id, include_ai=False)
                response_strategy = str(response.get("strategy") or "").strip()
                if response_strategy and response_strategy != strategy_name:
                    response = None
            except Exception:
                response = None

        if response:
            normalized["run_id"] = response.get("run_id")
            normalized["version_id"] = response.get("version_id") or normalized.get("version_id")
            normalized["diagnosis_status"] = response.get("diagnosis_status")
            normalized["summary_available"] = bool(response.get("summary_available"))

        resolved_version = None
        version_source = str(normalized.get("version_source") or "").strip()
        version_id = normalized.get("version_id")
        if version_id:
            resolved_version = mutation_service.get_version_by_id(version_id)
            if resolved_version is not None:
                version_source = version_source or "run"

        if resolved_version is None:
            resolved_version = mutation_service.get_active_version(strategy_name)
            if resolved_version is not None:
                normalized["version_id"] = getattr(resolved_version, "version_id", None)
                version_source = "active"

        normalized["version_source"] = version_source or "none"
        return {
            **normalized,
            "strategy_code": getattr(resolved_version, "code_snapshot", None) if resolved_version is not None else None,
            "backtest_results": self._build_ai_backtest_results(response),
        }

    def _resolve_requested_mode(self, message_text: str, classification: Any) -> str:
        task_types = {str(item or "").strip().lower() for item in getattr(classification, "task_types", [])}
        recommended_pipeline = str(getattr(classification, "recommended_pipeline", "") or "").strip().lower()
        lower_text = str(message_text or "").lower()
        candidate_markers = (
            "candidate",
            "code change",
            "patch",
            "generate a change",
            "create a version",
            "parameter candidate",
            "code candidate",
            "improve exits",
        )

        if getattr(classification, "requires_structured_out", False) or getattr(classification, "requires_code", False):
            return "candidate"
        if recommended_pipeline in {"code", "structured"}:
            return "candidate"
        if task_types & {"code_generation", "structured_output"}:
            return "candidate"
        if any(marker in lower_text for marker in candidate_markers):
            return "candidate"
        return "analysis"

    def _build_conversation_prompt(
        self,
        *,
        thread: dict[str, Any],
        latest_request: str,
        current_message_id: str,
        context: dict[str, Any],
        mode: str,
    ) -> str:
        history_lines = []
        for message in thread.get("messages", []):
            if message.get("id") == current_message_id or message.get("role") == "system":
                continue
            summary = self._summarize_history_entry(message)
            if not summary:
                continue
            role = "User" if message.get("role") == "user" else "Assistant"
            history_lines.append(f"{role}: {summary}")

        history = "\n\n".join(history_lines[-MAX_HISTORY_ITEMS:])
        context_lines = []
        if context.get("run_id"):
            context_lines.append(f"Latest run id: {context['run_id']}")
        if context.get("version_id"):
            context_lines.append(f"Resolved version id: {context['version_id']}")
        if context.get("version_source"):
            context_lines.append(f"Version source: {context['version_source']}")
        if context.get("diagnosis_status"):
            context_lines.append(f"Diagnosis status: {context['diagnosis_status']}")
        if context.get("summary_available"):
            context_lines.append("Latest persisted run summary is available.")

        parts = []
        if history:
            parts.append(f"Conversation so far:\n{history}")
        if context_lines:
            parts.append("Current UI context:\n" + "\n".join(context_lines))
        parts.append(f"Latest user request:\n{str(latest_request or '').strip()}")
        parts.append(
            "Return a concrete candidate change grounded in the current strategy and latest result. Prefer parameter-only changes when possible."
            if mode == "candidate"
            else "Stay grounded in the current strategy and latest result context. Be specific and actionable."
        )
        return "\n\n".join(part for part in parts if part)
    def _build_ai_backtest_results(self, response: dict[str, Any] | None) -> dict[str, Any]:
        payload = response if isinstance(response, dict) else {}
        summary_metrics = payload.get("summary_metrics") if isinstance(payload.get("summary_metrics"), dict) else {}
        diagnosis = payload.get("diagnosis") if isinstance(payload.get("diagnosis"), dict) else {}
        results_per_pair = payload.get("results_per_pair") if isinstance(payload.get("results_per_pair"), list) else []

        return {
            "total_profit": summary_metrics.get("profit_total_abs") or summary_metrics.get("absolute_profit"),
            "profit_ratio": summary_metrics.get("profit_total_pct") or summary_metrics.get("total_profit_pct"),
            "win_rate": summary_metrics.get("win_rate") or summary_metrics.get("winrate"),
            "max_drawdown": (
                summary_metrics.get("max_drawdown")
                or summary_metrics.get("max_drawdown_account")
                or summary_metrics.get("drawdown")
                or summary_metrics.get("max_drawdown_pct")
            ),
            "profit_factor": summary_metrics.get("profit_factor"),
            "sharpe": summary_metrics.get("sharpe"),
            "sortino": summary_metrics.get("sortino"),
            "total_trades": summary_metrics.get("total_trades"),
            "avg_trade": summary_metrics.get("avg_profit_pct") or summary_metrics.get("avg_trade"),
            "calmar": summary_metrics.get("calmar"),
            "run_id": payload.get("run_id"),
            "version_id": payload.get("version_id"),
            "diagnosis_status": payload.get("diagnosis_status"),
            "primary_flags": [
                flag.get("message") or flag.get("rule")
                for flag in diagnosis.get("primary_flags", [])
                if isinstance(flag, dict) and (flag.get("message") or flag.get("rule"))
            ][:4],
            "parameter_hints": diagnosis.get("parameter_hints", [])[:4] if isinstance(diagnosis.get("parameter_hints"), list) else [],
            "top_pairs": [
                {
                    "pair": row.get("key"),
                    "profit_pct": row.get("profit_total_pct"),
                    "trades": row.get("trades"),
                }
                for row in results_per_pair
                if isinstance(row, dict) and row.get("key") and row.get("key") != "TOTAL"
            ][:4],
        }

    def _summarize_history_entry(self, message: dict[str, Any]) -> str:
        parameters = message.get("parameters")
        if isinstance(parameters, dict) and parameters:
            return f"Structured parameter suggestion: {self._compact_text(str(parameters))}"
        if message.get("code"):
            return "Structured code candidate returned for the current strategy."
        return self._compact_text(message.get("text") or "")

    def _compact_text(self, value: Any, max_length: int = 700) -> str:
        text = str(value or "").strip()
        if len(text) <= max_length:
            return text
        return f"{text[:max_length]}..."

    def _labelize(self, value: Any) -> str:
        return str(value or "unknown").replace("_", " ")

    def _normalize_context(self, strategy_name: str, context: dict[str, Any]) -> dict[str, Any]:
        payload = context if isinstance(context, dict) else {}
        return {
            "strategy_name": strategy_name,
            "run_id": payload.get("run_id") or None,
            "version_id": payload.get("version_id") or None,
            "version_source": payload.get("version_source") or "none",
            "diagnosis_status": payload.get("diagnosis_status") or None,
            "summary_available": bool(payload.get("summary_available")),
        }

    def _context_snapshot(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._normalize_context(str(context.get("strategy_name") or "").strip(), context)

    def _build_message(
        self,
        *,
        role: str,
        strategy_name: str,
        text: str,
        title: str,
        context: dict[str, Any],
        meta: str = "",
        note: str = "",
        recommendations: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        code: str | None = None,
        analysis_payload: dict[str, Any] | None = None,
        provider: str | None = None,
        model: str | None = None,
        job_id: str | None = None,
        resolved_mode: str | None = None,
    ) -> dict[str, Any]:
        created_at = now_iso()
        return {
            "id": self._new_message_id(),
            "role": role,
            "title": title,
            "text": str(text or "").strip(),
            "meta": str(meta or "").strip(),
            "note": str(note or "").strip(),
            "recommendations": [str(item).strip() for item in (recommendations or []) if str(item).strip()],
            "parameters": parameters if isinstance(parameters, dict) and parameters else None,
            "code": str(code or "").strip() or None,
            "analysis_payload": analysis_payload if isinstance(analysis_payload, dict) and analysis_payload else None,
            "provider": str(provider or "").strip() or None,
            "model": str(model or "").strip() or None,
            "strategy_name": strategy_name,
            "run_id": context.get("run_id"),
            "version_id": context.get("version_id"),
            "version_source": context.get("version_source"),
            "resolved_mode": resolved_mode,
            "job_id": job_id,
            "created_at": created_at,
        }
    def _default_thread(self, strategy_name: str) -> dict[str, Any]:
        now = now_iso()
        return {
            "strategy_name": strategy_name,
            "created_at": now,
            "updated_at": now,
            "latest_context": self._normalize_context(strategy_name, {}),
            "messages": [],
            "active_job_id": None,
        }

    def _load_thread(self, strategy_name: str) -> dict[str, Any]:
        strategy = str(strategy_name or "").strip()
        if not strategy:
            return self._default_thread("")

        raw = self.persistence.load_ai_chat_thread(strategy)
        if not isinstance(raw, dict) or not raw:
            return self._default_thread(strategy)

        thread = self._default_thread(strategy)
        thread["created_at"] = raw.get("created_at") or thread["created_at"]
        thread["updated_at"] = raw.get("updated_at") or thread["updated_at"]
        thread["latest_context"] = self._normalize_context(strategy, raw.get("latest_context") or {})
        thread["messages"] = [message for message in raw.get("messages", []) if isinstance(message, dict)]
        thread["active_job_id"] = raw.get("active_job_id") or None
        return thread

    def _save_thread(self, thread: dict[str, Any]) -> None:
        strategy = str(thread.get("strategy_name") or "").strip()
        if not strategy:
            return
        self.persistence.save_ai_chat_thread(strategy, thread)

    def _load_job(self, job_id: str) -> dict[str, Any]:
        raw = self.persistence.load_ai_chat_job(job_id)
        if not isinstance(raw, dict):
            return {}
        raw.setdefault("timeline_events", [])
        raw.setdefault("event_seq", 0)
        raw.setdefault("resolved_provider", None)
        raw.setdefault("resolved_model", None)
        return raw

    def _save_job(self, job: dict[str, Any]) -> None:
        job_id = str(job.get("job_id") or "").strip()
        if not job_id:
            return
        self.persistence.save_ai_chat_job(job_id, job)

    def _find_message(self, thread: dict[str, Any], message_id: str | None) -> dict[str, Any] | None:
        target_id = str(message_id or "").strip()
        if not target_id:
            return None
        for message in thread.get("messages", []):
            if message.get("id") == target_id:
                return message
        return None

    def _reconcile_job(self, thread: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("job_id") or "").strip()
        if job.get("status") not in ACTIVE_JOB_STATUSES:
            return job
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            return job
        return self._fail_job(job, thread, "The previous AI request was interrupted before it completed.", interrupted=True)

    def _new_message_id(self) -> str:
        return f"ai-chat-msg-{uuid.uuid4().hex[:10]}"

    def _new_job_id(self) -> str:
        return f"aic-{uuid.uuid4().hex[:8]}"


persistent_ai_chat_service = PersistentAiChatService()


__all__ = ["PersistentAiChatService", "persistent_ai_chat_service", "ACTIVE_JOB_STATUSES", "TERMINAL_JOB_STATUSES"]




