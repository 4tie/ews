/**
 * compare-panel.js — Renders the current summary strategy comparison block.
 */

import { on, EVENTS } from "../../../core/events.js";
import { el } from "../../../core/utils.js";
import { getLatestResultsPayload } from "../results/results-controller.js";

const compareArea = document.getElementById("compare-area");

export function initComparePanel() {
  if (!compareArea) return;

  on(EVENTS.RESULTS_LOADED, renderComparison);
  renderComparison(getLatestResultsPayload());
}

function renderComparison(payload) {
  if (!compareArea) return;

  const comparison = payload?.summary?.strategy_comparison;
  if (!hasComparisonData(comparison)) {
    compareArea.innerHTML = `
      <div class="info-empty">
        No in-summary strategy comparison is available for the latest result. Comparing multiple saved results still needs backend support.
      </div>
    `;
    return;
  }

  compareArea.innerHTML = "";
  const rows = normalizeRows(comparison);

  if (rows?.length) {
    compareArea.appendChild(buildComparisonTable(rows));
  } else if (isObject(comparison)) {
    compareArea.appendChild(buildComparisonStats(comparison));
  } else {
    const pre = el("pre", { class: "compare-json" });
    pre.textContent = JSON.stringify(comparison, null, 2);
    compareArea.appendChild(pre);
  }

  compareArea.appendChild(el(
    "div",
    { class: "compare-note" },
    "This tab is driven by the latest summary payload only. Multi-result compare still needs backend support."
  ));
}

function buildComparisonTable(rows) {
  const table = el("table", { class: "data-table compare-table" });
  const columns = collectColumns(rows);
  const thead = el("thead");
  const headRow = el("tr");

  columns.forEach((column) => {
    headRow.appendChild(el("th", {}, labelize(column)));
  });

  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = el("tbody");
  rows.forEach((row) => {
    const tr = el("tr");
    columns.forEach((column) => {
      const td = el("td");
      td.textContent = formatValue(column, row[column]);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  table.appendChild(tbody);
  return table;
}

function buildComparisonStats(comparison) {
  const stats = el("div", { class: "compare-stats" });

  Object.entries(comparison).forEach(([key, value]) => {
    const item = el("div", { class: "compare-stat" });
    const label = el("span", { class: "compare-stat__label" }, labelize(key));
    const text = el("span", { class: "compare-stat__value" }, formatValue(key, value));
    item.appendChild(label);
    item.appendChild(text);
    stats.appendChild(item);
  });

  return stats;
}

function normalizeRows(comparison) {
  if (Array.isArray(comparison)) {
    return comparison.filter(isObject);
  }

  if (!isObject(comparison)) return null;

  const entries = Object.entries(comparison);
  if (entries.length && entries.every(([, value]) => isObject(value))) {
    return entries.map(([key, value]) => ({ strategy: value.strategy ?? value.key ?? key, ...value }));
  }

  return null;
}

function collectColumns(rows) {
  const preferred = ["strategy", "key", "pair", "profit_total_pct", "profit_total", "total_trades"];
  const seen = new Set();
  const columns = [];

  preferred.forEach((column) => {
    if (rows.some((row) => column in row)) {
      seen.add(column);
      columns.push(column);
    }
  });

  rows.forEach((row) => {
    Object.entries(row).forEach(([key, value]) => {
      if (seen.has(key) || isObject(value) || Array.isArray(value)) return;
      seen.add(key);
      columns.push(key);
    });
  });

  return columns;
}

function formatValue(key, value) {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (/pct|percent|drawdown|winrate/i.test(key)) return value.toFixed(2);
    return Number.isInteger(value) ? String(value) : value.toFixed(Math.abs(value) >= 10 ? 2 : 4);
  }
  if (Array.isArray(value) || isObject(value)) return JSON.stringify(value);
  return String(value);
}

function hasComparisonData(comparison) {
  if (Array.isArray(comparison)) return comparison.length > 0;
  if (isObject(comparison)) return Object.keys(comparison).length > 0;
  return Boolean(comparison);
}

function labelize(key) {
  return String(key)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}
