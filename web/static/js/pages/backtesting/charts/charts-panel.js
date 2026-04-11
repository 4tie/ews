/**
 * charts-panel.js — Renders charts from the unified latest-results payload.
 */

import { on, EVENTS } from "../../../core/events.js";
import { el, formatDate, formatNum, formatPct } from "../../../core/utils.js";
import { getLatestResultsPayload } from "../results/results-controller.js";

const workspace = document.getElementById("charts-workspace");
const MAX_PAIR_BARS = 10;
const SVG_WIDTH = 640;
const SVG_HEIGHT = 220;
const PADDING = { top: 20, right: 24, bottom: 28, left: 24 };

export function initChartsPanel() {
  if (!workspace) return;

  on(EVENTS.RESULTS_LOADED, renderCharts);

  const cached = getLatestResultsPayload();
  if (cached) renderCharts(cached);
}

function renderCharts(payload) {
  if (!workspace) return;

  const trades = Array.isArray(payload?.trades) ? payload.trades : [];
  const pairRows = normalizePairRows(payload?.results_per_pair);

  if (!trades.length && !pairRows.length) {
    workspace.innerHTML = '<div class="info-empty">No latest result data is available for charts yet.</div>';
    return;
  }

  const grid = el("div", { class: "results-visual-grid" });
  grid.appendChild(renderEquityCard(trades));
  grid.appendChild(renderPairBarsCard(pairRows));

  workspace.innerHTML = "";
  workspace.appendChild(grid);
}

function renderEquityCard(trades) {
  const card = el("section", { class: "results-visual-card results-visual-card--chart" });
  const header = el("div", { class: "results-visual-card__header" });
  header.innerHTML = `
    <div>
      <h3 class="results-visual-card__title">Equity Curve</h3>
      <p class="results-visual-card__subtitle">Derived from the latest trades only.</p>
    </div>
  `;
  card.appendChild(header);

  const series = buildEquitySeries(trades);
  if (!series) {
    card.appendChild(el("div", { class: "info-empty" }, "No closed trades are available for an equity chart."));
    return card;
  }

  const values = series.points.map((point) => point.value);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const span = max - min || 1;
  const plotWidth = SVG_WIDTH - PADDING.left - PADDING.right;
  const plotHeight = SVG_HEIGHT - PADDING.top - PADDING.bottom;
  const denominator = Math.max(series.points.length - 1, 1);

  const points = series.points.map((point, index) => {
    const x = PADDING.left + (index / denominator) * plotWidth;
    const y = PADDING.top + ((max - point.value) / span) * plotHeight;
    return { x, y };
  });

  const pointList = points.map((point) => `${point.x},${point.y}`).join(" ");
  const zeroY = PADDING.top + ((max - 0) / span) * plotHeight;
  const lastValue = series.points[series.points.length - 1]?.value ?? 0;
  const valueLabel = series.useAbsolute ? formatNum(lastValue, 4) : formatPct(lastValue);
  const rangeLabel = series.startDate && series.endDate
    ? `${formatDate(series.startDate)} → ${formatDate(series.endDate)}`
    : `${series.points.length} trade(s)`;

  const chart = el("div", { class: "equity-chart" });
  chart.innerHTML = `
    <svg class="equity-chart__svg" viewBox="0 0 ${SVG_WIDTH} ${SVG_HEIGHT}" preserveAspectRatio="none" aria-label="Latest equity curve">
      <line class="equity-chart__baseline" x1="${PADDING.left}" y1="${zeroY}" x2="${SVG_WIDTH - PADDING.right}" y2="${zeroY}"></line>
      <polyline class="equity-chart__line" points="${pointList}"></polyline>
      ${points.map((point, index) => `<circle class="equity-chart__point${index === points.length - 1 ? " is-last" : ""}" cx="${point.x}" cy="${point.y}" r="${index === points.length - 1 ? 4 : 2.25}"></circle>`).join("")}
    </svg>
    <div class="equity-chart__summary">
      <span><strong>Net:</strong> ${valueLabel}</span>
      <span><strong>Mode:</strong> ${series.useAbsolute ? "Absolute profit" : "Profit %"}</span>
      <span><strong>Range:</strong> ${rangeLabel}</span>
    </div>
  `;
  card.appendChild(chart);
  return card;
}

