/**
 * proposal-workflow.js - Run-scoped proposal, candidate, rerun, compare, and decision workflow.
 */

import api from "../../../core/api.js";
import { getState } from "../../../core/state.js";
import { on, EVENTS } from "../../../core/events.js";
import { formatDate, formatNum, formatPct } from "../../../core/utils.js";
import showToast from "../../../components/toast.js";
import { startBacktestRun } from "../run/run-controller.js";
import { initPersistedRunsStore, subscribePersistedRuns } from "./persisted-runs-store.js";

const root = document.getElementById("summary-proposals");


let latestPayload = null;
let runsSnapshot = { status: "idle", strategy: "", runs: [], error: null };
let versionsState = { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
let compareState = { status: "idle", key: "", data: null, error: null };
let versionsRequestId = 0;
let compareRequestId = 0;
let busyAction = "";

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function resolveStrategy() {
  return getState("backtest.strategy") || latestPayload?.strategy || runsSnapshot.strategy || versionsState.strategy || "";
}

function currentBaselineRunId() {
  return latestPayload?.run_id || null;
}

function currentBaselineVersionId() {
  return latestPayload?.version_id || null;
}

function canShowWorkflow() {
  return Boolean(root && latestPayload?.diagnosis_status === "ready" && latestPayload?.summary_available && currentBaselineRunId());
}

function requiresExactBaselineVersion() {
  return Boolean(currentBaselineVersionId());
}

function getWorkflowVersions() {
  const baselineRunId = currentBaselineRunId();
  if (!baselineRunId) return [];
  const sourceRef = `backtest_run:${baselineRunId}`;
  return Array.isArray(versionsState.versions)
    ? versionsState.versions.filter((version) => version?.source_ref === sourceRef)
    : [];
}

function currentCandidateVersion() {
  return getWorkflowVersions()[0] || null;
}

function getCandidateRuns(candidateVersionId) {
  if (!candidateVersionId) return [];
  return (runsSnapshot.runs || [])
    .filter((run) => run?.version_id === candidateVersionId)
    .slice()
    .sort((left, right) => String(right?.completed_at || right?.created_at || "").localeCompare(String(left?.completed_at || left?.created_at || "")));
}

function currentCandidateRun() {
  const candidate = currentCandidateVersion();
  return getCandidateRuns(candidate?.version_id)[0] || null;
}

function currentComparableCandidateRun() {
  return getCandidateRuns(currentCandidateVersion()?.version_id).find((run) => run?.status === "completed" && run?.summary_available) || null;
}

function renderEmptyState(message) {
  if (!root) return;
  root.innerHTML = message ? `<section class="results-context results-context--empty"><div class="results-context__title">Proposal Workflow</div><div class="results-context__note">${escapeHtml(message)}</div></section>` : "";
}

function formatMetricValue(valueFormat, value, currency = "", options = {}) {
  if (value == null || value === "") return "-";
  if (valueFormat === "pct") return formatPct(value);
  if (valueFormat === "count") {
    const number = Number(value);
    return Number.isFinite(number) ? `${Math.round(number)}` : String(value);
  }
  if (valueFormat === "money") {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    const prefix = options.signed && number > 0 ? "+" : "";
    return `${prefix}${formatNum(number, 2)}${currency ? ` ${currency}` : ""}`;
  }
  const number = Number(value);
  if (Number.isFinite(number)) {
    const prefix = options.signed && number > 0 ? "+" : "";
    return `${prefix}${formatNum(number, 3)}`;
  }
  return String(value);
}

function renderPrimaryFlags() {
  const items = Array.isArray(latestPayload?.diagnosis?.primary_flags) ? latestPayload.diagnosis.primary_flags : [];
  const body = items.length
    ? `<div class="proposal-flags">${items.map((flag) => {
        const severity = String(flag?.severity || "warning");
        return `
          <article class="proposal-flag proposal-flag--${escapeHtml(severity)}">
            <div class="proposal-flag__header">
              <span class="proposal-flag__rule">${escapeHtml(flag?.rule || "issue")}</span>
              <span class="proposal-flag__severity">${escapeHtml(labelize(severity))}</span>
            </div>
            <div class="proposal-flag__message">${escapeHtml(flag?.message || "No summary available.")}</div>
          </article>
        `;
      }).join("")}</div>`
    : '<div class="results-context__note">No pinned flags are currently available for this run.</div>';

  return `
    <section class="results-context">
      <div class="results-context__title">Primary Flags</div>
      ${body}
    </section>
  `;
}

function renderRankedIssue(item) {
  const severity = labelize(item?.severity || "warning");
  const message = item?.message || item?.rule || "Ranked issue";
  const distance = item?.threshold_distance == null ? "-" : formatNum(item.threshold_distance, 2);
  return `
    <div class="proposal-item__body">${escapeHtml(message)}</div>
    <div class="proposal-item__meta">
      <span><strong>Rule:</strong> ${escapeHtml(item?.rule || "-")}</span>
      <span><strong>Severity:</strong> ${escapeHtml(severity)}</span>
      <span><strong>Distance:</strong> ${escapeHtml(distance)}</span>
    </div>
  `;
}

function renderParameterHint(item) {
  const parameters = Array.isArray(item?.parameters) ? item.parameters.join(", ") : "-";
  return `
    <div class="proposal-item__body">${escapeHtml(item?.rationale || item?.rule || "Parameter hint")}</div>
    <div class="proposal-item__meta">
      <span><strong>Rule:</strong> ${escapeHtml(item?.rule || "-")}</span>
      <span><strong>Parameters:</strong> ${escapeHtml(parameters)}</span>
    </div>
  `;
}

function renderAiSuggestion(item) {
  const name = item?.name || item?.parameter || item?.key || "AI suggestion";
  const value = item?.value == null ? "-" : String(item.value);
  const reason = item?.reason || item?.rationale || item?.summary || "AI suggestion grounded in the latest diagnosis.";
  return `
    <div class="proposal-item__body">${escapeHtml(reason)}</div>
    <div class="proposal-item__meta">
      <span><strong>Name:</strong> ${escapeHtml(name)}</span>
      <span><strong>Value:</strong> ${escapeHtml(value)}</span>
    </div>
  `;
}

function renderDeterministicAction(item) {
  const parameters = Array.isArray(item?.parameters) ? item.parameters.join(", ") : "-";
  const matchedRules = Array.isArray(item?.matched_rules) ? item.matched_rules.join(", ") : "-";
  return `
    <div class="proposal-item__body">${escapeHtml(item?.summary || item?.message || "Diagnosis-backed deterministic action")}</div>
    <div class="proposal-item__meta">
      <span><strong>Action:</strong> ${escapeHtml(item?.label || item?.action_type || "-")}</span>
      <span><strong>Rules:</strong> ${escapeHtml(matchedRules)}</span>
      <span><strong>Parameters:</strong> ${escapeHtml(parameters)}</span>
    </div>
  `;
}

function renderActionSection({ title, sourceKind, items, note, renderer }) {
  const body = items.length
    ? items.map((item, index) => {
        const actionKey = `create:${sourceKind}:${index}`;
        const disabled = busyAction && busyAction !== actionKey ? " disabled" : "";
        const loading = busyAction === actionKey;
        const actionTypeAttr = item?.action_type ? ` data-action-type="${escapeHtml(item.action_type)}"` : "";
        return `
          <article class="proposal-item">
            <div class="proposal-item__header">
              <div>
                <div class="proposal-item__title">${escapeHtml(item?.label || item?.rule || item?.name || item?.parameter || item?.key || `${title} ${index + 1}`)}</div>
                <div class="proposal-item__subtitle">${escapeHtml(sourceKind.replace(/_/g, " "))}</div>
              </div>
              <button type="button" class="btn btn--secondary btn--sm" data-action="create-candidate" data-source-kind="${escapeHtml(sourceKind)}" data-source-index="${index}"${actionTypeAttr}${disabled}>${loading ? "Creating..." : "Create Candidate"}</button>
            </div>
            ${renderer(item)}
          </article>
        `;
      }).join("")
    : `<div class="results-context__note">${escapeHtml(note)}</div>`;

  return `
    <section class="results-context">
      <div class="results-context__title">${escapeHtml(title)}</div>
      <div class="proposal-items">${body}</div>
    </section>
  `;
}

function renderWorkflowState() {
  const candidate = currentCandidateVersion();
  if (!candidate) {
    return `
      <section class="results-context results-context--empty results-context--table">
        <div class="results-context__title">Candidate State</div>
        <div class="results-context__note">Create a candidate from one of the diagnosis-backed proposal sources to start the run-scoped workflow.</div>
      </section>
    `;
  }

  const baselineRunId = currentBaselineRunId();
  const baselineVersionId = currentBaselineVersionId() || "Unavailable on baseline run";
  const exactBaseline = requiresExactBaselineVersion();
  const candidateRun = currentCandidateRun();
  const rerunBusy = busyAction === "rerun-candidate";
  const acceptBusy = busyAction === "accept-candidate";
  const rejectBusy = busyAction === "reject-candidate";
  const rollbackBusy = busyAction === "rollback-baseline";
  const anyBusy = Boolean(busyAction);

  const candidateRunLabel = candidateRun
    ? `${labelize(candidateRun.status)} | ${formatDate(candidateRun.completed_at || candidateRun.created_at)}`
    : "Not rerun yet";
  const exactBaselineNote = exactBaseline
    ? "Accept and rollback stay enabled because this run already points to an exact version."
    : "Baseline run has no exact version_id. Candidate creation and rerun are available, but accept and rollback stay disabled to avoid promoting against an ambiguous baseline.";

  return `
    <section class="results-context results-context--table">
      <div class="results-context__title">Candidate State</div>
      <div class="results-context__meta proposal-state-grid">
        <span><strong>Baseline Run:</strong> ${escapeHtml(baselineRunId || "-")}</span>
        <span><strong>Baseline Version:</strong> ${escapeHtml(baselineVersionId)}</span>
        <span><strong>Candidate Version:</strong> ${escapeHtml(candidate.version_id || "-")}</span>
        <span><strong>Candidate Status:</strong> ${escapeHtml(labelize(candidate.status))}</span>
        <span><strong>Candidate Type:</strong> ${escapeHtml(labelize(candidate.change_type))}</span>
        <span><strong>Source:</strong> ${escapeHtml(candidate.summary || candidate.source_ref || "-")}</span>
        <span><strong>Candidate Run:</strong> ${escapeHtml(candidateRunLabel)}</span>
        <span><strong>Created:</strong> ${escapeHtml(formatDate(candidate.created_at))}</span>
      </div>
      <div class="results-context__note">${escapeHtml(exactBaselineNote)}</div>
      <div class="proposal-actions">
        <button type="button" class="btn btn--secondary btn--sm" data-action="rerun-candidate"${anyBusy && !rerunBusy ? " disabled" : ""}>${rerunBusy ? "Starting..." : "Re-run Candidate"}</button>
        <button type="button" class="btn btn--secondary btn--sm" data-action="accept-candidate"${!exactBaseline || (anyBusy && !acceptBusy) ? " disabled" : ""}>${acceptBusy ? "Accepting..." : "Accept"}</button>
        <button type="button" class="btn btn--ghost btn--sm" data-action="reject-candidate"${anyBusy && !rejectBusy ? " disabled" : ""}>${rejectBusy ? "Rejecting..." : "Reject"}</button>
        <button type="button" class="btn btn--ghost btn--sm" data-action="rollback-baseline"${!exactBaseline || (anyBusy && !rollbackBusy) ? " disabled" : ""}>${rollbackBusy ? "Rolling Back..." : "Rollback"}</button>
      </div>
    </section>
  `;
}

function renderCompareSection() {
  const candidate = currentCandidateVersion();
  const candidateRun = currentComparableCandidateRun();
  if (!candidate) {
    return "";
  }
  if (!candidateRun) {
    return `
      <section class="results-context results-context--table results-context--empty">
        <div class="results-context__title">Candidate Compare</div>
        <div class="results-context__note">Run the current candidate to compare it against the baseline run inline.</div>
      </section>
    `;
  }
  if (compareState.status === "loading") {
    return `
      <section class="results-context results-context--table results-context--empty">
        <div class="results-context__title">Candidate Compare</div>
        <div class="results-context__note">Loading inline compare for baseline ${escapeHtml(currentBaselineRunId())} vs candidate run ${escapeHtml(candidateRun.run_id)}.</div>
      </section>
    `;
  }
  if (compareState.status === "error") {
    return `
      <section class="results-context results-context--table results-context--empty">
        <div class="results-context__title">Candidate Compare</div>
        <div class="results-context__note">${escapeHtml(compareState.error || "Inline compare failed.")}</div>
      </section>
    `;
  }
  if (!compareState.data) {
    return "";
  }

  const rows = Array.isArray(compareState.data?.metrics) ? compareState.data.metrics : [];
  const leftCurrency = compareState.data?.left?.summary_metrics?.stake_currency || "";
  const rightCurrency = compareState.data?.right?.summary_metrics?.stake_currency || leftCurrency;

  return `
    <section class="results-context results-context--table">
      <div class="results-context__title">Candidate Compare</div>
      <div class="results-context__note">Baseline run ${escapeHtml(currentBaselineRunId())} vs latest candidate run ${escapeHtml(candidateRun.run_id)}.</div>
      <div class="results-context__table">
        <table class="data-table compare-table proposal-compare-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>Candidate</th>
              <th>Delta</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((metric) => {
              const deltaClass = classifyDelta(metric.key, metric.delta);
              return `
                <tr>
                  <td>${escapeHtml(metric.label)}</td>
                  <td>${escapeHtml(formatMetricValue(metric.format, metric.left, leftCurrency))}</td>
                  <td>${escapeHtml(formatMetricValue(metric.format, metric.right, rightCurrency))}</td>
                  <td class="${escapeHtml(deltaClass)}">${escapeHtml(formatMetricValue(metric.format, metric.delta, rightCurrency, { signed: true }))}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function classifyDelta(key, delta) {
  const number = Number(delta);
  if (!Number.isFinite(number) || number === 0) return "";
  if (key === "max_drawdown_pct") {
    return number < 0 ? "positive" : "negative";
  }
  return number > 0 ? "positive" : "negative";
}

function render() {
  if (!root) return;

  if (!resolveStrategy()) {
    renderEmptyState("");
    return;
  }
  if (!latestPayload) {
    renderEmptyState("");
    return;
  }
  if (latestPayload?.diagnosis_status !== "ready" || !latestPayload?.summary_available) {
    renderEmptyState("");
    return;
  }

  const rankedIssues = Array.isArray(latestPayload?.diagnosis?.ranked_issues) ? latestPayload.diagnosis.ranked_issues : [];
  const parameterHints = Array.isArray(latestPayload?.diagnosis?.parameter_hints) ? latestPayload.diagnosis.parameter_hints : [];
  const deterministic_actions = Array.isArray(latestPayload?.diagnosis?.proposal_actions) ? latestPayload.diagnosis.proposal_actions : [];
  const aiSuggestions = latestPayload?.ai?.ai_status === "ready" && Array.isArray(latestPayload?.ai?.parameter_suggestions)
    ? latestPayload.ai.parameter_suggestions
    : [];
  const aiNote = latestPayload?.ai?.ai_status === "unavailable"
    ? "AI suggestions are unavailable for this run right now. Deterministic proposal sources remain usable."
    : "No AI parameter suggestions were returned for this run.";

  root.innerHTML = `
    ${renderPrimaryFlags()}
    ${renderActionSection({
      title: "Deterministic Actions",
      sourceKind: "deterministic_action",
      items: deterministic_actions,
      note: "No deterministic actions are recommended for this run based on the diagnosis flags.",
      renderer: renderDeterministicAction,
    })}
    ${renderActionSection({
      title: "Ranked Issues",
      sourceKind: "ranked_issue",
      items: rankedIssues,
      note: "No ranked issues are available for this run.",
      renderer: renderRankedIssue,
    })}
    ${renderActionSection({
      title: "Parameter Hints",
      sourceKind: "parameter_hint",
      items: parameterHints,
      note: "No deterministic parameter hints are available for this run.",
      renderer: renderParameterHint,
    })}
    ${renderActionSection({
      title: "AI Parameter Suggestions",
      sourceKind: "ai_parameter_suggestion",
      items: aiSuggestions,
      note: aiNote,
      renderer: renderAiSuggestion,
    })}
    ${renderWorkflowState()}
    ${renderCompareSection()}
  `;
}

async function loadVersions(strategy, options = {}) {
  if (!strategy) {
    versionsState = { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
    render();
    return;
  }

  const requestId = ++versionsRequestId;
  if (!options.silent) {
    versionsState = { ...versionsState, status: "loading", strategy, error: null };
    render();
  }

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
    render();
    void ensureCompareLoaded();
  } catch (error) {
    if (requestId !== versionsRequestId) return;
    versionsState = {
      status: "error",
      strategy,
      versions: [],
      activeVersionId: null,
      error: error?.message || String(error),
    };
    render();
  }
}

async function ensureCompareLoaded() {
  if (!canShowWorkflow()) {
    compareState = { status: "idle", key: "", data: null, error: null };
    render();
    return;
  }

  const candidateRun = currentComparableCandidateRun();
  if (!candidateRun) {
    compareState = { status: "idle", key: "", data: null, error: null };
    render();
    return;
  }

  const key = `${currentBaselineRunId()}:${candidateRun.run_id}`;
  if (compareState.key === key && (compareState.status === "ready" || compareState.status === "loading")) {
    return;
  }

  const requestId = ++compareRequestId;
  compareState = { status: "loading", key, data: null, error: null };
  render();

  try {
    const comparison = await api.backtest.compareRuns(currentBaselineRunId(), candidateRun.run_id);
    if (requestId !== compareRequestId) return;
    compareState = { status: "ready", key, data: comparison, error: null };
    render();
  } catch (error) {
    if (requestId !== compareRequestId) return;
    compareState = { status: "error", key, data: null, error: error?.message || String(error) };
    render();
  }
}

async function handleCreateCandidate(sourceKind, sourceIndex, actionType) {
  const baselineRunId = currentBaselineRunId();
  if (!baselineRunId) {
    showToast("No baseline run is loaded for proposal creation.", "warning");
    return;
  }

  busyAction = `create:${sourceKind}:${sourceIndex}`;
  render();

  try {
    const payload = {
      source_kind: sourceKind,
      source_index: Number(sourceIndex),
      candidate_mode: "auto",
    };
    if (actionType) {
      payload.action_type = actionType;
    }
    const response = await api.backtest.createProposalCandidate(baselineRunId, payload);
    showToast(response?.candidate_version_id ? `Candidate ${response.candidate_version_id} created.` : "Candidate created.", "success");
    await loadVersions(resolveStrategy(), { silent: true });
    await ensureCompareLoaded();
  } catch (error) {
    showToast(`Failed to create candidate: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

async function handleRerunCandidate() {
  const candidate = currentCandidateVersion();
  const baselineRunId = currentBaselineRunId();
  if (!candidate?.version_id || !baselineRunId) {
    showToast("Candidate rerun context is incomplete.", "warning");
    return;
  }

  busyAction = "rerun-candidate";
  render();

  try {
    const response = await api.backtest.getRun(baselineRunId);
    const baselineRun = response?.run;
    const snapshot = isObject(baselineRun?.request_snapshot) ? baselineRun.request_snapshot : null;
    if (!snapshot?.strategy || !snapshot?.timeframe) {
      throw new Error("Baseline run request snapshot is missing required strategy launch fields.");
    }

    await startBacktestRun({
      strategy: snapshot.strategy,
      timeframe: snapshot.timeframe,
      timerange: snapshot.timerange || undefined,
      pairs: Array.isArray(snapshot.pairs) ? snapshot.pairs : [],
      exchange: snapshot.exchange || "binance",
      max_open_trades: snapshot.max_open_trades ?? undefined,
      dry_run_wallet: snapshot.dry_run_wallet ?? undefined,
      config_path: snapshot.config_path || undefined,
      extra_flags: Array.isArray(snapshot.extra_flags) ? snapshot.extra_flags : [],
      version_id: candidate.version_id,
      trigger_source: "ai_apply",
    });
  } catch (error) {
    showToast(`Failed to start candidate rerun: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

async function handleAcceptCandidate() {
  const strategy = resolveStrategy();
  const candidate = currentCandidateVersion();
  if (!strategy || !candidate?.version_id) {
    showToast("No candidate is available to accept.", "warning");
    return;
  }
  if (!requiresExactBaselineVersion()) {
    showToast("Baseline run is missing an exact version link, so accept stays disabled for this workflow.", "warning");
    return;
  }

  busyAction = "accept-candidate";
  render();

  try {
    const response = await api.versions.accept(strategy, {
      version_id: candidate.version_id,
      notes: `Accepted from proposal workflow using baseline run ${currentBaselineRunId()}`,
    });
    showToast(response?.message || `Accepted ${candidate.version_id}.`, "success");
    await loadVersions(strategy, { silent: true });
  } catch (error) {
    showToast(`Failed to accept candidate: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

async function handleRejectCandidate() {
  const strategy = resolveStrategy();
  const candidate = currentCandidateVersion();
  if (!strategy || !candidate?.version_id) {
    showToast("No candidate is available to reject.", "warning");
    return;
  }

  busyAction = "reject-candidate";
  render();

  try {
    const response = await api.versions.reject(strategy, {
      version_id: candidate.version_id,
      reason: `Rejected from proposal workflow using baseline run ${currentBaselineRunId()}`,
    });
    showToast(response?.message || `Rejected ${candidate.version_id}.`, "success");
    await loadVersions(strategy, { silent: true });
  } catch (error) {
    showToast(`Failed to reject candidate: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

async function handleRollbackBaseline() {
  const strategy = resolveStrategy();
  const baselineVersionId = currentBaselineVersionId();
  if (!strategy || !baselineVersionId) {
    showToast("Baseline version is unavailable for rollback.", "warning");
    return;
  }

  busyAction = "rollback-baseline";
  render();

  try {
    const response = await api.versions.rollback(strategy, {
      target_version_id: baselineVersionId,
      reason: `Rollback to baseline run ${currentBaselineRunId()} from proposal workflow`,
    });
    showToast(response?.message || `Rolled back to ${baselineVersionId}.`, "success");
    await loadVersions(strategy, { silent: true });
  } catch (error) {
    showToast(`Failed to rollback baseline: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

function handleRootClick(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action || "";

  if (action === "create-candidate") {
    const sourceKind = button.dataset.sourceKind || "";
    const sourceIndex = button.dataset.sourceIndex || "0";
    const actionType = button.dataset.actionType || null;
    void handleCreateCandidate(sourceKind, sourceIndex, actionType);
    return;
  }
  if (action === "rerun-candidate") {
    void handleRerunCandidate();
    return;
  }
  if (action === "accept-candidate") {
    void handleAcceptCandidate();
    return;
  }
  if (action === "reject-candidate") {
    void handleRejectCandidate();
    return;
  }
  if (action === "rollback-baseline") {
    void handleRollbackBaseline();
  }
}

export function initProposalWorkflow() {
  if (!root) return;

  initPersistedRunsStore();
  root.addEventListener("click", handleRootClick);
  subscribePersistedRuns((snapshot) => {
    runsSnapshot = snapshot || { status: "idle", strategy: "", runs: [], error: null };
    render();
    void ensureCompareLoaded();
  });

  on(EVENTS.RESULTS_LOADED, (payload) => {
    latestPayload = payload || null;
    render();
    void loadVersions(resolveStrategy(), { silent: false });
  });

  render();
}
