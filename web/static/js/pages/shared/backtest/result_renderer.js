/**
 * result_renderer.js - Shared backtest result rendering.
 * Used by both backtesting and optimizer pages.
 */

import { formatPct, formatNum, el } from "../../../core/utils.js";

const EMPTY_VALUE = "—";

/**
 * Render a grid of summary stat cards into a container element.
 * @param {HTMLElement} container
 * @param {Object} summary - raw strategy summary from the API
 * @param {Object} options
 */
export function renderSummaryCards(container, summary, options = {}) {
  if (!container) return;
  container.innerHTML = "";

  if (!summary) {
    container.innerHTML = '<div class="info-empty">No summary data available.</div>';
    return;
  }

  const expanded = Boolean(options.expanded);
  const metrics = extractMetrics(summary, { expanded });
  const grid = el("div", { class: "summary-cards__grid" });

  metrics.forEach(({ label, value, subtext, positive, negative }) => {
    const card = el("div", {
      class: `card ${positive ? "card--positive" : negative ? "card--negative" : ""}`.trim(),
    });
    card.innerHTML = `
      <div class="card__label">${label}</div>
      <div class="card__value">${value}</div>
      ${subtext ? `<div class="card__subtext">${subtext}</div>` : ""}
    `;
    grid.appendChild(card);
  });

  container.appendChild(grid);

  if (!expanded) return;

  const sections = extractSummarySections(summary);
  if (!sections.length) return;

  const details = el("div", { class: "summary-details" });
  sections.forEach((section) => details.appendChild(renderSummarySection(section)));
  container.appendChild(details);
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
  trades.forEach((trade) => {
    const profitPct = parseFloat(trade.profit_ratio ?? trade.profit_pct ?? 0) * 100;
    const row = el("tr");
    row.innerHTML = `
      <td>${trade.pair ?? EMPTY_VALUE}</td>
      <td class="${profitPct >= 0 ? "positive" : "negative"}">${formatPct(profitPct)}</td>
      <td class="mono">${formatNum(trade.profit_abs ?? trade.profit_absolute, 4)}</td>
      <td class="mono">${trade.open_date ?? EMPTY_VALUE}</td>
      <td class="mono">${trade.close_date ?? EMPTY_VALUE}</td>
      <td>${trade.trade_duration ?? trade.duration ?? EMPTY_VALUE}</td>
    `;
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  wrapper.innerHTML = "";
  wrapper.appendChild(table);
}

function renderSummarySection({ title, items, note, positive, negative }) {
  const section = el("section", {
    class: `results-context ${positive ? "results-context--positive" : negative ? "results-context--negative" : ""}`.trim(),
  });

  const metaMarkup = items
    .filter((item) => item?.value && item.value !== EMPTY_VALUE)
    .map((item) => `<span><strong>${item.label}:</strong> ${item.value}</span>`)
    .join("");

  section.innerHTML = `
    <div class="results-context__title">${title}</div>
    <div class="results-context__meta">${metaMarkup}</div>
    ${note ? `<div class="results-context__note">${note}</div>` : ""}
  `;

  return section;
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function toNumber(value) {
  if (value == null) return null;
  const n = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

function unwrapStrategyEntry(summaryInput) {
  if (!isObject(summaryInput)) return { strategyName: null, block: null };

  if (
    Array.isArray(summaryInput.results_per_pair) ||
    summaryInput.total_trades != null ||
    summaryInput.wins != null
  ) {
    return {
      strategyName: summaryInput.strategy_name ?? null,
      block: summaryInput,
    };
  }

  for (const [key, value] of Object.entries(summaryInput)) {
    if (key === "strategy_comparison") continue;
    if (isObject(value)) {
      return {
        strategyName: value.strategy_name ?? key,
        block: value,
      };
    }
  }

  return { strategyName: null, block: null };
}

function unwrapStrategyBlock(summaryInput) {
  return unwrapStrategyEntry(summaryInput).block;
}

function findTotalRow(strategyBlock) {
  const rows = strategyBlock?.results_per_pair;
  if (!Array.isArray(rows)) return null;
  return rows.find((row) => String(row?.key ?? row?.pair ?? "") === "TOTAL") ?? null;
}

function buildSummarySnapshot(summaryInput) {
  const { strategyName, block } = unwrapStrategyEntry(summaryInput);
  const s = block ?? {};
  const total = findTotalRow(s);
  const currency = s.stake_currency ?? "";

  let profitTotalPct = toNumber(total?.profit_total_pct) ?? toNumber(s.profit_total_pct);
  if (profitTotalPct == null) {
    const ratio = toNumber(total?.profit_total) ?? toNumber(s.profit_total);
    profitTotalPct = ratio == null ? null : ratio * 100;
  }

  let winRatePct = null;
  const winrateRatio = toNumber(total?.winrate) ?? toNumber(s.winrate);
  if (winrateRatio != null) {
    winRatePct = winrateRatio * 100;
  } else {
    const wins = toNumber(total?.wins) ?? toNumber(s.wins);
    const trades = toNumber(total?.trades) ?? toNumber(s.total_trades);
    if (wins != null && trades != null && trades !== 0) {
      winRatePct = (wins / trades) * 100;
    }
  }

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

  const marketChangeRatio = toNumber(s.market_change);

  return {
    strategyName: s.strategy_name ?? strategyName,
    block: s,
    total,
    currency,
    profitTotalPct,
    absoluteProfit: toNumber(total?.profit_total_abs) ?? toNumber(s.profit_total_abs),
    winRatePct,
    totalTrades: toNumber(total?.trades) ?? toNumber(s.total_trades),
    avgDuration: total?.duration_avg ?? s.holding_avg ?? null,
    maxDrawdownPct,
    maxDrawdownAbs: toNumber(total?.max_drawdown_abs) ?? toNumber(s.max_drawdown_abs),
    sharpe: toNumber(total?.sharpe) ?? toNumber(s.sharpe) ?? toNumber(s.sharpe_ratio),
    sortino: toNumber(total?.sortino) ?? toNumber(s.sortino) ?? toNumber(s.sortino_ratio),
    calmar: toNumber(total?.calmar) ?? toNumber(s.calmar),
    profitFactor: toNumber(total?.profit_factor) ?? toNumber(s.profit_factor),
    sqn: toNumber(total?.sqn) ?? toNumber(s.sqn),
    expectancyRatio: toNumber(total?.expectancy_ratio) ?? toNumber(s.expectancy_ratio),
    finalBalance: toNumber(s.final_balance),
    startingBalance: toNumber(s.starting_balance) ?? toNumber(s.dry_run_wallet),
    avgStakeAmount: toNumber(s.avg_stake_amount),
    totalVolume: toNumber(s.total_volume),
    bestPair: s.best_pair,
    worstPair: s.worst_pair,
    bestDayAbs: toNumber(s.backtest_best_day_abs),
    worstDayAbs: toNumber(s.backtest_worst_day_abs),
    maxConsecutiveWins: toNumber(s.max_consecutive_wins),
    maxConsecutiveLosses: toNumber(s.max_consecutive_losses),
    drawdownDuration: s.drawdown_duration ?? null,
    timeframe: s.timeframe ?? null,
    timerange: s.timerange ?? null,
    tradingMode: s.trading_mode ?? null,
    marketChangePct: marketChangeRatio == null ? null : marketChangeRatio * 100,
  };
}

function extractMetrics(summaryInput, { expanded = false } = {}) {
  const snapshot = buildSummarySnapshot(summaryInput);
  const metrics = [
    {
      label: "Total Profit %",
      value: formatPct(snapshot.profitTotalPct),
      positive: snapshot.profitTotalPct > 0,
      negative: snapshot.profitTotalPct < 0,
    },
    { label: "Win Rate", value: formatPct(snapshot.winRatePct, 1) },
    { label: "Total Trades", value: formatCount(snapshot.totalTrades) },
    { label: "Avg Duration", value: displayText(snapshot.avgDuration) },
    {
      label: "Max Drawdown %",
      value: formatPct(snapshot.maxDrawdownPct),
      subtext: snapshot.maxDrawdownAbs == null ? null : `${formatMoney(snapshot.maxDrawdownAbs, snapshot.currency)} abs`,
      negative: snapshot.maxDrawdownPct != null,
    },
    { label: "Sharpe", value: formatRatio(snapshot.sharpe) },
    { label: "Sortino", value: formatRatio(snapshot.sortino) },
    { label: "Calmar", value: formatRatio(snapshot.calmar) },
  ];

  if (!expanded) {
    return metrics;
  }

  return metrics.concat(
    compactMetrics([
      {
        label: "Absolute Profit",
        value: formatSignedMoney(snapshot.absoluteProfit, snapshot.currency),
        positive: snapshot.absoluteProfit > 0,
        negative: snapshot.absoluteProfit < 0,
      },
      {
        label: "Final Balance",
        value: formatMoney(snapshot.finalBalance, snapshot.currency),
        subtext: snapshot.startingBalance == null ? null : `Start ${formatMoney(snapshot.startingBalance, snapshot.currency)}`,
        positive: snapshot.finalBalance != null && snapshot.startingBalance != null && snapshot.finalBalance > snapshot.startingBalance,
        negative: snapshot.finalBalance != null && snapshot.startingBalance != null && snapshot.finalBalance < snapshot.startingBalance,
      },
      {
        label: "Profit Factor",
        value: formatRatio(snapshot.profitFactor),
      },
      {
        label: "SQN",
        value: formatRatio(snapshot.sqn),
      },
      {
        label: "Best Pair",
        value: formatPairName(snapshot.bestPair),
        subtext: formatPairSubtext(snapshot.bestPair),
        positive: pairProfitPct(snapshot.bestPair) > 0,
        negative: pairProfitPct(snapshot.bestPair) < 0,
      },
      {
        label: "Worst Pair",
        value: formatPairName(snapshot.worstPair),
        subtext: formatPairSubtext(snapshot.worstPair),
        positive: pairProfitPct(snapshot.worstPair) > 0,
        negative: pairProfitPct(snapshot.worstPair) < 0,
      },
      {
        label: "Best Day",
        value: formatSignedMoney(snapshot.bestDayAbs, snapshot.currency),
        positive: snapshot.bestDayAbs > 0,
        negative: snapshot.bestDayAbs < 0,
      },
      {
        label: "Worst Day",
        value: formatSignedMoney(snapshot.worstDayAbs, snapshot.currency),
        positive: snapshot.worstDayAbs > 0,
        negative: snapshot.worstDayAbs < 0,
      },
      {
        label: "Avg Stake",
        value: formatMoney(snapshot.avgStakeAmount, snapshot.currency),
      },
      {
        label: "Market Change",
        value: formatPct(snapshot.marketChangePct),
        positive: snapshot.marketChangePct > 0,
        negative: snapshot.marketChangePct < 0,
      },
    ])
  );
}

function extractSummarySections(summaryInput) {
  const snapshot = buildSummarySnapshot(summaryInput);
  const tonePositive = snapshot.profitTotalPct > 0;
  const toneNegative = snapshot.profitTotalPct < 0;

  return compactSections([
    {
      title: "Run Context",
      positive: tonePositive,
      negative: toneNegative,
      items: [
        { label: "Strategy", value: displayText(snapshot.strategyName) },
        { label: "Timeframe", value: displayText(snapshot.timeframe) },
        { label: "Range", value: formatTimerange(snapshot.timerange) },
        { label: "Mode", value: displayText(snapshot.tradingMode) },
      ],
      note: `Latest persisted summary for ${displayText(snapshot.strategyName)}.`,
    },
    {
      title: "Capital & Risk",
      items: [
        { label: "Starting Balance", value: formatMoney(snapshot.startingBalance, snapshot.currency) },
        { label: "Final Balance", value: formatMoney(snapshot.finalBalance, snapshot.currency) },
        { label: "Max Drawdown", value: formatPct(snapshot.maxDrawdownPct) },
        { label: "Duration", value: displayText(snapshot.drawdownDuration) },
      ],
      note: `Market change ${formatPct(snapshot.marketChangePct)} | Absolute drawdown ${formatMoney(snapshot.maxDrawdownAbs, snapshot.currency)}.`,
    },
    {
      title: "Execution Quality",
      items: [
        { label: "Profit Factor", value: formatRatio(snapshot.profitFactor) },
        { label: "Expectancy Ratio", value: formatRatio(snapshot.expectancyRatio) },
        { label: "SQN", value: formatRatio(snapshot.sqn) },
        { label: "Avg Stake", value: formatMoney(snapshot.avgStakeAmount, snapshot.currency) },
      ],
      note: `Best day ${formatSignedMoney(snapshot.bestDayAbs, snapshot.currency)} | Worst day ${formatSignedMoney(snapshot.worstDayAbs, snapshot.currency)}.`,
    },
    {
      title: "Trade Distribution",
      items: [
        { label: "Best Pair", value: formatPairDisplay(snapshot.bestPair) },
        { label: "Worst Pair", value: formatPairDisplay(snapshot.worstPair) },
        { label: "Max Win Streak", value: formatCount(snapshot.maxConsecutiveWins) },
        { label: "Max Loss Streak", value: formatCount(snapshot.maxConsecutiveLosses) },
      ],
      note: `Win rate ${formatPct(snapshot.winRatePct, 1)} across ${formatCount(snapshot.totalTrades)} trades | Volume ${formatMoney(snapshot.totalVolume, snapshot.currency)}.`,
    },
  ]);
}

function compactMetrics(metrics) {
  return metrics.filter((metric) => metric?.value && metric.value !== EMPTY_VALUE);
}

function compactSections(sections) {
  return sections.filter((section) => section.items?.some((item) => item?.value && item.value !== EMPTY_VALUE));
}

function displayText(value) {
  if (value == null || value === "") return EMPTY_VALUE;
  return String(value);
}

function formatCount(value) {
  const n = toNumber(value);
  return n == null ? EMPTY_VALUE : `${Math.round(n)}`;
}

function formatRatio(value, decimals = 3) {
  return value == null ? EMPTY_VALUE : formatNum(value, decimals);
}

function formatMoney(value, currency = "", decimals = 2) {
  const n = toNumber(value);
  if (n == null) return EMPTY_VALUE;
  return `${formatNum(n, decimals)}${currency ? ` ${currency}` : ""}`;
}

function formatSignedMoney(value, currency = "", decimals = 2) {
  const n = toNumber(value);
  if (n == null) return EMPTY_VALUE;
  const sign = n > 0 ? "+" : "";
  return `${sign}${formatNum(n, decimals)}${currency ? ` ${currency}` : ""}`;
}

function formatTimerange(timerange) {
  if (!timerange) return EMPTY_VALUE;
  const [start, end] = String(timerange).split("-");
  if (start?.length === 8 && end?.length === 8) {
    return `${formatDateToken(start)} to ${formatDateToken(end)}`;
  }
  return String(timerange);
}

function formatDateToken(value) {
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}`;
}

function formatPairName(pairStat) {
  if (!pairStat) return EMPTY_VALUE;
  if (isObject(pairStat)) {
    return displayText(pairStat.key ?? pairStat.pair);
  }
  return displayText(pairStat);
}

function pairProfitPct(pairStat) {
  if (!isObject(pairStat)) return null;
  return toNumber(pairStat.profit_total_pct);
}

function formatPairSubtext(pairStat) {
  if (!isObject(pairStat)) return null;
  const parts = [];
  const pct = pairProfitPct(pairStat);
  const trades = toNumber(pairStat.trades);
  if (pct != null) parts.push(formatPct(pct));
  if (trades != null) parts.push(`${Math.round(trades)} trades`);
  return parts.join(" | ") || null;
}

function formatPairDisplay(pairStat) {
  const name = formatPairName(pairStat);
  const subtext = formatPairSubtext(pairStat);
  if (!subtext || name === EMPTY_VALUE) return name;
  return `${name} (${subtext})`;
}
