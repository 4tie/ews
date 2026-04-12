/**
 * compare-panel.js - Baseline-versus-candidate compare in workflow mode, generic two-run compare otherwise.
 */

import api from "../../../core/api.js";
import { on as onEvent, EVENTS } from "../../../core/events.js";
import { getState, on as onState } from "../../../core/state.js";
import { el, formatDate } from "../../../core/utils.js";
import {
  ensureSelectedCandidateVersion,
  getSelectedCandidateVersionId,
  getWorkflowCandidateVersions,
  setSelectedCandidateVersionId,
} from "./candidate-selection-state.js";
import { escapeHtml, labelize, renderDecisionReadyCompare } from "./decision-ready-renderer.js";
import {
  initPersistedRunsStore,
  subscribePersistedRuns,
} from "../results/persisted-runs-store.js";

const compareArea = document.getElementById("compare-area");
let persistedRunsState = { status: "idle", strategy: "", runs: [], error: null };
let versionsState = { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
let comparableRuns = [];
let latestResultsPayload = null;
let selectedLeftRunId = "";
let selectedRightRunId = "";
let lastComparison = null;
let lastComparedPairKey = "";
let compareError = null;
let compareLoading = false;
let compareRequestId = 0;
let versionsRequestId = 0;

export function initComparePanel() {
  if (!compareArea) return;

  initPersistedRunsStore();
  subscribePersistedRuns(handleRunsSnapshot);
  onEvent(EVENTS.RESULTS_LOADED, handleResultsLoaded);
  onState("backtest.selectedCandidateVersionId", () => {
    renderComparePanel();
    void maybeLoadComparison();
  });
}

function workflowModeActive() {
  return Boolean(
    latestResultsPayload?.diagnosis_status === "ready"
      && latestResultsPayload?.summary_available
      && latestResultsPayload?.run_id
  );
}

function workflowBaselineRunId() {
  return workflowModeActive() ? latestResultsPayload?.run_id || "" : "";
}

function workflowCandidateVersions() {
  return getWorkflowCandidateVersions(versionsState.versions, workflowBaselineRunId());
}

function workflowCandidateVersion() {
  const selected = getSelectedCandidateVersionId();
  return workflowCandidateVersions().find((version) => version?.version_id === selected) || workflowCandidateVersions()[0] || null;
}

function workflowCandidateRun() {
  const versionId = workflowCandidateVersion()?.version_id;
  if (!versionId) return null;
  return (persistedRunsState.runs || [])
    .filter((run) => run?.version_id === versionId && run?.status === "completed" && run?.summary_available)
    .slice()
    .sort((left, right) => String(right?.completed_at || right?.created_at || "").localeCompare(String(left?.completed_at || left?.created_at || "")))[0] || null;
}

function formatRunOption(run) {
  const versionId = run?.version_id || "no version";
  return `${run.run_id} | ${run.strategy || "Unknown"} | ${labelize(run.status)} | ${versionId} | ${formatDate(run?.completed_at || run?.created_at)}`;
}

function formatWorkflowCandidateOption(version) {
  const sourceTitle = version?.source_context?.title || version?.summary || version?.source_ref || "Candidate";
  return `${version?.version_id || "-"} | ${labelize(version?.change_type)} | ${sourceTitle} | ${formatDate(version?.created_at)}`;
}

function pickRetainedRunId(currentRunId, fallbackIndex) {
  if (currentRunId && comparableRuns.some((run) => run.run_id === currentRunId)) {
    return currentRunId;
  }
  return comparableRuns[fallbackIndex]?.run_id || "";
}

function pickDifferentRunId(excludedRunId) {
  return comparableRuns.find((run) => run.run_id !== excludedRunId)?.run_id || "";
}

function pickRetainedRightRunId(leftRunId, currentRunId) {
  if (currentRunId && currentRunId !== leftRunId && comparableRuns.some((run) => run.run_id === currentRunId)) {
    return currentRunId;
  }
  return pickDifferentRunId(leftRunId);
}

async function loadVersions(strategy) {
  if (!strategy) {
    versionsState = { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
    setSelectedCandidateVersionId(null);
    renderComparePanel();
    return;
  }

  const requestId = ++versionsRequestId;
  versionsState = { ...versionsState, status: "loading", strategy, error: null };
  renderComparePanel();

  try {
    const response = await api.versions.listVersions(strategy, true);
    if (requestId !== versionsRequestId) return;
    versionsState = {
      status: "ready",
      strategy,
      versions: Array.isArray(response?.versions) ? response.versions : [],
      activeVersionId: response?.active_version_id || null,
      error: null,
    };
    ensureSelectedCandidateVersion(versionsState.versions, workflowBaselineRunId());
    renderComparePanel();
    void maybeLoadComparison();
  } catch (error) {
    if (requestId !== versionsRequestId) return;
    versionsState = {
      status: "error",
      strategy,
      versions: [],
      activeVersionId: null,
      error: error?.message || String(error),
    };
    renderComparePanel();
  }
}

function handleResultsLoaded(payload) {
  latestResultsPayload = payload || null;
  if (!workflowModeActive()) {
    setSelectedCandidateVersionId(null);
  }
  const strategy = getState("backtest.strategy") || latestResultsPayload?.strategy || persistedRunsState.strategy || "";
  void loadVersions(strategy);
  renderComparePanel();
  void maybeLoadComparison();
}

function handleRunsSnapshot(snapshot) {
  persistedRunsState = snapshot;
  comparableRuns = Array.isArray(snapshot?.runs) ? snapshot.runs.filter((run) => run?.summary_available) : [];
  selectedLeftRunId = pickRetainedRunId(selectedLeftRunId, 0);
  selectedRightRunId = pickRetainedRightRunId(selectedLeftRunId, selectedRightRunId);

  if (workflowModeActive()) {
    ensureSelectedCandidateVersion(versionsState.versions, workflowBaselineRunId());
    renderComparePanel();
    void maybeLoadComparison();
    return;
  }

  if (!selectedLeftRunId || !selectedRightRunId || selectedLeftRunId === selectedRightRunId) {
    lastComparison = null;
    lastComparedPairKey = "";
    compareLoading = false;
    compareError = null;
    renderComparePanel();
    return;
  }

  const pairKey = `${selectedLeftRunId}:${selectedRightRunId}`;
  if (snapshot.status === "ready" && pairKey !== lastComparedPairKey && !compareLoading) {
    void maybeLoadComparison();
    return;
  }

  renderComparePanel();
}

async function loadComparisonForRuns(leftRunId, rightRunId) {
  if (!leftRunId || !rightRunId || leftRunId === rightRunId) {
    lastComparison = null;
    lastComparedPairKey = "";
    compareLoading = false;
    compareError = null;
    renderComparePanel();
    return;
  }

  const requestId = ++compareRequestId;
  lastComparison = null;
  lastComparedPairKey = "";
  compareLoading = true;
  compareError = null;
  renderComparePanel();

  try {
    const comparison = await api.backtest.compareRuns(leftRunId, rightRunId);
    if (requestId !== compareRequestId) return;
    lastComparison = comparison;
    lastComparedPairKey = `${leftRunId}:${rightRunId}`;
    compareLoading = false;
    compareError = null;
    renderComparePanel();
  } catch (error) {
    if (requestId !== compareRequestId) return;
    lastComparison = null;
    lastComparedPairKey = "";
    compareLoading = false;
    compareError = error?.message || String(error);
    renderComparePanel();
  }
}

async function maybeLoadComparison() {
  if (workflowModeActive()) {
    const candidateRun = workflowCandidateRun();
    if (!candidateRun) {
      lastComparison = null;
      lastComparedPairKey = "";
      compareLoading = false;
      compareError = null;
      renderComparePanel();
      return;
    }

    const key = `${workflowBaselineRunId()}:${candidateRun.run_id}`;
    if (key === lastComparedPairKey && (compareLoading || lastComparison)) {
      return;
    }
    await loadComparisonForRuns(workflowBaselineRunId(), candidateRun.run_id);
    return;
  }

  if (!selectedLeftRunId || !selectedRightRunId || selectedLeftRunId === selectedRightRunId) {
    lastComparison = null;
    lastComparedPairKey = "";
    compareLoading = false;
    compareError = null;
    renderComparePanel();
    return;
  }

  const key = `${selectedLeftRunId}:${selectedRightRunId}`;
  if (key === lastComparedPairKey && (compareLoading || lastComparison)) {
    return;
  }
  await loadComparisonForRuns(selectedLeftRunId, selectedRightRunId);
}

function buildSelectField({ label, id, value, options, onChange, disabled = false }) {
  const wrapper = el("label", { class: "setup-field compare-toolbar__field" });
  wrapper.appendChild(el("span", { class: "form-label" }, label));

  const select = el("select", { class: "form-select", id });
  select.disabled = disabled;
  options.forEach((option) => {
    const optionNode = el("option", { value: option.value }, option.label);
    if (option.value === value) optionNode.selected = true;
    select.appendChild(optionNode);
  });
  select.addEventListener("change", (event) => onChange(event.target.value));
  wrapper.appendChild(select);
  return wrapper;
}

function buildGenericToolbar() {
  const toolbar = el("div", { class: "compare-toolbar" });
  toolbar.appendChild(buildSelectField({
    label: "Left run",
    id: "compare-left-run",
    value: selectedLeftRunId,
    disabled: comparableRuns.length < 2 || persistedRunsState.status === "loading",
    options: comparableRuns.map((run) => ({ value: run.run_id, label: formatRunOption(run) })),
    onChange: (value) => {
      selectedLeftRunId = value;
      if (selectedLeftRunId === selectedRightRunId) {
        selectedRightRunId = pickRetainedRightRunId(selectedLeftRunId, selectedRightRunId);
      }
      lastComparison = null;
      lastComparedPairKey = "";
      compareError = null;
      void maybeLoadComparison();
    },
  }));
  toolbar.appendChild(buildSelectField({
    label: "Right run",
    id: "compare-right-run",
    value: selectedRightRunId,
    disabled: comparableRuns.length < 2 || persistedRunsState.status === "loading",
    options: comparableRuns.map((run) => ({ value: run.run_id, label: formatRunOption(run) })),
    onChange: (value) => {
      selectedRightRunId = value;
      if (selectedRightRunId === selectedLeftRunId) {
        selectedLeftRunId = pickDifferentRunId(selectedRightRunId);
      }
      lastComparison = null;
      lastComparedPairKey = "";
      compareError = null;
      void maybeLoadComparison();
    },
  }));
  return toolbar;
}

function buildWorkflowToolbar() {
  const toolbar = el("div", { class: "compare-toolbar" });
  toolbar.appendChild(buildSelectField({
    label: "Baseline",
    id: "compare-baseline-run",
    value: workflowBaselineRunId(),
    disabled: true,
    options: [{
      value: workflowBaselineRunId() || "",
      label: workflowBaselineRunId()
        ? `${workflowBaselineRunId()} | ${latestResultsPayload?.version_id || 'no version'} | ${formatDate(latestResultsPayload?.summary_metrics?.trade_end || latestResultsPayload?.summary_metrics?.trade_start || '')}`
        : "No baseline run",
    }],
    onChange: () => {},
  }));
  toolbar.appendChild(buildSelectField({
    label: "Selected Candidate",
    id: "compare-selected-candidate",
    value: getSelectedCandidateVersionId(),
    disabled: versionsState.status === "loading" || !workflowCandidateVersions().length,
    options: workflowCandidateVersions().map((version) => ({ value: version.version_id, label: formatWorkflowCandidateOption(version) })),
    onChange: (value) => {
      setSelectedCandidateVersionId(value || null);
    },
  }));
  return toolbar;
}

function buildContextGrid(comparison, { leftTitle = "Left run", rightTitle = "Right run" } = {}) {
  const grid = el("div", { class: "compare-context-grid" });
  grid.appendChild(buildRunContext(comparison?.left, leftTitle));
  grid.appendChild(buildRunContext(comparison?.right, rightTitle));
  return grid;
}

function buildRunContext(run, title) {
  const metrics = run?.summary_metrics || {};
  const section = el("section", { class: "results-context" });
  section.innerHTML = `
    <div class="results-context__title">${escapeHtml(title)}</div>
    <div class="results-context__meta">
      <span><strong>Run ID:</strong> ${escapeHtml(run?.run_id || "-")}</span>
      <span><strong>Strategy:</strong> ${escapeHtml(metrics.strategy || run?.strategy || "-")}</span>
      <span><strong>Version:</strong> ${escapeHtml(run?.version_id || "-")}</span>
      <span><strong>Status:</strong> ${escapeHtml(labelize(run?.status))}</span>
      <span><strong>Created:</strong> ${escapeHtml(formatDate(run?.completed_at || run?.created_at))}</span>
    </div>
  `;
  return section;
}

function renderWorkflowCompare(layout) {
  layout.appendChild(buildWorkflowToolbar());

  if (versionsState.status === "loading") {
    layout.appendChild(el("div", { class: "compare-note" }, "Loading workflow-linked candidate versions..."));
    return;
  }
  if (versionsState.status === "error") {
    layout.appendChild(el("div", { class: "info-empty" }, `Failed to load workflow candidates: ${versionsState.error}`));
    return;
  }
  if (!workflowCandidateVersions().length) {
    layout.appendChild(el("div", { class: "info-empty" }, "No persisted candidates are linked to the current baseline run yet."));
    return;
  }

  const candidateRun = workflowCandidateRun();
  if (!candidateRun) {
    layout.appendChild(el("div", { class: "info-empty" }, "Re-run the selected candidate to compare it against the baseline run."));
    return;
  }

  if (compareLoading) {
    layout.appendChild(el("div", { class: "compare-note" }, "Loading baseline versus selected candidate compare..."));
  }
  if (compareError) {
    layout.appendChild(el("div", { class: "info-empty" }, `Unable to compare the baseline run and selected candidate: ${compareError}`));
    return;
  }
  if (!lastComparison) {
    layout.appendChild(el("div", { class: "compare-note" }, "Select a candidate version to load its persisted compare evidence against the current baseline run."));
    return;
  }

  layout.appendChild(buildContextGrid(lastComparison, { leftTitle: "Baseline", rightTitle: "Selected Candidate" }));
  const evidence = el("div", { class: "compare-evidence" });
  evidence.innerHTML = renderDecisionReadyCompare(lastComparison, {
    baselineLabel: "Baseline",
    candidateLabel: "Selected Candidate",
  });
  layout.appendChild(evidence);
  layout.appendChild(el("div", { class: "compare-note" }, "Decision evidence is grounded in persisted run summaries, request snapshots, and version artifacts only."));
}

function renderGenericCompare(layout) {
  layout.appendChild(buildGenericToolbar());

  if (persistedRunsState.status === "loading" && !persistedRunsState.runs.length) {
    layout.appendChild(el("div", { class: "info-empty" }, "Loading persisted backtest runs for compare..."));
    return;
  }
  if (persistedRunsState.status === "error") {
    layout.appendChild(el("div", { class: "info-empty" }, `Failed to load persisted compare runs: ${persistedRunsState.error}`));
    return;
  }
  if (!comparableRuns.length) {
    layout.appendChild(el("div", { class: "info-empty" }, "No persisted completed runs with saved summary artifacts are available to compare yet."));
    return;
  }
  if (!selectedLeftRunId || !selectedRightRunId || selectedLeftRunId === selectedRightRunId) {
    layout.appendChild(el("div", { class: "info-empty" }, "Select two different persisted runs to compare."));
    return;
  }
  if (compareLoading) {
    layout.appendChild(el("div", { class: "compare-note" }, "Loading persisted comparison..."));
  }
  if (compareError) {
    layout.appendChild(el("div", { class: "info-empty" }, `Unable to compare the selected runs: ${compareError}`));
    return;
  }
  if (!lastComparison) {
    layout.appendChild(el("div", { class: "compare-note" }, "Choose the two saved runs you want to compare. The latest successful pair loads automatically."));
    return;
  }

  layout.appendChild(buildContextGrid(lastComparison));
  const evidence = el("div", { class: "compare-evidence" });
  evidence.innerHTML = renderDecisionReadyCompare(lastComparison, {
    baselineLabel: "Left run",
    candidateLabel: "Right run",
  });
  layout.appendChild(evidence);
  layout.appendChild(el("div", { class: "compare-note" }, "Compare rows are computed from persisted run-linked summary artifacts. Delta is right minus left."));
}

function renderComparePanel() {
  if (!compareArea) return;
  compareArea.innerHTML = "";

  const layout = el("div", { class: "compare-layout" });
  if (workflowModeActive()) {
    renderWorkflowCompare(layout);
  } else {
    renderGenericCompare(layout);
  }
  compareArea.appendChild(layout);
}