function renderPairBarsCard(rows) {
  const card = el("section", { class: "results-visual-card" });
  const header = el("div", { class: "results-visual-card__header" });
  header.innerHTML = `
    <div>
      <h3 class="results-visual-card__title">Per-Pair Profit</h3>
      <p class="results-visual-card__subtitle">Top pairs from the latest summary payload.</p>
    </div>
  `;
  card.appendChild(header);

  if (!rows.length) {
    card.appendChild(el("div", { class: "info-empty" }, "No per-pair rows are available for charting."));
    return card;
  }

  const visibleRows = rows.slice(0, MAX_PAIR_BARS);
  const maxAbs = Math.max(...visibleRows.map((row) => Math.abs(row.pct)), 1);
  const list = el("div", { class: "results-bar-list" });

  visibleRows.forEach((row) => {
    const item = el("div", { class: "results-bar-row" });
    const fillClass = row.pct >= 0 ? "results-bar-fill results-bar-fill--positive" : "results-bar-fill results-bar-fill--negative";
    const width = Math.max((Math.abs(row.pct) / maxAbs) * 100, 6);
    item.innerHTML = `
      <div class="results-bar-row__header">
        <span class="results-bar-row__label">${row.label}</span>
        <span class="results-bar-row__value">${formatPct(row.pct)}</span>
      </div>
      <div class="results-bar-track">
        <div class="${fillClass}" style="width:${width}%"></div>
      </div>
      <div class="results-bar-row__meta">${row.trades} trade(s)</div>
    `;
    list.appendChild(item);
  });

  card.appendChild(list);

  if (rows.length > MAX_PAIR_BARS) {
    card.appendChild(el("div", { class: "results-visual-card__hint" }, `Showing ${MAX_PAIR_BARS} of ${rows.length} pairs by profit.`));
  }

  return card;
}

function buildEquitySeries(trades) {
  if (!Array.isArray(trades) || !trades.length) return null;

  const orderedTrades = trades
    .map((trade, index) => ({ trade, index, ts: resolveTradeTimestamp(trade) }))
    .filter(({ trade }) => hasProfitValue(trade))
    .sort((left, right) => {
      const leftTs = left.ts ?? Number.MAX_SAFE_INTEGER;
      const rightTs = right.ts ?? Number.MAX_SAFE_INTEGER;
      return leftTs - rightTs || left.index - right.index;
    });

  if (!orderedTrades.length) return null;

  const useAbsolute = orderedTrades.every(({ trade }) => toNumber(trade.profit_abs ?? trade.profit_absolute) != null);
  let cumulative = 0;

  const points = orderedTrades.map(({ trade }, index) => {
    const delta = useAbsolute
      ? toNumber(trade.profit_abs ?? trade.profit_absolute) ?? 0
      : (toNumber(trade.profit_ratio ?? trade.profit_pct) ?? 0) * 100;
    cumulative += delta;
    return {
      label: trade.close_date ?? trade.open_date ?? `Trade ${index + 1}`,
      value: cumulative,
    };
  });

  return {
    useAbsolute,
    startDate: orderedTrades[0]?.trade?.open_date ?? orderedTrades[0]?.trade?.close_date ?? null,
    endDate: orderedTrades[orderedTrades.length - 1]?.trade?.close_date ?? orderedTrades[orderedTrades.length - 1]?.trade?.open_date ?? null,
    points,
  };
}

function normalizePairRows(rows) {
  if (!Array.isArray(rows)) return [];

  return rows
    .filter((row) => String(row?.key ?? row?.pair ?? "") !== "TOTAL")
    .map((row) => {
      const directPct = toNumber(row?.profit_total_pct);
      const ratioPct = toNumber(row?.profit_total);
      const pct = directPct ?? (ratioPct == null ? null : ratioPct * 100);
      return {
        label: row?.key ?? row?.pair ?? "—",
        pct,
        trades: Number(row?.trades ?? 0) || 0,
      };
    })
    .filter((row) => row.pct != null)
    .sort((left, right) => right.pct - left.pct);
}

function resolveTradeTimestamp(trade) {
  const value = trade?.close_date ?? trade?.open_date;
  if (!value) return null;
  const ts = new Date(value).getTime();
  return Number.isFinite(ts) ? ts : null;
}

function hasProfitValue(trade) {
  return toNumber(trade?.profit_abs ?? trade?.profit_absolute) != null
    || toNumber(trade?.profit_ratio ?? trade?.profit_pct) != null;
}

function toNumber(value) {
  if (value == null || value === "") return null;
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) ? number : null;
}
