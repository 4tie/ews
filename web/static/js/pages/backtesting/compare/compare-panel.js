/**
 * compare-panel.js - Compares persisted backtest runs via the backend compare read.
 */

import api from "../../../core/api.js";
import { el, formatDate, formatNum, formatPct } from "../../../core/utils.js";
import {
  initPersistedRunsStore,
  subscribePersistedRuns,
} from "../results/persisted-runs-store.js";

const compareArea = document.getElementById("compare-area");
let persistedRunsState = { status: "idle", strategy: "", runs: [], error: null };
let comparableRuns = [];
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
  subscribePersistedRuns(handleRunsSnapshot);
}

function handleRunsSnapshot(snapshot) {
  persistedRunsState = snapshot;
  comparableRuns = Array.isArray(snapshot?.runs) ? snapshot.runs.filter((run) => run?.summary_available) : [];
  selectedLeftRunId = pickRetainedRunId(selectedLeftRunId, 0);
  selectedRightRunId = pickRetainedRightRunId(selectedLeftRunId, selectedRightRunId);

  if (!selectedLeftRunId || !selectedRightRunId || selectedLeftRunId === selectedRightRunId) {
    lastComparison = null;
    lastComparedPairKey = "";
    compareLoading = false;
    renderComparePanel();
    return;
  }

  const pairKey = `${selectedLeftRunId}:${selectedRightRunId}`;
  if (snapshot.status === "ready" && pairKey !== lastComparedPairKey && !compareLoading) {
    loadComparison();
    return;
  }

  renderComparePanel();
}

