"""
Strategy Intelligence Apply Service - Applies deterministic and AI-backed proposal candidates.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any

from app.models.optimizer_models import ChangeType, MutationRequest
from app.freqtrade.runtime import load_live_strategy_code, load_live_strategy_parameters
from app.services.ai_chat.loop_service import LoopConfig, run_ai_loop
from app.services.mutation_service import mutation_service


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


_VALID_SOURCE_KINDS = {
    "ranked_issue",
    "parameter_hint",
    "ai_parameter_suggestion",
    "deterministic_action",
    "ai_chat_draft",
}
_VALID_CANDIDATE_MODES = {"auto", "parameter_only", "code_patch"}
_ACTION_ALIASES = {
    "accelerate_exits": "review_exit_timing",
}


def _normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _build_source_context(
    *,
    run_id: str,
    source_kind: str,
    action_type: str | None = None,
    source_item: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {"run_id": run_id}
    if action_type:
        context["action_type"] = action_type

    source_item = source_item or {}
    rule = str(source_item.get("rule") or "").strip()
    if source_kind in {"ranked_issue", "parameter_hint"}:
        if rule:
            context["rule"] = rule
            context["flag_rule"] = rule
    elif source_kind == "deterministic_action":
        matched_rules = _normalize_string_list(source_item.get("matched_rules"))
        context["matched_rules"] = matched_rules
        if len(matched_rules) == 1:
            context["flag_rule"] = matched_rules[0]

    if isinstance(extra, dict):
        for key, value in extra.items():
            if value in (None, "", [], {}):
                continue
            context[key] = value

    return context


async def apply_strategy_recommendations(
    strategy_name: str,
    parameters: dict | None = None,
    code: str | None = None,
    strategy_dir: str | None = None,
) -> ApplyIntelligenceResult:
    """Create candidate versions from AI recommendations without touching live files."""
    if parameters:
        parameter_result = _stage_candidate_mutation(
            strategy_name=strategy_name,
            linked_version=mutation_service.get_active_version(strategy_name),
            summary=f"AI parameter recommendation for {strategy_name}",
            created_by="ai_apply",
            parameters=parameters,
        )
        if not parameter_result.success:
            return ApplyIntelligenceResult(
                success=False,
                message=parameter_result.error or parameter_result.message,
                parameters_applied=None,
                code_applied=False,
            )

    if code:
        code_result = _stage_candidate_mutation(
            strategy_name=strategy_name,
            linked_version=mutation_service.get_active_version(strategy_name),
            summary=f"AI code recommendation for {strategy_name}",
            created_by="ai_apply",
            code=code,
        )
        if not code_result.success:
            return ApplyIntelligenceResult(
                success=False,
                message=code_result.error or code_result.message,
                parameters_applied=parameters,
                code_applied=False,
            )
        return ApplyIntelligenceResult(
            success=True,
            message=code_result.message,
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


def _stage_candidate_mutation(
    *,
    strategy_name: str,
    linked_version: Any | None,
    summary: str,
    created_by: str,
    parameters: dict[str, Any] | None = None,
    code: str | None = None,
    source_ref: str | None = None,
    source_kind: str | None = None,
    source_context: dict[str, Any] | None = None,
    source_title: str | None = None,
    ai_mode: str | None = None,
) -> ProposalCandidateResult:
    if not isinstance(parameters, dict):
        parameters = None
    if not isinstance(code, str) or not code.strip():
        code = None

    if parameters is None and code is None:
        return ProposalCandidateResult(
            success=False,
            message="Candidate payload is empty.",
            error="At least one of parameters or code must be provided.",
            source_title=source_title,
            ai_mode=ai_mode,
        )

    change_type = ChangeType.CODE_CHANGE if code is not None else ChangeType.PARAMETER_CHANGE
    parent_version_id = getattr(linked_version, "version_id", None)
    mutation_result = mutation_service.create_mutation(
        MutationRequest(
            strategy_name=strategy_name,
            change_type=change_type,
            summary=summary,
            created_by=created_by,
            code=code,
            parameters=parameters,
            parent_version_id=parent_version_id,
            source_ref=source_ref,
            source_kind=source_kind,
            source_context=dict(source_context or {}),
        )
    )
    if not mutation_result.version_id:
        return ProposalCandidateResult(
            success=False,
            message="Candidate version could not be staged.",
            error=mutation_result.message or "Mutation service error.",
            source_title=source_title,
            ai_mode=ai_mode,
        )

    version = mutation_service.get_version_by_id(mutation_result.version_id)
    return ProposalCandidateResult(
        success=True,
        message=mutation_result.message or f"Candidate version {mutation_result.version_id} created.",
        version_id=mutation_result.version_id,
        candidate_change_type=getattr(getattr(version, "change_type", None), "value", None),
        candidate_status=getattr(getattr(version, "status", None), "value", None),
        source_title=source_title,
        ai_mode=ai_mode,
        error=None,
    )


def _resolve_effective_artifacts(strategy_name: str, linked_version: Any | None) -> dict[str, Any]:
    version_id = getattr(linked_version, "version_id", None)
    if version_id:
        try:
            resolved = mutation_service.resolve_effective_artifacts(str(version_id))
            if isinstance(resolved, dict):
                return resolved
        except Exception:
            pass

    return {
        "strategy_name": strategy_name,
        "code_snapshot": None,
        "parameters_snapshot": None,
    }


def _resolve_strategy_code(strategy_name: str, linked_version: Any | None) -> str | None:
    resolved = _resolve_effective_artifacts(strategy_name, linked_version)
    code_snapshot = resolved.get("code_snapshot")
    if isinstance(code_snapshot, str) and code_snapshot.strip():
        return code_snapshot

    return load_live_strategy_code(strategy_name)


def _resolve_parameters_snapshot(strategy_name: str, linked_version: Any | None) -> dict[str, Any] | None:
    resolved = _resolve_effective_artifacts(strategy_name, linked_version)
    snapshot = resolved.get("parameters_snapshot")
    if isinstance(snapshot, dict) and snapshot:
        return copy.deepcopy(snapshot)

    live_parameters = load_live_strategy_parameters(strategy_name)
    if isinstance(live_parameters, dict) and live_parameters:
        return copy.deepcopy(live_parameters)
    return None


async def _apply_tighten_entries_action(
    strategy_name: str,
    parameters_snapshot: dict[str, Any] | None,
    run_id: str,
    linked_version: Any | None,
    source_kind: str,
    source_context: dict[str, Any] | None = None,
) -> ProposalCandidateResult:
    if not parameters_snapshot:
        return ProposalCandidateResult(
            success=False,
            message="No parameters snapshot available for tighten_entries action.",
            error="Parameters snapshot required but not found.",
        )

    modified_params = copy.deepcopy(parameters_snapshot)
    changed = False

    for key in ("entry_trigger", "buy_rsi", "buy_threshold", "entry_threshold"):
        if key not in modified_params or not isinstance(modified_params[key], (int, float)):
            continue
        if "rsi" in key.lower():
            modified_params[key] = min(float(modified_params[key]) + 5.0, 100.0)
            changed = True
        elif float(modified_params[key]) > 0:
            modified_params[key] = float(modified_params[key]) * 1.1
            changed = True

    if not changed:
        return ProposalCandidateResult(
            success=False,
            message="No recognized entry threshold parameters found to tighten.",
            error="Strategy parameters do not contain supported entry threshold keys.",
        )

    return _stage_candidate_mutation(
        strategy_name=strategy_name,
        linked_version=linked_version,
        summary=f"Deterministic action: tighten entries (from diagnosis run {run_id})",
        created_by="deterministic_proposal",
        parameters=modified_params,
        source_ref=f"backtest_run:{run_id}",
        source_kind=source_kind,
        source_context=source_context,
        source_title="Tighten Entries",
    )


async def _apply_reduce_weak_pairs_action(
    strategy_name: str,
    parameters_snapshot: dict[str, Any] | None,
    diagnosis: dict[str, Any] | None,
    run_id: str,
    linked_version: Any | None,
    source_kind: str,
    source_context: dict[str, Any] | None = None,
) -> ProposalCandidateResult:
    if not parameters_snapshot:
        return ProposalCandidateResult(
            success=False,
            message="No parameters snapshot available for reduce_weak_pairs action.",
            error="Parameters snapshot required but not found.",
        )

    worst_pair = None
    if isinstance((diagnosis or {}).get("facts"), dict):
        worst_pair = (diagnosis or {})["facts"].get("worst_pair")
    if not worst_pair:
        return ProposalCandidateResult(
            success=False,
            message="Could not identify a weak pair from diagnosis.",
            error="Diagnosis facts do not contain worst_pair.",
        )

    modified_params = copy.deepcopy(parameters_snapshot)
    excluded_pairs = modified_params.get("excluded_pairs")
    if isinstance(excluded_pairs, list):
        if worst_pair in excluded_pairs:
            return ProposalCandidateResult(
                success=False,
                message=f"Weak pair {worst_pair} is already excluded.",
                error="No action needed.",
            )
        excluded_pairs.append(worst_pair)
    else:
        modified_params["excluded_pairs"] = [worst_pair]

    return _stage_candidate_mutation(
        strategy_name=strategy_name,
        linked_version=linked_version,
        summary=f"Deterministic action: reduce weak pairs by excluding {worst_pair} (from diagnosis run {run_id})",
        created_by="deterministic_proposal",
        parameters=modified_params,
        source_ref=f"backtest_run:{run_id}",
        source_kind=source_kind,
        source_context=source_context,
        source_title="Reduce Weak Pairs",
    )


async def _apply_tighten_stoploss_action(
    strategy_name: str,
    parameters_snapshot: dict[str, Any] | None,
    run_id: str,
    linked_version: Any | None,
    source_kind: str,
    source_context: dict[str, Any] | None = None,
) -> ProposalCandidateResult:
    if not parameters_snapshot:
        return ProposalCandidateResult(
            success=False,
            message="No parameters snapshot available for tighten_stoploss action.",
            error="Parameters snapshot required but not found.",
        )

    modified_params = copy.deepcopy(parameters_snapshot)
    changed = False

    stoploss = modified_params.get("stoploss")
    if isinstance(stoploss, (int, float)) and stoploss < 0:
        modified_params["stoploss"] = round(max(float(stoploss) * 0.75, -0.5), 6)
        changed = True

    trailing_stop = modified_params.get("trailing_stop")
    if isinstance(trailing_stop, bool) and not trailing_stop:
        modified_params["trailing_stop"] = True
        changed = True

    trailing_positive = modified_params.get("trailing_stop_positive")
    if isinstance(trailing_positive, (int, float)) and float(trailing_positive) > 0.001:
        modified_params["trailing_stop_positive"] = round(max(float(trailing_positive) * 0.5, 0.001), 6)
        changed = True

    if not changed:
        return ProposalCandidateResult(
            success=False,
            message="No stoploss parameters could be tightened.",
            error="Could not identify modifiable stoploss controls.",
        )

    return _stage_candidate_mutation(
        strategy_name=strategy_name,
        linked_version=linked_version,
        summary=f"Deterministic action: tighten stoploss (from diagnosis run {run_id})",
        created_by="deterministic_proposal",
        parameters=modified_params,
        source_ref=f"backtest_run:{run_id}",
        source_kind=source_kind,
        source_context=source_context,
        source_title="Tighten Stoploss",
    )


async def _apply_review_exit_timing_action(
    strategy_name: str,
    parameters_snapshot: dict[str, Any] | None,
    run_id: str,
    linked_version: Any | None,
    source_kind: str,
    source_context: dict[str, Any] | None = None,
) -> ProposalCandidateResult:
    if not parameters_snapshot:
        return ProposalCandidateResult(
            success=False,
            message="No parameters snapshot available for review_exit_timing action.",
            error="Parameters snapshot required but not found.",
        )

    modified_params = copy.deepcopy(parameters_snapshot)
    changed = False

    minimal_roi = modified_params.get("minimal_roi")
    if isinstance(minimal_roi, dict) and minimal_roi:
        reviewed_roi = {}
        for time_str, target in minimal_roi.items():
            try:
                new_time = max(int(int(time_str) * 0.5), 0)
                reviewed_roi[str(new_time)] = target
                changed = True
            except (TypeError, ValueError):
                reviewed_roi[time_str] = target
        if changed:
            modified_params["minimal_roi"] = reviewed_roi

    trailing_positive = modified_params.get("trailing_stop_positive")
    if isinstance(trailing_positive, (int, float)) and float(trailing_positive) > 0.001:
        modified_params["trailing_stop_positive"] = round(max(float(trailing_positive) * 0.7, 0.001), 6)
        changed = True

    if not changed:
        return ProposalCandidateResult(
            success=False,
            message="No exit timing parameters could be reviewed automatically.",
            error="Could not identify modifiable exit timing controls.",
        )

    return _stage_candidate_mutation(
        strategy_name=strategy_name,
        linked_version=linked_version,
        summary=f"Deterministic action: review exit timing (from diagnosis run {run_id})",
        created_by="deterministic_proposal",
        parameters=modified_params,
        source_ref=f"backtest_run:{run_id}",
        source_kind=source_kind,
        source_context=source_context,
        source_title="Review Exit Timing",
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
    elif source_kind == "deterministic_action":
        items = diagnosis.get("proposal_actions") or []
    else:
        items = ai_payload.get("parameter_suggestions") or []

    if not isinstance(items, list) or source_index >= len(items):
        return None

    item = items[source_index]
    return item if isinstance(item, dict) else {"value": item}


def _normalize_action_type(action_type: str | None) -> str | None:
    if not action_type:
        return None
    return _ACTION_ALIASES.get(action_type, action_type)


def _find_action_type_for_rule(diagnosis: dict[str, Any] | None, rule: str | None) -> str | None:
    if not rule:
        return None
    for action in (diagnosis or {}).get("proposal_actions") or []:
        if not isinstance(action, dict):
            continue
        matched_rules = [str(item) for item in action.get("matched_rules") or []]
        if rule in matched_rules:
            return _normalize_action_type(str(action.get("action_type") or ""))
    return None


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
    if source_kind == "deterministic_action":
        return str(item.get("label") or item.get("action_type") or "Deterministic action")

    name = str(item.get("name") or item.get("parameter") or item.get("key") or "AI suggestion")
    value = item.get("value")
    reason = str(item.get("reason") or item.get("rationale") or item.get("summary") or "").strip()
    value_label = f" = {value}" if value not in (None, "") else ""
    return f"{name}{value_label}" + (f": {reason}" if reason else "")


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
    action_type: str | None = None,
    candidate_parameters: dict[str, Any] | None = None,
    candidate_code: str | None = None,
    candidate_summary: str | None = None,
) -> ProposalCandidateResult:
    if source_kind not in _VALID_SOURCE_KINDS:
        return ProposalCandidateResult(
            success=False,
            message="Invalid proposal source.",
            error=f"Unsupported source_kind: {source_kind}",
        )
    if source_index < 0:
        return ProposalCandidateResult(
            success=False,
            message="Invalid proposal source index.",
            error="source_index must be >= 0",
        )
    if candidate_mode not in _VALID_CANDIDATE_MODES:
        return ProposalCandidateResult(
            success=False,
            message="Invalid candidate mode.",
            error=f"Unsupported candidate_mode: {candidate_mode}",
        )

    diagnosis = diagnosis or {}
    ai_payload = ai_payload or {}
    parameters_snapshot = _resolve_parameters_snapshot(strategy_name, linked_version)

    if source_kind == "ai_chat_draft":
        has_parameters = isinstance(candidate_parameters, dict) and bool(candidate_parameters)
        has_code = isinstance(candidate_code, str) and bool(candidate_code.strip())
        if has_parameters == has_code:
            return ProposalCandidateResult(
                success=False,
                message="AI chat draft must contain exactly one candidate payload.",
                error="Provide either parameters or code for ai_chat_draft.",
            )

        effective_mode = candidate_mode
        if effective_mode == "auto":
            effective_mode = "code_patch" if has_code else "parameter_only"
        if effective_mode == "parameter_only" and not has_parameters:
            return ProposalCandidateResult(
                success=False,
                message="AI chat draft requested a parameter candidate without parameters.",
                error="parameter_only mode requires candidate_parameters.",
            )
        if effective_mode == "code_patch" and not has_code:
            return ProposalCandidateResult(
                success=False,
                message="AI chat draft requested a code candidate without code.",
                error="code_patch mode requires candidate_code.",
            )

        chat_summary = str(candidate_summary or "").strip()
        extra_context = {"candidate_mode": effective_mode}
        if chat_summary:
            extra_context["chat_summary"] = chat_summary
        return _stage_candidate_mutation(
            strategy_name=strategy_name,
            linked_version=linked_version,
            summary=f"AI chat candidate from run {run_id}",
            created_by="ai_apply",
            parameters=candidate_parameters if has_parameters else None,
            code=candidate_code if has_code else None,
            source_ref=f"backtest_run:{run_id}",
            source_kind=source_kind,
            source_context=_build_source_context(
                run_id=run_id,
                source_kind=source_kind,
                extra=extra_context,
            ),
            source_title="AI Chat Draft",
            ai_mode=effective_mode,
        )

    source_item = _resolve_source_item(source_kind, source_index, diagnosis, ai_payload)
    if source_item is None:
        return ProposalCandidateResult(
            success=False,
            message="Proposal source could not be resolved.",
            error=f"No {source_kind} found at index {source_index}",
        )

    normalized_action_type = _normalize_action_type(action_type)
    if source_kind == "deterministic_action" and not normalized_action_type:
        normalized_action_type = _normalize_action_type(str(source_item.get("action_type") or ""))

    if source_kind in {"ranked_issue", "parameter_hint"} and not normalized_action_type:
        normalized_action_type = _find_action_type_for_rule(diagnosis, str(source_item.get("rule") or ""))
        if not normalized_action_type:
            return ProposalCandidateResult(
                success=False,
                message=f"No deterministic action mapped for rule '{source_item.get('rule')}'.",
                error="Diagnosis did not produce a proposal action for this source.",
            )

    if normalized_action_type in {"tighten_entries", "reduce_weak_pairs", "tighten_stoploss", "review_exit_timing"}:
        source_context = _build_source_context(
            run_id=run_id,
            source_kind=source_kind,
            action_type=normalized_action_type,
            source_item=source_item,
        )
        if normalized_action_type == "tighten_entries":
            return await _apply_tighten_entries_action(
                strategy_name,
                parameters_snapshot,
                run_id,
                linked_version,
                source_kind,
                source_context,
            )
        if normalized_action_type == "reduce_weak_pairs":
            return await _apply_reduce_weak_pairs_action(
                strategy_name,
                parameters_snapshot,
                diagnosis,
                run_id,
                linked_version,
                source_kind,
                source_context,
            )
        if normalized_action_type == "tighten_stoploss":
            return await _apply_tighten_stoploss_action(
                strategy_name,
                parameters_snapshot,
                run_id,
                linked_version,
                source_kind,
                source_context,
            )
        return await _apply_review_exit_timing_action(
            strategy_name,
            parameters_snapshot,
            run_id,
            linked_version,
            source_kind,
            source_context,
        )

    if source_kind == "ai_parameter_suggestion":
        strategy_code = _resolve_strategy_code(strategy_name, linked_version)
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
            diagnosis=diagnosis,
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
                "primary_flags": diagnosis.get("primary_flags") or [],
                "ranked_issues": diagnosis.get("ranked_issues") or [],
                "parameter_hints": diagnosis.get("parameter_hints") or [],
                "proposal_actions": diagnosis.get("proposal_actions") or [],
                "facts": diagnosis.get("facts") or {},
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
        ai_mode = "parameter_only" if loop_result.final_parameters else "code_patch"
        return _stage_candidate_mutation(
            strategy_name=strategy_name,
            linked_version=linked_version,
            summary=candidate_summary,
            created_by="ai_apply",
            parameters=loop_result.final_parameters,
            code=loop_result.final_code,
            source_ref=f"backtest_run:{run_id}",
            source_kind=source_kind,
            source_context=_build_source_context(
                run_id=run_id,
                source_kind=source_kind,
                extra={
                    "candidate_mode": ai_mode,
                    "source_index": source_index,
                    "title": source_title,
                },
            ),
            source_title=source_title,
            ai_mode=ai_mode,
        )

    if source_kind in {"ranked_issue", "parameter_hint", "deterministic_action"}:
        return ProposalCandidateResult(
            success=False,
            message="Deterministic action could not be resolved.",
            error=f"Unsupported action type: {normalized_action_type or action_type}",
        )

    return ProposalCandidateResult(
        success=False,
        message=f"Unknown source_kind: {source_kind}",
        error="No matching route for this source kind.",
    )


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
        f"Proposal actions: {json.dumps((diagnosis or {}).get('proposal_actions') or [], indent=2, sort_keys=True)}",
        f"Current parameters snapshot: {json.dumps(parameters_snapshot or {}, indent=2, sort_keys=True)}",
        f"Linked version id: {linked_version_id or 'unavailable'}",
        f"Linked version change type: {linked_change_type or 'unavailable'}",
    ]
    return "\n".join(prompt_sections)


__all__ = [
    "ApplyIntelligenceResult",
    "ProposalCandidateResult",
    "apply_strategy_recommendations",
    "create_proposal_candidate_from_diagnosis",
]
