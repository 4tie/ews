"""
Strategy Intelligence Apply Service - Applies AI recommendations to strategies.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from app.services.ai_chat.apply_code_service import apply_code_patch, apply_parameters
from app.services.ai_chat.loop_service import LoopConfig, run_ai_loop
from app.services.config_service import ConfigService
from app.services.mutation_service import mutation_service
from app.utils.paths import live_strategy_file, strategy_config_file


@dataclass
class ApplyIntelligenceResult:
    success: bool
    message: str
    parameters_applied: dict | None = None
    code_applied: bool = False


@dataclass
class ProposalCandidateResult:
    success: bool
    message: str
    version_id: str | None = None
    candidate_change_type: str | None = None
    candidate_status: str | None = None
    source_title: str | None = None
    ai_mode: str | None = None
    error: str | None = None


_CONFIG_SVC = ConfigService()
_VALID_SOURCE_KINDS = {"ranked_issue", "parameter_hint", "ai_parameter_suggestion"}
_VALID_CANDIDATE_MODES = {"auto", "parameter_only", "code_patch"}


async def apply_strategy_recommendations(
    strategy_name: str,
    parameters: dict | None = None,
    code: str | None = None,
    strategy_dir: str | None = None,
) -> ApplyIntelligenceResult:
    """Create candidate versions from AI recommendations."""
    if parameters:
        result = await apply_parameters(
            strategy_name=strategy_name,
            parameters=parameters,
        )

        if not result.success:
            return ApplyIntelligenceResult(
                success=False,
                message=f"Failed to create parameter candidate: {result.error}",
                parameters_applied=None,
                code_applied=False,
            )

    if code:
        result = await apply_code_patch(
            strategy_name=strategy_name,
            code=code,
            strategy_dir=strategy_dir,
        )

        if not result.success:
            return ApplyIntelligenceResult(
                success=False,
                message=f"Failed to create code candidate: {result.error}",
                parameters_applied=parameters,
                code_applied=False,
            )

        return ApplyIntelligenceResult(
            success=True,
            message="Candidate version created for the recommended code changes.",
            parameters_applied=parameters,
            code_applied=True,
        )

    if parameters:
        return ApplyIntelligenceResult(
            success=True,
            message="Candidate version created for the recommended parameter changes.",
            parameters_applied=parameters,
            code_applied=False,
        )

    return ApplyIntelligenceResult(
        success=False,
        message="No changes to apply",
        parameters_applied=None,
        code_applied=False,
    )


async def create_proposal_candidate_from_diagnosis(
    *,
    strategy_name: str,
    run_id: str,
    linked_version: Any | None,
    request_snapshot: dict[str, Any] | None,
    summary_metrics: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    ai_payload: dict[str, Any] | None,
    source_kind: str,
    source_index: int,
    candidate_mode: str = "auto",
) -> ProposalCandidateResult:
    """Draft and stage a candidate version from a run-scoped diagnosis source."""
    if source_kind not in _VALID_SOURCE_KINDS:
        return ProposalCandidateResult(
            success=False,
            message="Invalid proposal source.",
            error=f"Unsupported source_kind: {source_kind}",
        )
    if candidate_mode not in _VALID_CANDIDATE_MODES:
        return ProposalCandidateResult(
            success=False,
            message="Invalid candidate mode.",
            error=f"Unsupported candidate_mode: {candidate_mode}",
        )
    if source_index < 0:
        return ProposalCandidateResult(
            success=False,
            message="Invalid proposal source index.",
            error="source_index must be >= 0",
        )

    source_item = _resolve_source_item(source_kind, source_index, diagnosis, ai_payload)
    if source_item is None:
        return ProposalCandidateResult(
            success=False,
            message="Proposal source could not be resolved.",
            error=f"No {source_kind} found at index {source_index}",
        )

    strategy_code = _resolve_strategy_code(strategy_name, linked_version)
    parameters_snapshot = _resolve_parameters_snapshot(strategy_name, linked_version)
    effective_mode = candidate_mode
    if effective_mode == "code_patch" and not strategy_code:
        return ProposalCandidateResult(
            success=False,
            message="Code candidate creation requires a strategy snapshot.",
            error="No strategy code snapshot is available for a code_patch proposal.",
        )
    if effective_mode == "auto" and not strategy_code:
        effective_mode = "parameter_only"

    source_title = _summarize_source_item(source_kind, source_item)
    prompt = _build_candidate_prompt(
        strategy_name=strategy_name,
        request_snapshot=request_snapshot or {},
        summary_metrics=summary_metrics or {},
        diagnosis=diagnosis or {},
        source_kind=source_kind,
        source_index=source_index,
        source_item=source_item,
        candidate_mode=effective_mode,
        linked_version=linked_version,
        parameters_snapshot=parameters_snapshot,
        code_available=bool(strategy_code),
    )
    backtest_context = {
        "summary_metrics": summary_metrics or {},
        "request_snapshot": request_snapshot or {},
        "diagnosis": {
            "primary_flags": (diagnosis or {}).get("primary_flags") or [],
            "ranked_issues": (diagnosis or {}).get("ranked_issues") or [],
            "parameter_hints": (diagnosis or {}).get("parameter_hints") or [],
            "facts": (diagnosis or {}).get("facts") or {},
        },
        "selected_source": {
            "kind": source_kind,
            "index": source_index,
            "title": source_title,
            "payload": source_item,
        },
        "current_parameters": parameters_snapshot or {},
    }

    loop_result = await run_ai_loop(
        user_message=prompt,
        strategy_name=strategy_name,
        strategy_code=strategy_code,
        backtest_results=backtest_context,
        config=LoopConfig(
            max_iterations=4,
            temperature=0.2,
            include_code=bool(strategy_code),
            include_backtest=True,
            include_optimizer=False,
        ),
    )
    if not loop_result.success:
        return ProposalCandidateResult(
            success=False,
            message="AI could not draft a candidate from this diagnosis item.",
            error=loop_result.error or "AI candidate drafting failed.",
            source_title=source_title,
        )

    if effective_mode == "parameter_only" and loop_result.final_code:
        return ProposalCandidateResult(
            success=False,
            message="AI returned a code candidate where a parameter-only candidate was required.",
            error="Unexpected code candidate for parameter_only mode.",
            source_title=source_title,
            ai_mode="code_patch",
        )
    if effective_mode == "code_patch" and loop_result.final_parameters:
        return ProposalCandidateResult(
            success=False,
            message="AI returned a parameter candidate where a code candidate was required.",
            error="Unexpected parameter candidate for code_patch mode.",
            source_title=source_title,
            ai_mode="parameter_only",
        )
    if loop_result.final_code and not strategy_code:
        return ProposalCandidateResult(
            success=False,
            message="AI returned a code candidate without a strategy code context.",
            error="No strategy code snapshot was available for code candidate generation.",
            source_title=source_title,
            ai_mode="code_patch",
        )

    candidate_summary = (
        f"AI proposal candidate from run {run_id} using {source_kind}[{source_index}]"
        f" ({source_title})"
    )
    parent_version_id = getattr(linked_version, "version_id", None)
    source_ref = f"backtest_run:{run_id}"

    if loop_result.final_parameters:
        apply_result = await apply_parameters(
            strategy_name=strategy_name,
            parameters=loop_result.final_parameters,
            created_by="ai_apply",
            summary=candidate_summary,
            source_ref=source_ref,
            parent_version_id=parent_version_id,
        )
        ai_mode = "parameter_only"
    elif loop_result.final_code:
        apply_result = await apply_code_patch(
            strategy_name=strategy_name,
            code=loop_result.final_code,
            created_by="ai_apply",
            summary=candidate_summary,
            source_ref=source_ref,
            parent_version_id=parent_version_id,
        )
        ai_mode = "code_patch"
    else:
        return ProposalCandidateResult(
            success=False,
            message="AI did not return a candidate payload.",
            error="No parameters or code candidate was returned.",
            source_title=source_title,
        )

    if not apply_result.success or not apply_result.version_id:
        return ProposalCandidateResult(
            success=False,
            message="Candidate version could not be staged.",
            error=apply_result.error or "Candidate staging failed.",
            source_title=source_title,
            ai_mode=ai_mode,
        )

    version = mutation_service.get_version_by_id(apply_result.version_id)
    change_type = getattr(getattr(version, "change_type", None), "value", None)
    status = getattr(getattr(version, "status", None), "value", None)

    return ProposalCandidateResult(
        success=True,
        message=apply_result.message or f"Candidate version {apply_result.version_id} created.",
        version_id=apply_result.version_id,
        candidate_change_type=change_type,
        candidate_status=status,
        source_title=source_title,
        ai_mode=ai_mode,
        error=None,
    )


def _resolve_source_item(
    source_kind: str,
    source_index: int,
    diagnosis: dict[str, Any] | None,
    ai_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    diagnosis = diagnosis or {}
    ai_payload = ai_payload or {}

    if source_kind == "ranked_issue":
        items = diagnosis.get("ranked_issues") or []
    elif source_kind == "parameter_hint":
        items = diagnosis.get("parameter_hints") or []
    else:
        items = ai_payload.get("parameter_suggestions") or []

    if not isinstance(items, list) or source_index >= len(items):
        return None

    item = items[source_index]
    return item if isinstance(item, dict) else {"value": item}


def _resolve_strategy_code(strategy_name: str, linked_version: Any | None) -> str | None:
    code_snapshot = getattr(linked_version, "code_snapshot", None)
    if isinstance(code_snapshot, str) and code_snapshot.strip():
        return code_snapshot

    settings = _CONFIG_SVC.get_settings()
    try:
        strategy_path = live_strategy_file(strategy_name, settings.get("user_data_path"))
    except Exception:
        return None
    if not strategy_path or not os.path.isfile(strategy_path):
        return None
    try:
        with open(strategy_path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def _resolve_parameters_snapshot(strategy_name: str, linked_version: Any | None) -> dict[str, Any] | None:
    snapshot = getattr(linked_version, "parameters_snapshot", None)
    if isinstance(snapshot, dict) and snapshot:
        return snapshot

    settings = _CONFIG_SVC.get_settings()
    try:
        config_path = strategy_config_file(strategy_name, settings.get("user_data_path"))
    except Exception:
        return None
    if not config_path or not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload else None


def _summarize_source_item(source_kind: str, item: dict[str, Any]) -> str:
    if source_kind == "ranked_issue":
        rule = str(item.get("rule") or "ranked issue")
        message = str(item.get("message") or "").strip()
        severity = str(item.get("severity") or "warning")
        return f"{rule} [{severity}]" + (f": {message}" if message else "")
    if source_kind == "parameter_hint":
        rule = str(item.get("rule") or "parameter hint")
        parameters = item.get("parameters") or []
        joined = ", ".join(str(param) for param in parameters if str(param).strip())
        return f"{rule}" + (f" -> {joined}" if joined else "")

    name = str(item.get("name") or item.get("parameter") or item.get("key") or "AI suggestion")
    value = item.get("value")
    reason = str(item.get("reason") or item.get("rationale") or item.get("summary") or "").strip()
    value_label = f" = {value}" if value not in (None, "") else ""
    return f"{name}{value_label}" + (f": {reason}" if reason else "")


def _build_candidate_prompt(
    *,
    strategy_name: str,
    request_snapshot: dict[str, Any],
    summary_metrics: dict[str, Any],
    diagnosis: dict[str, Any],
    source_kind: str,
    source_index: int,
    source_item: dict[str, Any],
    candidate_mode: str,
    linked_version: Any | None,
    parameters_snapshot: dict[str, Any] | None,
    code_available: bool,
) -> str:
    linked_version_id = getattr(linked_version, "version_id", None)
    linked_change_type = getattr(getattr(linked_version, "change_type", None), "value", None)

    mode_directive = {
        "auto": "Prefer a parameter-only candidate first. Use a code candidate only if the selected issue cannot be addressed credibly with parameters alone.",
        "parameter_only": "Return only a parameter-only candidate.",
        "code_patch": "Return only a code candidate.",
    }[candidate_mode]

    code_note = (
        "Strategy code snapshot is available, so code changes are allowed when necessary."
        if code_available
        else "No strategy code snapshot is available, so stay in parameter-only territory."
    )

    prompt_sections = [
        f"Draft one concrete candidate mutation for strategy {strategy_name}.",
        "This candidate will be staged as a new version only. It will not be promoted automatically.",
        mode_directive,
        code_note,
        "Keep the change narrow and directly tied to the selected diagnosis source.",
        "Do not describe rollout steps, testing steps, or promotion steps. Return only the strict two-mode output.",
        f"Selected proposal source: {source_kind}[{source_index}]",
        f"Source payload: {json.dumps(source_item, indent=2, sort_keys=True)}",
        f"Run request snapshot: {json.dumps(request_snapshot, indent=2, sort_keys=True)}",
        f"Persisted summary metrics: {json.dumps(summary_metrics, indent=2, sort_keys=True)}",
        f"Deterministic diagnosis facts: {json.dumps((diagnosis or {}).get('facts') or {}, indent=2, sort_keys=True)}",
        f"Primary flags: {json.dumps((diagnosis or {}).get('primary_flags') or [], indent=2, sort_keys=True)}",
        f"Current parameters snapshot: {json.dumps(parameters_snapshot or {}, indent=2, sort_keys=True)}",
        f"Linked version id: {linked_version_id or 'unavailable'}",
        f"Linked version change type: {linked_change_type or 'unavailable'}",
    ]
    return "

".join(prompt_sections)


__all__ = [
    "ApplyIntelligenceResult",
    "ProposalCandidateResult",
    "apply_strategy_recommendations",
    "create_proposal_candidate_from_diagnosis",
]
