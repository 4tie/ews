/**
 * result_renderer.js — Shared backtest result rendering.
 * Used by both backtesting and optimizer pages.
 */

import { formatPct, formatNum, el } from "../../../core/utils.js";

/**
 * Render a grid of summary stat cards into a container element.
 * @param {HTMLElement} container
 * @param {Object} summary — raw strategy summary from the API
 */
export function renderSummaryCards(container, summary) {
  if (!container) return;
  container.innerHTML = "";

  if (!summary) {
    container.innerHTML = '<div class="info-empty">No summary data available.</div>';
    return;
  }

  const metrics = extractMetrics(summary);
  metrics.forEach(({ label, value, positive, negative }) => {
    const card = el("div", { class: `card ${positive ? "card--positive" : negative ? "card--negative" : ""}` });
    card.innerHTML = `
      <div class="card__label">${label}</div>
      <div class="card__value">${value}</div>
    `;
    container.appendChild(card);
  });
}

/**
 * Render trades into a data-table inside a wrapper element.
 * @param {HTMLElement} wrapper
 * @param {Array} trades
 */
export function renderTradesTable(wrapper, trades) {
  if (!wrapper) return;
  if (!trades || !trades.length) {
    wrapper.innerHTML = '<div class="info-empty">No trades to display.</div>';
    return;
  }

  const table = el("table", { class: "data-table" });
  table.innerHTML = `
    <thead>
      <tr>
        <th>Pair</th>
        <th>Profit %</th>
        <th>Profit Abs</th>
        <th>Open Date</th>
        <th>Close Date</th>
        <th>Duration</th>
      </tr>
    </thead>
  `;
  const tbody = el("tbody");
  trades.forEach(trade => {
    const profitPct = parseFloat(trade.profit_ratio ?? trade.profit_pct ?? 0) * 100;
    const row = el("tr");
    row.innerHTML = `
      <td>${trade.pair ?? "—"}</td>
      <td class="${profitPct >= 0 ? "positive" : "negative"}">${formatPct(profitPct)}</td>
      <td class="mono">${formatNum(trade.profit_abs ?? trade.profit_absolute, 4)}</td>
      <td class="mono">${trade.open_date ?? "—"}</td>
      <td class="mono">${trade.close_date ?? "—"}</td>
      <td>${trade.trade_duration ?? trade.duration ?? "—"}</td>
    `;
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  wrapper.innerHTML = "";
  wrapper.appendChild(table);
}

function extractMetrics(summary) {
  // Freqtrade summary may nest under strategy name key
  let s = summary;
  const keys = Object.keys(summary || {});
  if (keys.length === 1 && typeof summary[keys[0]] === "object") {
    s = summary[keys[0]];
  }
  return [
    { label: "Total Profit %",   value: formatPct((s.profit_total_pct ?? s.profit_factor ?? 0) * 100) },
    { label: "Win Rate",         value: formatPct((s.wins / (s.total_trades || 1)) * 100, 1) },
    { label: "Total Trades",     value: s.total_trades ?? "—" },
    { label: "Avg Duration",     value: s.holding_avg ?? "—" },
    { label: "Max Drawdown %",   value: formatPct(-(s.max_drawdown_pct ?? s.max_drawdown ?? 0) * 100), negative: true },
    { label: "Sharpe",           value: formatNum(s.sharpe_ratio, 3) },
    { label: "Sortino",          value: formatNum(s.sortino, 3) },
    { label: "Calmar",           value: formatNum(s.calmar, 3) },
  ];
}
