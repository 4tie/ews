"""
Strategy Mutation Service - Core contract for version-controlled strategy mutations.

All strategy changes (Strategy Lab save, AI proposal candidates, Evolution generation,
Parameter-only quick actions) MUST go through this service to ensure:
- Every mutation creates a new version (no in-place overwrites)
- Full traceability (who, when, what)
- Reversibility (Accept/Rollback)
- Backtest/evolution reruns track exact version_id used
"""
from __future__ import annotations

import difflib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.freqtrade.paths import live_strategy_file, strategy_config_file
from app.models.optimizer_models import (
    ChangeType,
    MutationRequest,
    MutationResult,
    StrategyVersion,
    VersionAuditEvent,
    VersionStatus,
)
from app.services.config_service import ConfigService
from app.utils.json_io import read_json, write_json
from app.utils.paths import (
    storage_dir,
    strategy_active_version_file,
    strategy_version_file,
    strategy_versions_dir,
)


@dataclass
class MutationContext:
    """Context passed through the mutation pipeline."""
    request: MutationRequest
    version: StrategyVersion
    success: bool
    error: Optional[str] = None


class StrategyMutationService:
    """Single source of truth for all strategy mutations."""

    def __init__(self):
        self._cache: Dict[str, StrategyVersion] = {}

    def _generate_version_id(self, strategy_name: str) -> str:
        """Generate a unique version ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:6]
        return f"v_{strategy_name}_{timestamp}_{short_uuid}"

    def _ensure_version_dir(self, strategy_name: str) -> None:
        """Ensure version directory exists."""
        version_dir = strategy_versions_dir(strategy_name)
        os.makedirs(version_dir, exist_ok=True)

    def _load_version_from_disk(self, strategy_name: str, version_id: str) -> Optional[StrategyVersion]:
        """Load version from disk."""
        version_file = strategy_version_file(strategy_name, version_id)
        if not os.path.exists(version_file):
            return None
        data = read_json(version_file, fallback={})
        if not data:
            return None
        return StrategyVersion(**data)

    def _save_version(self, version: StrategyVersion) -> None:
        """Save version to disk."""
        self._ensure_version_dir(version.strategy_name)
        version_file = strategy_version_file(version.strategy_name, version.version_id)
        write_json(version_file, version.model_dump())
        self._cache[version.version_id] = version

    def _set_active_version(self, version: StrategyVersion) -> None:
        """Set active version reference."""
        self._ensure_version_dir(version.strategy_name)
        active_file = strategy_active_version_file(version.strategy_name)
        write_json(active_file, {
            "version_id": version.version_id,
            "updated_at": datetime.now().isoformat(),
        })

    def _get_active_version_id(self, strategy_name: str) -> Optional[str]:
        """Get the active version ID."""
        active_file = strategy_active_version_file(strategy_name)
        if not os.path.exists(active_file):
            return None
        data = read_json(active_file, fallback={})
        return data.get("version_id")

    def _live_artifact_paths(self, strategy_name: str) -> dict[str, str]:
        settings = ConfigService().get_settings()
        user_data_path = settings.get("user_data_path")
        return {
            "strategy_file": live_strategy_file(strategy_name, user_data_path),
            "config_file": strategy_config_file(strategy_name, user_data_path),
        }

    def _write_live_artifacts(self, version_id: str) -> dict[str, Any]:
        """
        SOLE AUTHORITY for writing to live strategy files.
        
        This is the ONLY path that modifies:
        - {user_data}/strategies/{strategy_name}.py
        - {user_data}/config/{strategy_name}.json
        
        Called exclusively from:
        - accept_version() - after status + artifact validation gates
        - rollback_version() - after artifact validation gates
        
        Caller must validate:
        - Version status is correct (accept checks CANDIDATE, rollback checks any)
        - Version has valid code_snapshot in lineage
        
        This ensures no side-channel writes or bypasses of promotion path.
        """
        resolved = self.resolve_effective_artifacts(version_id)
        strategy_name = str(resolved.get("strategy_name") or "")
        code_snapshot = resolved.get("code_snapshot")
        parameters_snapshot = resolved.get("parameters_snapshot")

        if not strategy_name:
            raise ValueError(f"Version {version_id} did not resolve to a strategy name")
        if not isinstance(code_snapshot, str) or not code_snapshot.strip():
            raise ValueError(f"Version {version_id} does not resolve to a strategy code snapshot")
        if parameters_snapshot is not None and not isinstance(parameters_snapshot, dict):
            raise ValueError(f"Version {version_id} resolved to an invalid parameters snapshot")

        paths = self._live_artifact_paths(strategy_name)
        os.makedirs(os.path.dirname(paths["strategy_file"]), exist_ok=True)
        with open(paths["strategy_file"], "w", encoding="utf-8") as handle:
            handle.write(code_snapshot)

        if isinstance(parameters_snapshot, dict):
            write_json(paths["config_file"], parameters_snapshot)
        elif os.path.isfile(paths["config_file"]):
            os.remove(paths["config_file"])

        return {
            "strategy_name": strategy_name,
            "strategy_file": paths["strategy_file"],
            "config_file": paths["config_file"],
            "parameters_written": isinstance(parameters_snapshot, dict),
        }

    def _archive_active_version(self, strategy_name: str, *, except_version_id: str | None = None) -> Optional[str]:
        active_id = self._get_active_version_id(strategy_name)
        if active_id and active_id != except_version_id:
            old_active = self.get_version(strategy_name, active_id) or self.get_version_by_id(active_id)
            if old_active:
                old_active.status = VersionStatus.ARCHIVED
                self._save_version(old_active)
        return active_id

    @staticmethod
    def _deep_merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
        """Merge nested parameter dictionaries with child values taking precedence."""
        merged = dict(base)
        for key, value in overlay.items():
            current = merged.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                merged[key] = StrategyMutationService._deep_merge_dicts(current, value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _normalize_diff_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): StrategyMutationService._normalize_diff_value(value[key])
                for key in sorted(value.keys(), key=lambda item: str(item))
            }
        if isinstance(value, list):
            return [StrategyMutationService._normalize_diff_value(item) for item in value]
        if isinstance(value, tuple):
            return [StrategyMutationService._normalize_diff_value(item) for item in value]
        if isinstance(value, float):
            return round(value, 12)
        return value

    @staticmethod
    def _classify_parameter_diff_row(before: Any, after: Any) -> str:
        if before is None and after is not None:
            return "added"
        if before is not None and after is None:
            return "removed"
        return "changed"

    @staticmethod
    def _collect_parameter_diff_rows(before: Any, after: Any, path: str, rows: list[dict[str, Any]]) -> None:
        before_value = StrategyMutationService._normalize_diff_value(before)
        after_value = StrategyMutationService._normalize_diff_value(after)

        if before_value == after_value:
            return

        if isinstance(before_value, dict) or isinstance(after_value, dict):
            left_dict = before_value if isinstance(before_value, dict) else {}
            right_dict = after_value if isinstance(after_value, dict) else {}
            keys = sorted(set(left_dict) | set(right_dict), key=lambda item: str(item))
            for key in keys:
                next_path = f"{path}.{key}" if path else str(key)
                StrategyMutationService._collect_parameter_diff_rows(
                    left_dict.get(key),
                    right_dict.get(key),
                    next_path,
                    rows,
                )
            return

        if isinstance(before_value, list) or isinstance(after_value, list):
            left_list = before_value if isinstance(before_value, list) else []
            right_list = after_value if isinstance(after_value, list) else []
            for index in range(max(len(left_list), len(right_list))):
                next_path = f"{path}[{index}]" if path else f"[{index}]"
                StrategyMutationService._collect_parameter_diff_rows(
                    left_list[index] if index < len(left_list) else None,
                    right_list[index] if index < len(right_list) else None,
                    next_path,
                    rows,
                )
            return

        rows.append(
            {
                "path": path or "$",
                "before": before_value,
                "after": after_value,
                "status": StrategyMutationService._classify_parameter_diff_row(before_value, after_value),
            }
        )

    @staticmethod
    def _count_code_diff_lines(before_code: str, after_code: str) -> tuple[int, int]:
        added_lines = 0
        removed_lines = 0
        for line in difflib.ndiff(before_code.splitlines(), after_code.splitlines()):
            if line.startswith("+ "):
                added_lines += 1
            elif line.startswith("- "):
                removed_lines += 1
        return added_lines, removed_lines

    @staticmethod
    def _append_audit_event(
        version: StrategyVersion,
        event_type: str,
        *,
        actor: str | None = None,
        note: str | None = None,
        from_version_id: str | None = None,
    ) -> None:
        note_text = str(note or "").strip() or None
        source_version_id = str(from_version_id or "").strip() or None
        audit_events = list(getattr(version, "audit_events", None) or [])
        audit_events.append(
            VersionAuditEvent(
                event_type=event_type,
                created_at=datetime.now().isoformat(),
                actor=str(actor or "system").strip() or "system",
                note=note_text,
                from_version_id=source_version_id,
            )
        )
        version.audit_events = audit_events

    @staticmethod
    def _validate_new_strategy_name(strategy_name: str, current_strategy_name: str | None = None) -> str:
        normalized = str(strategy_name or "").strip()
        if not normalized:
            raise ValueError("New strategy name is required")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", normalized):
            raise ValueError("New strategy name must be a valid Python identifier")
        if current_strategy_name and normalized == str(current_strategy_name).strip():
            raise ValueError("New strategy name must be different from the current strategy")
        return normalized

    def _ensure_new_strategy_targets_available(self, strategy_name: str) -> None:
        paths = self._live_artifact_paths(strategy_name)
        collisions: list[str] = []
        if os.path.exists(paths["strategy_file"]):
            collisions.append(paths["strategy_file"])
        if os.path.exists(paths["config_file"]):
            collisions.append(paths["config_file"])
        version_dir = strategy_versions_dir(strategy_name)
        if os.path.exists(version_dir):
            collisions.append(version_dir)
        if collisions:
            raise ValueError(f"New strategy target already exists: {', '.join(collisions)}")

    @staticmethod
    def _rename_strategy_class(code_snapshot: str, source_strategy_name: str, new_strategy_name: str) -> str:
        if not isinstance(code_snapshot, str) or not code_snapshot.strip():
            raise ValueError("Resolved strategy code snapshot is empty")

        class_pattern = re.compile(r"(^\s*class\s+)([A-Za-z_][A-Za-z0-9_]*)(\s*(?:\(|:))", re.MULTILINE)
        matches = list(class_pattern.finditer(code_snapshot))
        if not matches:
            raise ValueError("Could not locate a strategy class definition in the resolved code snapshot")

        target_match = None
        for match in matches:
            if match.group(2) == source_strategy_name:
                target_match = match
                break
        if target_match is None:
            target_match = matches[0]

        start, end = target_match.span(2)
        return f"{code_snapshot[:start]}{new_strategy_name}{code_snapshot[end:]}"

    @staticmethod
    def _build_code_diff_preview(
        before_code: str,
        after_code: str,
        *,
        baseline_label: str = "baseline",
        candidate_label: str = "candidate",
        max_blocks: int = 3,
        max_lines: int = 40,
    ) -> dict[str, Any]:
        diff_lines = list(
            difflib.unified_diff(
                before_code.splitlines(),
                after_code.splitlines(),
                fromfile=baseline_label,
                tofile=candidate_label,
                n=2,
                lineterm="",
            )
        )
        if not diff_lines:
            return {
                "preview_blocks": [],
                "preview_truncated": False,
            }

        total_hunks = sum(1 for line in diff_lines if line.startswith("@@"))
        preview_blocks: list[dict[str, Any]] = []
        current_block: dict[str, Any] | None = None
        preview_line_count = 0
        truncated = False

        for line in diff_lines:
            if line.startswith("---") or line.startswith("+++"):
                continue
            if line.startswith("@@"):
                if len(preview_blocks) >= max_blocks:
                    truncated = True
                    break
                current_block = {
                    "header": line,
                    "lines": [],
                }
                preview_blocks.append(current_block)
                continue
            if current_block is None:
                continue
            if preview_line_count >= max_lines:
                truncated = True
                break

            kind = "context"
            text = line
            if line.startswith("+"):
                kind = "added"
                text = line[1:]
            elif line.startswith("-"):
                kind = "removed"
                text = line[1:]
            elif line.startswith(" "):
                kind = "context"
                text = line[1:]

            current_block["lines"].append({
                "kind": kind,
                "text": text,
            })
            preview_line_count += 1

        if total_hunks > len(preview_blocks):
            truncated = True

        return {
            "preview_blocks": [block for block in preview_blocks if block.get("lines")],
            "preview_truncated": truncated,
        }

    def normalize_source_metadata(self, version: StrategyVersion | None) -> dict[str, Any]:
        if version is None:
            return {
                "source_kind": None,
                "source_title": None,
                "candidate_mode": None,
                "source_index": None,
                "action_type": None,
                "rule": None,
                "matched_rules": [],
            }

        source_context = dict(getattr(version, "source_context", None) or {})
        matched_rules = source_context.get("matched_rules")
        if not isinstance(matched_rules, list):
            matched_rules = []

        source_title = (
            str(source_context.get("title") or source_context.get("chat_summary") or "").strip()
            or str(getattr(version, "summary", None) or "").strip()
            or str(getattr(version, "source_ref", None) or "").strip()
            or None
        )
        candidate_mode = str(source_context.get("candidate_mode") or "").strip() or None
        action_type = str(source_context.get("action_type") or "").strip() or None
        rule = str(source_context.get("rule") or source_context.get("flag_rule") or "").strip() or None
        source_index = source_context.get("source_index")

        return {
            "source_kind": getattr(version, "source_kind", None),
            "source_title": source_title,
            "candidate_mode": candidate_mode,
            "source_index": source_index,
            "action_type": action_type,
            "rule": rule,
            "matched_rules": [str(item).strip() for item in matched_rules if str(item).strip()],
        }

    def resolve_compare_versions(self, left_version_id: str | None, right_version_id: str | None) -> dict[str, Any]:
        baseline_version = self.get_version_by_id(left_version_id) if left_version_id else None
        candidate_version = self.get_version_by_id(right_version_id) if right_version_id else None
        baseline_source = "run" if baseline_version is not None else None

        if baseline_version is None and candidate_version is not None and candidate_version.parent_version_id:
            fallback_version = self.get_version_by_id(candidate_version.parent_version_id)
            if fallback_version is not None:
                baseline_version = fallback_version
                baseline_source = "candidate_parent"

        return {
            "baseline_version": baseline_version,
            "candidate_version": candidate_version,
            "baseline_version_source": baseline_source,
        }

    def build_parameter_diff_rows(
        self,
        baseline_version: StrategyVersion | None,
        candidate_version: StrategyVersion | None,
    ) -> list[dict[str, Any]]:
        baseline_parameters = None
        candidate_parameters = None

        if baseline_version is not None:
            baseline_parameters = self.resolve_effective_artifacts(baseline_version.version_id).get("parameters_snapshot")
        if candidate_version is not None:
            candidate_parameters = self.resolve_effective_artifacts(candidate_version.version_id).get("parameters_snapshot")

        rows: list[dict[str, Any]] = []
        self._collect_parameter_diff_rows(baseline_parameters, candidate_parameters, "", rows)
        rows.sort(key=lambda row: str(row.get("path") or ""))
        return rows

    def summarize_code_diff(
        self,
        baseline_version: StrategyVersion | None,
        candidate_version: StrategyVersion | None,
    ) -> dict[str, Any]:
        baseline_code = ""
        candidate_code = ""
        diff_ref = getattr(candidate_version, "diff_ref", None) if candidate_version is not None else None

        if baseline_version is not None:
            baseline_code = str(self.resolve_effective_artifacts(baseline_version.version_id).get("code_snapshot") or "")
        if candidate_version is not None:
            candidate_code = str(self.resolve_effective_artifacts(candidate_version.version_id).get("code_snapshot") or "")

        preview = self._build_code_diff_preview(
            baseline_code,
            candidate_code,
            baseline_label=getattr(baseline_version, "version_id", None) or "baseline",
            candidate_label=getattr(candidate_version, "version_id", None) or "candidate",
        )

        if not baseline_code.strip() and not candidate_code.strip():
            return {
                "changed": False,
                "added_lines": 0,
                "removed_lines": 0,
                "diff_ref": diff_ref,
                "summary": "No persisted code snapshot is available for this compare.",
                "preview_blocks": [],
                "preview_truncated": False,
            }

        if baseline_code == candidate_code:
            return {
                "changed": False,
                "added_lines": 0,
                "removed_lines": 0,
                "diff_ref": diff_ref,
                "summary": "No persisted code changes were detected between baseline and candidate.",
                "preview_blocks": [],
                "preview_truncated": False,
            }

        added_lines, removed_lines = self._count_code_diff_lines(baseline_code, candidate_code)
        return {
            "changed": True,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "diff_ref": diff_ref,
            "summary": f"Persisted code snapshot changed by {added_lines} added and {removed_lines} removed lines.",
            "preview_blocks": preview["preview_blocks"],
            "preview_truncated": preview["preview_truncated"],
        }

    def build_version_compare_payload(self, left_version_id: str | None, right_version_id: str | None) -> dict[str, Any]:
        resolved_versions = self.resolve_compare_versions(left_version_id, right_version_id)
        baseline_version = resolved_versions["baseline_version"]
        candidate_version = resolved_versions["candidate_version"]
        source_metadata = self.normalize_source_metadata(candidate_version)

        versions = {
            "baseline_version_id": getattr(baseline_version, "version_id", None),
            "candidate_version_id": getattr(candidate_version, "version_id", None),
            "candidate_parent_version_id": getattr(candidate_version, "parent_version_id", None),
            "baseline_version_source": resolved_versions.get("baseline_version_source"),
        }
        version_diff = {
            **versions,
            "source_kind": source_metadata["source_kind"],
            "source_title": source_metadata["source_title"],
            "candidate_mode": source_metadata["candidate_mode"],
            "change_type": getattr(getattr(candidate_version, "change_type", None), "value", None),
            "summary": getattr(candidate_version, "summary", None),
            "source_index": source_metadata["source_index"],
            "action_type": source_metadata["action_type"],
            "rule": source_metadata["rule"],
            "matched_rules": source_metadata["matched_rules"],
            "parameter_diff_rows": self.build_parameter_diff_rows(baseline_version, candidate_version),
            "code_diff": self.summarize_code_diff(baseline_version, candidate_version),
        }
        return {
            "versions": versions,
            "version_diff": version_diff,
        }

    def get_version_by_id(self, version_id: str) -> Optional[StrategyVersion]:
        """Get a version by ID without inferring ownership from the ID format."""
        if version_id in self._cache:
            return self._cache[version_id]

        versions_root = os.path.join(storage_dir(), "versions")
        if not os.path.isdir(versions_root):
            return None

        for strategy_name in os.listdir(versions_root):
            strategy_dir = os.path.join(versions_root, strategy_name)
            if not os.path.isdir(strategy_dir):
                continue

            version = self._load_version_from_disk(strategy_name, version_id)
            if version:
                return version

        return None

    def resolve_effective_artifacts(self, version_id: str) -> dict[str, Any]:
        """Resolve the effective code and parameter snapshots for a version lineage."""
        version = self.get_version_by_id(version_id)
        if not version:
            raise ValueError(f"Version {version_id} not found")

        strategy_name = version.strategy_name
        lineage: list[str] = []
        seen: set[str] = set()
        code_snapshot: str | None = None
        parameter_layers: list[dict[str, Any]] = []
        current: StrategyVersion | None = version

        while current is not None:
            if current.version_id in seen:
                raise ValueError(f"Version lineage cycle detected at {current.version_id}")

            seen.add(current.version_id)
            lineage.append(current.version_id)

            if current.strategy_name != strategy_name:
                raise ValueError(
                    f"Version lineage crosses strategies: {version_id} -> {current.version_id}"
                )

            if code_snapshot is None and isinstance(current.code_snapshot, str) and current.code_snapshot.strip():
                code_snapshot = current.code_snapshot

            if isinstance(current.parameters_snapshot, dict) and current.parameters_snapshot:
                parameter_layers.append(current.parameters_snapshot)

            parent_version_id = current.parent_version_id
            if not parent_version_id:
                break

            parent = self.get_version_by_id(parent_version_id)
            if parent is None:
                break
            current = parent

        parameters_snapshot: dict[str, Any] | None = None
        if parameter_layers:
            merged: dict[str, Any] = {}
            for layer in reversed(parameter_layers):
                merged = self._deep_merge_dicts(merged, layer)
            parameters_snapshot = merged

        return {
            "version_id": version.version_id,
            "strategy_name": strategy_name,
            "lineage": lineage,
            "code_snapshot": code_snapshot,
            "parameters_snapshot": parameters_snapshot,
        }

    def create_mutation(self, request: MutationRequest) -> MutationResult:
        """
        Create a new version from a mutation request.

        This is the ONLY way to create new strategy versions.
        All change paths must use this service.
        """
        version_id = self._generate_version_id(request.strategy_name)

        parent_version_id = request.parent_version_id
        if not parent_version_id:
            parent_version_id = self._get_active_version_id(request.strategy_name)

        version = StrategyVersion(
            version_id=version_id,
            parent_version_id=parent_version_id,
            strategy_name=request.strategy_name,
            created_at=datetime.now().isoformat(),
            created_by=request.created_by,
            change_type=request.change_type,
            summary=request.summary,
            diff_ref=request.diff_ref,
            source_ref=request.source_ref,
            source_kind=request.source_kind,
            source_context=dict(request.source_context or {}),
            status=VersionStatus.CANDIDATE,
            code_snapshot=request.code,
            parameters_snapshot=request.parameters,
        )
        self._append_audit_event(version, "created", actor=request.created_by)

        self._save_version(version)

        return MutationResult(
            version_id=version_id,
            status="created",
            message=f"New candidate version {version_id} created from {request.change_type}",
        )

    def promote_as_new_strategy(
        self,
        version_id: str,
        *,
        new_strategy_name: str | None,
        notes: Optional[str] = None,
    ) -> MutationResult:
        source_version = self.get_version_by_id(version_id)
        if not source_version:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} not found",
            )

        if source_version.status != VersionStatus.CANDIDATE:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} is not a candidate (status: {source_version.status})",
            )

        try:
            normalized_strategy_name = self._validate_new_strategy_name(new_strategy_name or "", source_version.strategy_name)
            self._ensure_new_strategy_targets_available(normalized_strategy_name)
            artifacts = self.resolve_effective_artifacts(version_id)
            code_snapshot = self._rename_strategy_class(
                str(artifacts.get("code_snapshot") or ""),
                source_version.strategy_name,
                normalized_strategy_name,
            )
            parameters_snapshot = artifacts.get("parameters_snapshot")
            if parameters_snapshot is not None and not isinstance(parameters_snapshot, dict):
                raise ValueError("Resolved parameters snapshot is invalid")
        except Exception as exc:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} could not be promoted as a new strategy: {exc}",
            )

        source_title = (
            str((getattr(source_version, "source_context", None) or {}).get("title") or "").strip()
            or str(getattr(source_version, "summary", None) or "").strip()
            or f"Promoted from {source_version.strategy_name}:{source_version.version_id}"
        )
        mutation_result = self.create_mutation(
            MutationRequest(
                strategy_name=normalized_strategy_name,
                change_type=getattr(source_version, "change_type", ChangeType.MANUAL),
                summary=f"Promoted from {source_version.strategy_name}:{source_version.version_id}",
                created_by="promote_as_new_strategy",
                code=code_snapshot,
                parameters=parameters_snapshot if isinstance(parameters_snapshot, dict) else None,
                parent_version_id=None,
                source_ref=f"strategy_version:{source_version.strategy_name}:{source_version.version_id}",
                source_kind="promoted_strategy",
                source_context={
                    "title": source_title,
                    "promoted_as_new_strategy": True,
                    "source_strategy_name": source_version.strategy_name,
                    "source_version_id": source_version.version_id,
                    "new_strategy_name": normalized_strategy_name,
                    "candidate_mode": (getattr(source_version, "source_context", None) or {}).get("candidate_mode"),
                },
            )
        )
        if mutation_result.status == "error":
            return mutation_result

        accept_result = self.accept_version(mutation_result.version_id, notes)
        if accept_result.status == "error":
            return accept_result

        promoted_note = str(notes or "").strip()
        if promoted_note:
            promoted_note = f"Promoted as new strategy {normalized_strategy_name}. {promoted_note}"
        else:
            promoted_note = f"Promoted as new strategy {normalized_strategy_name}."
        self._append_audit_event(
            source_version,
            "promoted_as_new_strategy",
            actor="promote_as_new_strategy",
            note=promoted_note,
        )
        self._save_version(source_version)

        return MutationResult(
            version_id=accept_result.version_id,
            status="promoted_as_new_strategy",
            message=f"Version {version_id} promoted as new strategy {normalized_strategy_name}",
        )

    def accept_version(self, version_id: str, notes: Optional[str] = None) -> MutationResult:
        """Promote a candidate version to active and write its live artifacts."""
        version = self.get_version_by_id(version_id)
        if not version:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} not found",
            )

        if version.status != VersionStatus.CANDIDATE:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} is not a candidate (status: {version.status})",
            )

        # Gate 1: Ensure valid artifacts before touching live files
        try:
            artifacts = self.resolve_effective_artifacts(version_id)
            if not isinstance(artifacts.get("code_snapshot"), str) or not artifacts.get("code_snapshot", "").strip():
                raise ValueError(f"Version {version_id} does not resolve to a valid code snapshot")
        except Exception as exc:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} has invalid artifacts: {exc}",
            )

        try:
            self._write_live_artifacts(version_id)
        except Exception as exc:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} could not be promoted: {exc}",
            )

        active_id = self._archive_active_version(version.strategy_name, except_version_id=version.version_id)
        version.status = VersionStatus.ACTIVE
        version.promoted_from_version_id = active_id
        version.promoted_at = datetime.now().isoformat()
        self._append_audit_event(version, "accepted", note=notes, from_version_id=active_id)
        self._save_version(version)
        self._set_active_version(version)

        return MutationResult(
            version_id=version_id,
            status="accepted",
            message=f"Version {version_id} promoted to active" + (f": {notes}" if notes else ""),
        )

    def rollback_version(self, target_version_id: str, reason: Optional[str] = None) -> MutationResult:
        """Rollback to an accepted prior version and restore its live artifacts."""
        target_version = self.get_version_by_id(target_version_id)
        if not target_version:
            return MutationResult(
                version_id=target_version_id,
                status="error",
                message=f"Version {target_version_id} not found",
            )

        if target_version.status in {VersionStatus.CANDIDATE, VersionStatus.DRAFT, VersionStatus.REJECTED}:
            return MutationResult(
                version_id=target_version_id,
                status="error",
                message=(
                    f"Version {target_version_id} is {target_version.status} and cannot be used as a rollback target"
                ),
            )

        # Gate 1: Ensure valid artifacts before touching live files
        try:
            artifacts = self.resolve_effective_artifacts(target_version_id)
            if not isinstance(artifacts.get("code_snapshot"), str) or not artifacts.get("code_snapshot", "").strip():
                raise ValueError(f"Version {target_version_id} does not resolve to a valid code snapshot")
        except Exception as exc:
            return MutationResult(
                version_id=target_version_id,
                status="error",
                message=f"Rollback to {target_version_id} failed - invalid artifacts: {exc}",
            )

        try:
            self._write_live_artifacts(target_version_id)
        except Exception as exc:
            return MutationResult(
                version_id=target_version_id,
                status="error",
                message=f"Rollback to {target_version_id} failed: {exc}",
            )

        current_active = self._archive_active_version(
            target_version.strategy_name,
            except_version_id=target_version.version_id,
        )
        target_version.status = VersionStatus.ACTIVE
        target_version.promoted_from_version_id = current_active
        target_version.promoted_at = datetime.now().isoformat()
        self._append_audit_event(target_version, "rolled_back", note=reason, from_version_id=current_active)
        self._save_version(target_version)
        self._set_active_version(target_version)

        return MutationResult(
            version_id=target_version_id,
            status="rolled_back",
            message=f"Rolled back to {target_version_id}" + (f": {reason}" if reason else ""),
        )

    def reject_version(self, version_id: str, reason: Optional[str] = None) -> MutationResult:
        """Reject a candidate version without changing the active version."""
        version = self.get_version_by_id(version_id)
        if not version:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} not found",
            )

        if version.status == VersionStatus.ACTIVE:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} is active and cannot be rejected",
            )

        if version.status == VersionStatus.REJECTED:
            return MutationResult(
                version_id=version_id,
                status="rejected",
                message=f"Version {version_id} is already rejected" + (f": {reason}" if reason else ""),
            )

        if version.status != VersionStatus.CANDIDATE:
            return MutationResult(
                version_id=version_id,
                status="error",
                message=f"Version {version_id} is not a candidate and cannot be rejected",
            )

        version.status = VersionStatus.REJECTED
        self._append_audit_event(version, "rejected", note=reason)
        self._save_version(version)

        return MutationResult(
            version_id=version_id,
            status="rejected",
            message=f"Version {version_id} rejected" + (f": {reason}" if reason else ""),
        )

    def get_version(self, strategy_name: str, version_id: str) -> Optional[StrategyVersion]:
        """Get a specific version."""
        if version_id in self._cache:
            return self._cache[version_id]
        return self._load_version_from_disk(strategy_name, version_id)

    def get_active_version(self, strategy_name: str) -> Optional[StrategyVersion]:
        """Get the active version for a strategy."""
        active_id = self._get_active_version_id(strategy_name)
        if not active_id:
            return None
        return self.get_version(strategy_name, active_id)

    def list_versions(self, strategy_name: str, include_archived: bool = False) -> List[StrategyVersion]:
        """List all versions for a strategy."""
        version_dir = strategy_versions_dir(strategy_name)
        if not os.path.exists(version_dir):
            return []

        versions: List[StrategyVersion] = []
        for fname in os.listdir(version_dir):
            if not fname.endswith(".json"):
                continue
            if fname == "active_version.json":
                continue

            version_id = fname[:-5]
            version = self.get_version(strategy_name, version_id)
            if version and (include_archived or version.status != VersionStatus.ARCHIVED):
                versions.append(version)

        return sorted(versions, key=lambda v: v.created_at, reverse=True)

    def link_backtest(
        self,
        version_id: str,
        backtest_run_id: str,
        profit_pct: Optional[float] = None,
    ) -> None:
        """Link a backtest run to a version."""
        version = self.get_version_by_id(version_id)
        if version:
            version.backtest_run_id = backtest_run_id
            version.backtest_profit_pct = profit_pct
            self._save_version(version)


mutation_service = StrategyMutationService()


__all__ = [
    "StrategyMutationService",
    "MutationContext",
    "mutation_service",
    "MutationRequest",
    "MutationResult",
    "VersionStatus",
]