async function loadComparison() {
  if (!selectedLeftRunId || !selectedRightRunId || selectedLeftRunId === selectedRightRunId) {
    lastComparison = null;
    lastComparedPairKey = "";
    compareLoading = false;
    renderComparePanel();
    return;
  }

  const requestId = ++compareRequestId;
  compareLoading = true;
  compareError = null;
  renderComparePanel();

  try {
    const comparison = await api.backtest.compareRuns(selectedLeftRunId, selectedRightRunId);
    if (requestId !== compareRequestId) return;
    lastComparison = comparison;
    lastComparedPairKey = `${selectedLeftRunId}:${selectedRightRunId}`;
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

function renderComparePanel() {
  if (!compareArea) return;

  compareArea.innerHTML = "";

  const layout = el("div", { class: "compare-layout" });
  layout.appendChild(buildToolbar());

  if (persistedRunsState.status === "loading" && !persistedRunsState.runs.length) {
    layout.appendChild(el("div", { class: "info-empty" }, "Loading persisted backtest runs for compare..."));
    compareArea.appendChild(layout);
    return;
  }

  if (persistedRunsState.status === "error") {
    layout.appendChild(el("div", { class: "info-empty" }, `Failed to load persisted compare runs: ${persistedRunsState.error}`));
    compareArea.appendChild(layout);
    return;
  }

  if (!comparableRuns.length) {
    layout.appendChild(el("div", { class: "info-empty" }, "No persisted completed runs with saved summary artifacts are available to compare yet."));
    compareArea.appendChild(layout);
    return;
  }

  if (!selectedLeftRunId || !selectedRightRunId || selectedLeftRunId === selectedRightRunId) {
    layout.appendChild(el("div", { class: "info-empty" }, "Select two different persisted runs to compare."));
    compareArea.appendChild(layout);
    return;
  }

  if (compareLoading) {
    layout.appendChild(el("div", { class: "compare-note" }, "Loading persisted comparison..."));
  }

  if (compareError) {
    layout.appendChild(el("div", { class: "info-empty" }, `Unable to compare the selected runs: ${compareError}`));
    compareArea.appendChild(layout);
    return;
  }

  if (!lastComparison) {
    layout.appendChild(el("div", { class: "compare-note" }, "Choose the two saved runs you want to compare. The latest successful pair loads automatically."));
    compareArea.appendChild(layout);
    return;
  }

  layout.appendChild(buildContextGrid(lastComparison));
  layout.appendChild(buildMetricsTable(lastComparison));
  layout.appendChild(el("div", { class: "compare-note" }, "Compare rows are computed from the persisted run-linked summary artifacts. Delta is right minus left."));
  compareArea.appendChild(layout);
}

function buildToolbar() {
  const toolbar = el("div", { class: "compare-toolbar" });
  toolbar.appendChild(buildSelectField({
    label: "Left run",
    id: "compare-left-run",
    value: selectedLeftRunId,
    onChange: (value) => {
      selectedLeftRunId = value;
      if (selectedLeftRunId === selectedRightRunId) {
        selectedRightRunId = pickAlternateRunId(selectedLeftRunId);
      }
      lastComparison = null;
      lastComparedPairKey = "";
      compareError = null;
      loadComparison();
    },
  }));
  toolbar.appendChild(buildSelectField({
    label: "Right run",
    id: "compare-right-run",
    value: selectedRightRunId,
    onChange: (value) => {
      selectedRightRunId = value;
      if (selectedRightRunId === selectedLeftRunId) {
        selectedLeftRunId = pickAlternateRunId(selectedRightRunId);
      }
      lastComparison = null;
      lastComparedPairKey = "";
      compareError = null;
      loadComparison();
    },
  }));
  return toolbar;
}

function buildSelectField({ label, id, value, onChange }) {
  const wrapper = el("label", { class: "setup-field compare-toolbar__field" });
  wrapper.appendChild(el("span", { class: "form-label" }, label));

  const select = el("select", { class: "form-select", id });
  select.disabled = comparableRuns.length < 2 || persistedRunsState.status === "loading";
  comparableRuns.forEach((run) => {
    const option = el("option", { value: run.run_id }, formatRunOption(run));
    if (run.run_id === value) option.selected = true;
    select.appendChild(option);
  });
  select.addEventListener("change", (event) => onChange(event.target.value));
  wrapper.appendChild(select);
  return wrapper;
}

function buildContextGrid(comparison) {
  const grid = el("div", { class: "compare-context-grid" });
  grid.appendChild(buildRunContext(comparison.left, "Left run"));
  grid.appendChild(buildRunContext(comparison.right, "Right run"));
  return grid;
}

function buildRunContext(run, title) {
  const metrics = run?.summary_metrics || {};
  const profit = metrics.profit_total_pct == null ? "-" : formatPct(metrics.profit_total_pct);
  const tradeRange = formatTradeRange(metrics);
  const section = el("section", { class: "results-context" });
  section.innerHTML = `
    <div class="results-context__title">${title}</div>
    <div class="results-context__meta">
      <span><strong>Run ID:</strong> ${run?.run_id || "-"}</span>
      <span><strong>Strategy:</strong> ${metrics.strategy || run?.strategy || "-"}</span>
      <span><strong>Created:</strong> ${formatDate(run?.created_at)}</span>
      <span><strong>Status:</strong> ${labelize(run?.status)}</span>
      <span><strong>Total Profit:</strong> ${profit}</span>
      <span><strong>Trades:</strong> ${formatCount(metrics.total_trades)}</span>
      <span><strong>Pairs:</strong> ${formatCount(metrics.pair_count)}</span>
      <span><strong>Range:</strong> ${tradeRange}</span>
    </div>
  `;
  return section;
}

function buildMetricsTable(comparison) {
  const table = el("table", { class: "data-table compare-table" });
  table.innerHTML = `
    <thead>
      <tr>
        <th>Metric</th>
        <th>Left</th>
        <th>Right</th>
        <th>Delta</th>
      </tr>
    </thead>
  `;

  const tbody = el("tbody");
  const leftCurrency = comparison?.left?.summary_metrics?.stake_currency || "";
  const rightCurrency = comparison?.right?.summary_metrics?.stake_currency || leftCurrency;
  comparison?.metrics?.forEach((metric) => {
    const row = el("tr");
    const deltaClass = classifyDelta(metric.key, metric.delta);
    row.innerHTML = `
      <td>${metric.label}</td>
      <td>${formatMetricValue(metric.format, metric.left, leftCurrency)}</td>
      <td>${formatMetricValue(metric.format, metric.right, rightCurrency)}</td>
      <td class="${deltaClass}">${formatMetricValue(metric.format, metric.delta, rightCurrency, { signed: true })}</td>
    `;
    tbody.appendChild(row);
  });

  table.appendChild(tbody);
  return table;
}

function pickRetainedRunId(currentRunId, fallbackIndex) {
  if (currentRunId && comparableRuns.some((run) => run.run_id === currentRunId)) {
    return currentRunId;
  }
  return comparableRuns[fallbackIndex]?.run_id || "";
}

function pickRetainedRightRunId(leftRunId, currentRunId) {
  if (currentRunId && currentRunId !== leftRunId && comparableRuns.some((run) => run.run_id === currentRunId)) {
    return currentRunId;
  }
  return pickAlternateRunId(leftRunId);
}

function pickAlternateRunId(runId) {
  return comparableRuns.find((run) => run.run_id !== runId)?.run_id || "";
}

function formatRunOption(run) {
  const profit = run?.summary_metrics?.profit_total_pct;
  const profitLabel = profit == null ? "no profit metric" : formatPct(profit);
  const when = run?.completed_at || run?.created_at;
  return `${run.run_id} | ${run.strategy || "Unknown"} | ${labelize(run.status)} | ${profitLabel} | ${formatDate(when)}`;
}

function formatMetricValue(valueFormat, value, currency = "", options = {}) {
  if (value == null || value === "") return "-";
  if (valueFormat === "pct") return formatPct(value);
  if (valueFormat === "count") return formatCount(value);
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

function formatCount(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number)}` : "-";
}

function formatTradeRange(metrics) {
  if (metrics?.trade_start || metrics?.trade_end) {
    return `${formatDate(metrics.trade_start)} -> ${formatDate(metrics.trade_end)}`;
  }
  if (metrics?.timerange) {
    return formatTimerange(metrics.timerange);
  }
  return "No persisted trade range";
}

function formatTimerange(timerange) {
  const value = String(timerange || "");
  const parts = value.split("-");
  if (parts.length === 2 && parts[0].length === 8 && parts[1].length === 8) {
    return `${parts[0].slice(0, 4)}-${parts[0].slice(4, 6)}-${parts[0].slice(6, 8)} -> ${parts[1].slice(0, 4)}-${parts[1].slice(4, 6)}-${parts[1].slice(6, 8)}`;
  }
  return value || "No persisted trade range";
}

function classifyDelta(key, delta) {
  const number = Number(delta);
  if (!Number.isFinite(number) || number === 0) return "";
  if (key === "max_drawdown_pct") {
    return number < 0 ? "positive" : "negative";
  }
  return number > 0 ? "positive" : "negative";
}

function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
