/**
 * candidate-selection-state.js - Shared selected-candidate state for backtesting compare surfaces.
 */

import { getState, setState } from "../../../core/state.js";

function isPendingWorkflowCandidate(version) {
  return String(version?.status || "").toLowerCase() === "candidate";
}

function workflowSourceRef(baselineRunId) {
  const normalized = baselineRunId ? String(baselineRunId).trim() : "";
  return normalized ? `backtest_run:${normalized}` : "";
}

function selectedCandidateSelections() {
  const value = getState("backtest.selectedCandidateVersionBySourceRef");
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function getSelectedCandidateVersionId(baselineRunId = "") {
  const sourceRef = workflowSourceRef(baselineRunId);
  if (sourceRef) {
    const value = selectedCandidateSelections()[sourceRef];
    if (value) return String(value);
  }
  const value = getState("backtest.selectedCandidateVersionId");
  return value ? String(value) : "";
}

export function setSelectedCandidateVersionId(versionId, baselineRunId = "") {
  const normalized = versionId ? String(versionId) : null;
  const sourceRef = workflowSourceRef(baselineRunId);

  if (sourceRef) {
    const currentSelections = selectedCandidateSelections();
    const nextSelections = { ...currentSelections };
    if (normalized) {
      nextSelections[sourceRef] = normalized;
    } else {
      delete nextSelections[sourceRef];
    }
    const currentSelection = currentSelections[sourceRef] ? String(currentSelections[sourceRef]) : null;
    if (currentSelection !== normalized) {
      setState("backtest.selectedCandidateVersionBySourceRef", nextSelections);
    }
  }

  const currentValue = getState("backtest.selectedCandidateVersionId");
  const currentNormalized = currentValue ? String(currentValue) : null;
  if (currentNormalized !== normalized) {
    setState("backtest.selectedCandidateVersionId", normalized);
  }
}

export function getWorkflowCandidateVersions(versions, baselineRunId) {
  const sourceRef = workflowSourceRef(baselineRunId);
  if (!sourceRef || !Array.isArray(versions)) return [];
  return versions
    .filter((version) => version?.source_ref === sourceRef && isPendingWorkflowCandidate(version))
    .slice()
    .sort((left, right) => String(right?.created_at || "").localeCompare(String(left?.created_at || "")));
}

export function ensureSelectedCandidateVersion(versions, baselineRunId) {
  const workflowVersions = getWorkflowCandidateVersions(versions, baselineRunId);
  const current = getSelectedCandidateVersionId(baselineRunId);
  if (workflowVersions.some((version) => version?.version_id === current)) {
    return current;
  }

  const next = workflowVersions[0]?.version_id || "";
  if (next !== current) {
    setSelectedCandidateVersionId(next || null, baselineRunId);
  }
  return next;
}
