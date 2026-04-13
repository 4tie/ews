/**
 * candidate-selection-state.js - Shared selected-candidate state for backtesting compare surfaces.
 */

import { getState, setState } from "../../../core/state.js";

function isPendingWorkflowCandidate(version) {
  return String(version?.status || "").toLowerCase() === "candidate";
}

export function getSelectedCandidateVersionId() {
  const value = getState("backtest.selectedCandidateVersionId");
  return value ? String(value) : "";
}

export function setSelectedCandidateVersionId(versionId) {
  setState("backtest.selectedCandidateVersionId", versionId ? String(versionId) : null);
}

export function getWorkflowCandidateVersions(versions, baselineRunId) {
  const sourceRef = baselineRunId ? `backtest_run:${baselineRunId}` : "";
  if (!sourceRef || !Array.isArray(versions)) return [];
  return versions
    .filter((version) => version?.source_ref === sourceRef && isPendingWorkflowCandidate(version))
    .slice()
    .sort((left, right) => String(right?.created_at || "").localeCompare(String(left?.created_at || "")));
}

export function ensureSelectedCandidateVersion(versions, baselineRunId) {
  const workflowVersions = getWorkflowCandidateVersions(versions, baselineRunId);
  const current = getSelectedCandidateVersionId();
  if (workflowVersions.some((version) => version?.version_id === current)) {
    return current;
  }

  const next = workflowVersions[0]?.version_id || "";
  if (next !== current) {
    setSelectedCandidateVersionId(next || null);
  }
  return next;
}
