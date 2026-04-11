/**
 * data-validator.js - Validate data availability and timerange coverage before running backtest.
 */

import api from "../../../core/api.js";
import { getState } from "../../../core/state.js";
import showToast from "../../../components/toast.js";
import { setButtonLoading } from "../../../components/loading-state.js";

const validateBtn = document.getElementById("btn-validate-data");
const validationOutput = document.getElementById("data-validation-output");

const STATUS_LABELS = {
  valid: "Ready",
  partial: "Partial",
  missing: "Missing",
  empty: "Empty",
  invalid: "Invalid",
  unknown: "Unknown",
  unconfigured: "Unconfigured",
};

const STATUS_ORDER = {
  invalid: 0,
  partial: 1,
  missing: 2,
  empty: 3,
  unknown: 4,
  unconfigured: 5,
  valid: 6,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function buildTimerange(startDate, endDate) {
  return startDate && endDate
    ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
    : undefined;
}

function formatStatusCounts(counts = {}) {
  return Object.entries(counts)
    .sort((a, b) => (STATUS_ORDER[a[0]] ?? 99) - (STATUS_ORDER[b[0]] ?? 99))
    .map(([status, count]) => {
      const label = STATUS_LABELS[status] || status;
      return `<span class="validation-pill validation-pill--${escapeHtml(status)}">${escapeHtml(label)}: ${escapeHtml(count)}</span>`;
    })
    .join("");
}

function renderMetaRow(label, value) {
  if (value == null || value === "") return "";
  return `<span><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</span>`;
}

function renderItem(item) {
  const status = String(item.status || "unknown");
  const statusLabel = STATUS_LABELS[status] || status;
  const coverageLabel = item.coverage_start || item.coverage_end
    ? `${item.coverage_start || "—"} -> ${item.coverage_end || "—"}`
    : "";
  const requestedLabel = item.requested_start || item.requested_end
    ? `${item.requested_start || "—"} -> ${item.requested_end || "—"}`
    : "";

  return `
    <li class="validation-item validation-item--${escapeHtml(status)}">
      <div class="validation-item__header">
        <span class="validation-pill validation-pill--${escapeHtml(status)}">${escapeHtml(statusLabel)}</span>
        <strong class="validation-item__pair">${escapeHtml(item.pair || "Unknown pair")}</strong>
      </div>
      <div class="validation-item__message">${escapeHtml(item.message || statusLabel)}</div>
      <div class="validation-item__meta">
        ${renderMetaRow("Exchange", item.exchange)}
        ${renderMetaRow("Timeframe", item.timeframe)}
        ${renderMetaRow("Coverage", coverageLabel)}
        ${renderMetaRow("Requested", requestedLabel)}
        ${renderMetaRow("Candles", item.candle_count)}
        ${renderMetaRow("File", item.file_name || item.file_path)}
      </div>
    </li>
  `;
}

function renderResult(payload) {
  if (!validationOutput) return;

  const results = Array.isArray(payload?.results) ? [...payload.results] : [];
  const summary = payload?.summary || {};

  if (!results.length) {
    validationOutput.innerHTML = '<span class="muted">No validation results were returned.</span>';
    showToast("No validation results were returned.", "warning");
    return;
  }

  results.sort((left, right) => {
    const leftRank = STATUS_ORDER[String(left?.status || "unknown")] ?? 99;
    const rightRank = STATUS_ORDER[String(right?.status || "unknown")] ?? 99;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return String(left?.pair || "").localeCompare(String(right?.pair || ""));
  });

  const summaryClass = payload?.valid ? "validation-summary validation-summary--valid" : "validation-summary validation-summary--warning";
  const timerange = summary.timerange || "Latest available candles";
  const countsMarkup = formatStatusCounts(summary.status_counts || {});
  const listMarkup = results.map(renderItem).join("");

  validationOutput.innerHTML = `
    <div class="${summaryClass}">
      <div class="validation-summary__headline">${escapeHtml(payload?.message || "Validation complete")}</div>
      <div class="validation-summary__meta">
        <span><strong>Exchange:</strong> ${escapeHtml(summary.exchange || "—")}</span>
        <span><strong>Timeframe:</strong> ${escapeHtml(summary.timeframe || "—")}</span>
        <span><strong>Requested:</strong> ${escapeHtml(timerange)}</span>
      </div>
      ${countsMarkup ? `<div class="validation-summary__counts">${countsMarkup}</div>` : ""}
    </div>
    <ul class="validation-list">${listMarkup}</ul>
  `;

  if (payload?.valid) {
    showToast(payload.message || "All pairs have valid data.", "success");
  } else if ((summary.ready_count || 0) > 0) {
    showToast(payload?.message || "Some pairs have incomplete data.", "warning");
  } else {
    showToast(payload?.message || "No pairs are ready for the selected range.", "error");
  }
}

export function initDataValidator() {
  validateBtn?.addEventListener("click", async () => {
    const pairs = getState("backtest.pairs") || [];
    const timeframe = getState("backtest.timeframe");
    const exchange = getState("backtest.exchange") || "binance";
    const startDate = getState("backtest.startDate");
    const endDate = getState("backtest.endDate");
    const timerange = buildTimerange(startDate, endDate);

    if (!pairs.length) {
      showToast("Add pairs first.", "warning");
      return;
    }
    if (!timeframe) {
      showToast("Select a timeframe first.", "warning");
      return;
    }

    setButtonLoading(validateBtn, true, "Checking...");
    if (validationOutput) {
      validationOutput.textContent = timerange
        ? "Checking candle coverage for the selected range..."
        : "Checking data availability...";
    }

    try {
      const data = await api.backtest.validateData({ pairs, timeframe, exchange, timerange });
      renderResult(data);
    } catch (err) {
      const message = err?.message || String(err);
      if (validationOutput) validationOutput.textContent = `Error: ${message}`;
      showToast("Validation failed: " + message, "error");
    } finally {
      setButtonLoading(validateBtn, false);
    }
  });
}
