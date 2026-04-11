/**
 * export-panel.js — Client-side exports for the latest unified results payload.
 */

import { on, EVENTS } from "../../../core/events.js";
import showToast from "../../../components/toast.js";
import { getLatestResultsPayload } from "../results/results-controller.js";

const exportArea = document.getElementById("export-area");
const exportCsvBtn = document.getElementById("btn-export-csv");
const exportJsonBtn = document.getElementById("btn-export-json");
let latestPayload = null;

export function initExportPanel() {
  if (!exportArea) return;

  ensureStatusElement();

  exportCsvBtn?.addEventListener("click", () => {
    if (!Array.isArray(latestPayload?.trades) || !latestPayload.trades.length) return;

    const csv = buildTradesCsv(latestPayload.trades);
    downloadBlob(`${slugify(latestPayload.strategy || "backtest")}-latest-trades.csv`, "text/csv;charset=utf-8", csv);
    showToast("Trades CSV exported.", "success");
  });

  exportJsonBtn?.addEventListener("click", () => {
    if (!latestPayload?.summary) return;

    const json = JSON.stringify(latestPayload.summary, null, 2);
    downloadBlob(`${slugify(latestPayload.strategy || "backtest")}-latest-summary.json`, "application/json;charset=utf-8", json);
    showToast("Summary JSON exported.", "success");
  });

  on(EVENTS.RESULTS_LOADED, (payload) => {
    latestPayload = payload;
    renderExportState(payload);
  });

  latestPayload = getLatestResultsPayload();
  renderExportState(latestPayload);
}

function renderExportState(payload) {
  const statusEl = ensureStatusElement();
  const hasSummary = Boolean(payload?.summary);
  const trades = Array.isArray(payload?.trades) ? payload.trades : [];

  if (exportCsvBtn) exportCsvBtn.disabled = !trades.length;
  if (exportJsonBtn) exportJsonBtn.disabled = !hasSummary;
  if (!statusEl) return;

  if (!hasSummary) {
    statusEl.className = "export-status export-status--muted";
    statusEl.textContent = "Load or run a backtest to enable exports from the latest result.";
    return;
  }

  statusEl.className = "export-status";
  statusEl.textContent = `${payload.strategy || "Latest result"} ready for export · ${trades.length} trade(s) available.`;
}

function ensureStatusElement() {
  if (!exportArea) return null;

  let statusEl = document.getElementById("export-status");
  if (!statusEl) {
    statusEl = document.createElement("div");
    statusEl.id = "export-status";
    statusEl.className = "export-status export-status--muted";
    exportArea.appendChild(statusEl);
  }

  return statusEl;
}

function buildTradesCsv(trades) {
  const columns = collectColumns(trades);
  const lines = [
    columns.join(","),
    ...trades.map((trade) => columns.map((column) => csvEscape(resolveTradeValue(trade, column))).join(",")),
  ];

  return `${lines.join("\r\n")}\r\n`;
}

function collectColumns(trades) {
  const preferred = [
    "pair",
    "profit_ratio",
    "profit_pct",
    "profit_abs",
    "profit_absolute",
    "open_date",
    "close_date",
    "trade_duration",
    "duration",
    "enter_tag",
    "exit_reason",
  ];
  const seen = new Set();
  const columns = [];

  preferred.forEach((column) => {
    if (trades.some((trade) => trade && column in trade)) {
      seen.add(column);
      columns.push(column);
    }
  });

  trades.forEach((trade) => {
    Object.keys(trade || {}).forEach((column) => {
      if (seen.has(column)) return;
      seen.add(column);
      columns.push(column);
    });
  });

  return columns;
}

function resolveTradeValue(trade, column) {
  const value = trade?.[column];
  if (value == null) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function csvEscape(value) {
  const escaped = String(value ?? "").replace(/"/g, '""');
  return /[",\r\n]/.test(escaped) ? `"${escaped}"` : escaped;
}

function downloadBlob(filename, mimeType, content) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function slugify(value) {
  return String(value || "backtest")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
