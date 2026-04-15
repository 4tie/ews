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
import {
  initPersistedVersionsStore,
  refreshPersistedVersions,
  subscribePersistedVersions,
} from "../results/persisted-versions-store.js";

const compareArea = document.getElementById("compare-area");
let persistedRunsState = { status: "idle", strategy: "", runs: [], allRuns: [], error: null };
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

export function initComparePanel() {
  if (!compareArea) return;

  initPersistedRunsStore();
  initPersistedVersionsStore();
  subscribePersistedRuns(handleRunsSnapshot);
  subscribePersistedVersions(handleVersionsSnapshot);
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

function workflowCandidatesLoaded() {
  return workflowModeActive() && versionsState.status === "ready";
}

function workflowHasLinkedCandidates() {
  return workflowCandidatesLoaded() && workflowCandidateVersions().length > 0;
}

function workflowMissingLinkedCandidates() {
  return workflowCandidatesLoaded() && workflowCandidateVersions().length === 0;
}

function workflowUsesGenericFallback() {
  return workflowMissingLinkedCandidates()
    || (workflowModeActive() && versionsState.status === "error");
}

function workflowFallbackNote() {
  if (!workflowUsesGenericFallback()) return "";
  if (versionsState.status === "error") {
    return `Workflow-linked candidates could not be loaded: ${versionsState.error || "Unknown error"}. Generic compare is still available across persisted runs, including different strategies.`;
  }
  return "No persisted candidates are linked to the current baseline run yet. Generic compare is still available across persisted runs, including different strategies.";
}

function pinWorkflowBaselineFallbackSelection() {
  const baselineRunId = workflowBaselineRunId();
  if (!baselineRunId || !comparableRuns.some((run) => run?.run_id === baselineRunId)) {
    return;
  }
  selectedLeftRunId = baselineRunId;
  selectedRightRunId = pickRetainedRightRunId(selectedLeftRunId, selectedRightRunId);
}

function workflowCandidateVersion() {
  const selected = getSelectedCandidateVersionId(workflowBaselineRunId());
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

async function loadVersions(strategy, options = {}) {
  if (!strategy) {
    setSelectedCandidateVersionId(null);
    await refreshPersistedVersions("", options);
    renderComparePanel();
    return;
  }

  await refreshPersistedVersions(strategy, { silent: Boolean(options?.silent) });
}

function handleVersionsSnapshot(snapshot) {
  versionsState = snapshot || { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };

  if (workflowModeActive()) {
    if (workflowHasLinkedCandidates()) {
      ensureSelectedCandidateVersion(versionsState.versions, workflowBaselineRunId());
    } else if (workflowUsesGenericFallback()) {
      pinWorkflowBaselineFallbackSelection();
    }
    renderComparePanel();
    void maybeLoadComparison();
    return;
  }

  renderComparePanel();
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
  comparableRuns = Array.isArray(snapshot?.allRuns)
    ? snapshot.allRuns.filter((run) => run?.summary_available)
    : Array.isArray(snapshot?.runs)
      ? snapshot.runs.filter((run) => run?.summary_available)
      : [];
  selectedLeftRunId = pickRetainedRunId(selectedLeftRunId, 0);
  selectedRightRunId = pickRetainedRightRunId(selectedLeftRunId, selectedRightRunId);

  if (workflowUsesGenericFallback()) {
    pinWorkflowBaselineFallbackSelection();
  }

  if (workflowHasLinkedCandidates()) {
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
  if (workflowHasLinkedCandidates()) {
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
    value: getSelectedCandidateVersionId(workflowBaselineRunId()),
    disabled: versionsState.status === "loading" || !workflowCandidateVersions().length,
    options: workflowCandidateVersions().map((version) => ({ value: version.version_id, label: formatWorkflowCandidateOption(version) })),
    onChange: (value) => {
      setSelectedCandidateVersionId(value || null, workflowBaselineRunId());
    },
  }));
  return toolbar;
}

function buildContextGrid(comparison, { leftTitle = "Left run", rightTitle = "Right run" } = {}) {
  const grid = el("div", { class: "compare-context-grid" });
  grid.appendChild(buildRunContext(comparison?.baseline || comparison?.left, leftTitle));
  grid.appendChild(buildRunContext(comparison?.candidate || comparison?.right, rightTitle));
  return grid;
}

function buildRunContext(run, title) {
  const metrics = run?.summary_metrics || {};
  const snapshot = run?.request_snapshot || {};
  const pairCount = Array.isArray(snapshot?.pairs) ? snapshot.pairs.length : null;
  const section = el("section", { class: "results-context" });
  section.innerHTML = `
    <div class="results-context__title">${escapeHtml(title)}</div>
    <div class="results-context__meta">
      <span><strong>Run ID:</strong> ${escapeHtml(run?.run_id || "-")}</span>
      <span><strong>Strategy:</strong> ${escapeHtml(metrics.strategy || run?.strategy || "-")}</span>
      <span><strong>Version:</strong> ${escapeHtml(run?.version_id || "-")}</span>
      <span><strong>Status:</strong> ${escapeHtml(labelize(run?.status))}</span>
      <span><strong>Timeframe:</strong> ${escapeHtml(snapshot?.timeframe || metrics?.timeframe || "-")}</span>
      <span><strong>Timerange:</strong> ${escapeHtml(snapshot?.timerange || "-")}</span>
      <span><strong>Pairs:</strong> ${escapeHtml(pairCount == null ? "-" : String(pairCount))}</span>
      <span><strong>Exchange:</strong> ${escapeHtml(snapshot?.exchange || "-")}</span>
      <span><strong>Config:</strong> ${escapeHtml(snapshot?.config_path || "-")}</span>
      <span><strong>Trigger:</strong> ${escapeHtml(labelize(run?.trigger_source || "-"))}</span>
      <span><strong>Created:</strong> ${escapeHtml(formatDate(run?.completed_at || run?.created_at))}</span>
    </div>
  `;
  return section;
}

function renderWorkflowCompare(layout) {
  layout.appendChild(buildWorkflowToolbar());

  const candidateVersion = workflowCandidateVersion();
  const candidateSourceTitle = candidateVersion?.source_context?.title || candidateVersion?.summary || candidateVersion?.source_ref || "selected candidate";

  if (versionsState.status === "loading") {
    layout.appendChild(el("div", { class: "compare-note" }, "Loading workflow-linked candidate versions..."));
    return;
  }
  if (versionsState.status === "error") {
    layout.appendChild(el("div", { class: "info-empty" }, `Failed to load workflow candidates: ${versionsState.error}`));
    return;
  }
  if (!workflowCandidateVersions().length) {
    layout.appendChild(el("div", { class: "info-empty" }, "No persisted candidates are linked to the current baseline run yet. Create one from Proposal Workflow first."));
    return;
  }

  const candidateRun = workflowCandidateRun();
  if (!candidateRun) {
    layout.appendChild(el("div", { class: "info-empty" }, `Re-run the selected candidate to create a persisted completed run before comparing it against the baseline run. Review the compare evidence here before any version decision. Current selection: ${candidateVersion?.version_id || '-'} | ${candidateSourceTitle}.`));
    return;
  }

  layout.appendChild(el("div", { class: "compare-note" }, `Baseline ${workflowBaselineRunId()} vs selected candidate ${candidateVersion?.version_id || '-'} on persisted rerun ${candidateRun.run_id}.`));

  if (compareLoading) {
    layout.appendChild(el("div", { class: "compare-note" }, "Loading persisted compare evidence for the baseline run and selected candidate..."));
  }
  if (compareError) {
    layout.appendChild(el("div", { class: "info-empty" }, `Persisted compare evidence is unavailable for the baseline run and selected candidate: ${compareError}`));
    return;
  }
  if (!lastComparison) {
    layout.appendChild(el("div", { class: "compare-note" }, "Select a candidate version to load decision-ready compare evidence against the current baseline run."));
    return;
  }

  layout.appendChild(buildContextGrid(lastComparison, { leftTitle: "Baseline", rightTitle: "Selected Candidate" }));
  const evidence = el("div", { class: "compare-evidence" });
  evidence.innerHTML = renderDecisionReadyCompare(lastComparison, {
    baselineLabel: "Baseline",
    candidateLabel: "Selected Candidate",
  });
  layout.appendChild(evidence);
  layout.appendChild(el("div", { class: "compare-note" }, "Use Compare after rerun and before any version decision. Decision evidence is grounded in persisted run summaries, request snapshots, and version artifacts only. Review it before choosing Accept as current strategy or Promote as new strategy variant."));
}

function renderGenericCompare(layout, { note = "" } = {}) {
  layout.appendChild(buildGenericToolbar());

  if (note) {
    layout.appendChild(el("div", { class: "compare-note" }, note));
  }

  if (persistedRunsState.status === "loading" && !persistedRunsState.runs.length) {
    layout.appendChild(el("div", { class: "info-empty" }, "Loading persisted backtest runs for compare..."));
    return;
  }
  if (persistedRunsState.status === "error") {
    layout.appendChild(el("div", { class: "info-empty" }, `Failed to load persisted compare runs: ${persistedRunsState.error}`));
    return;
  }
  if (!comparableRuns.length) {
    layout.appendChild(el("div", { class: "info-empty" }, "No persisted completed runs with saved summary artifacts are available to compare yet. Run a baseline backtest or candidate rerun first."));
    return;
  }
  if (!selectedLeftRunId || !selectedRightRunId || selectedLeftRunId === selectedRightRunId) {
    layout.appendChild(el("div", { class: "info-empty" }, "Select two different persisted runs to compare."));
    return;
  }
  if (compareLoading) {
    layout.appendChild(el("div", { class: "compare-note" }, "Loading persisted compare evidence for the selected runs..."));
  }
  if (compareError) {
    layout.appendChild(el("div", { class: "info-empty" }, `Persisted compare evidence is unavailable for the selected runs: ${compareError}`));
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
  layout.appendChild(el("div", { class: "compare-note" }, "Use Compare after rerun and before any version decision. Decision evidence is grounded in persisted run summaries, request snapshots, and version artifacts only. Delta is right minus left."));
}

function renderComparePanel() {
  if (!compareArea) return;
  compareArea.innerHTML = "";

  const layout = el("div", { class: "compare-layout" });

  if (workflowModeActive() && !workflowUsesGenericFallback()) {
    renderWorkflowCompare(layout);
  } else {
    renderGenericCompare(layout, { note: workflowFallbackNote() });
  }
  compareArea.appendChild(layout);
}
