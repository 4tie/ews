/**
 * result_renderer.js â€” Shared backtest result rendering.
 * Used by both backtesting and optimizer pages.
 */

import { formatPct, formatNum, el } from "../../../core/utils.js";

/**
 * Render a grid of summary stat cards into a container element.
 * @param {HTMLElement} container
 * @param {Object} summary â€” raw strategy summary from the API
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
      <td>${trade.pair ?? "â€”"}</td>
      <td class="${profitPct >= 0 ? "positive" : "negative"}">${formatPct(profitPct)}</td>
      <td class="mono">${formatNum(trade.profit_abs ?? trade.profit_absolute, 4)}</td>
      <td class="mono">${trade.open_date ?? "â€”"}</td>
      <td class="mono">${trade.close_date ?? "â€”"}</td>
      <td>${trade.trade_duration ?? trade.duration ?? "â€”"}</td>
    `;
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  wrapper.innerHTML = "";
  wrapper.appendChild(table);
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function toNumber(value) {
  if (value == null) return null;
  const n = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

function unwrapStrategyBlock(summaryInput) {
  if (!isObject(summaryInput)) return null;

  if (
    Array.isArray(summaryInput.results_per_pair) ||
    summaryInput.total_trades != null ||
    summaryInput.wins != null
  ) {
    return summaryInput;
  }

  for (const [key, value] of Object.entries(summaryInput)) {
    if (key === "strategy_comparison") continue;
    if (isObject(value)) return value;
  }

  return null;
}

function findTotalRow(strategyBlock) {
  const rows = strategyBlock?.results_per_pair;
  if (!Array.isArray(rows)) return null;
  return rows.find(r => String(r?.key ?? r?.pair ?? "") === "TOTAL") ?? null;
}

function extractMetrics(summaryInput) {
  const s = unwrapStrategyBlock(summaryInput) ?? {};
  const total = findTotalRow(s);

  let profitTotalPct = toNumber(total?.profit_total_pct) ?? toNumber(s.profit_total_pct);
  if (profitTotalPct == null) {
    const ratio = toNumber(total?.profit_total) ?? toNumber(s.profit_total);
    profitTotalPct = ratio == null ? null : ratio * 100;
  }

  let winRatePct = null;
  const winrateRatio = toNumber(total?.winrate);
  if (winrateRatio != null) {
    winRatePct = winrateRatio * 100;
  } else {
    const wins = toNumber(total?.wins) ?? toNumber(s.wins);
    const trades = toNumber(total?.trades) ?? toNumber(s.total_trades);
    if (wins != null && trades != null && trades !== 0) {
      winRatePct = (wins / trades) * 100;
    }
  }

  const totalTrades = total?.trades ?? s.total_trades ?? "â€”";
  const avgDuration = total?.duration_avg ?? s.holding_avg ?? "â€”";

  let maxDrawdownPct = null;
  const ddAccount = toNumber(total?.max_drawdown_account) ?? toNumber(s.max_drawdown_account);
  if (ddAccount != null) {
    maxDrawdownPct = -Math.abs(ddAccount * 100);
  } else {
    const ddPct = toNumber(s.max_drawdown_pct);
    if (ddPct != null) {
      maxDrawdownPct = -Math.abs(ddPct);
    } else {
      const ddRatio = toNumber(s.max_drawdown);
      maxDrawdownPct = ddRatio == null ? null : -Math.abs(ddRatio * 100);
    }
  }

  const sharpe = toNumber(total?.sharpe) ?? toNumber(s.sharpe) ?? toNumber(s.sharpe_ratio);
  const sortino = toNumber(total?.sortino) ?? toNumber(s.sortino) ?? toNumber(s.sortino_ratio);
  const calmar = toNumber(total?.calmar) ?? toNumber(s.calmar);

  return [
    {
      label: "Total Profit %",
      value: formatPct(profitTotalPct),
      positive: profitTotalPct > 0,
      negative: profitTotalPct < 0,
    },
    { label: "Win Rate",       value: formatPct(winRatePct, 1) },
    { label: "Total Trades",   value: totalTrades },
    { label: "Avg Duration",   value: avgDuration },
    { label: "Max Drawdown %", value: formatPct(maxDrawdownPct), negative: maxDrawdownPct != null },
    { label: "Sharpe",         value: formatNum(sharpe, 3) },
    { label: "Sortino",        value: formatNum(sortino, 3) },
    { label: "Calmar",         value: formatNum(calmar, 3) },
  ];
}
