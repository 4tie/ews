/**
 * result_renderer.js - Shared backtest result rendering.
 * Used by both backtesting and optimizer pages.
 */

import { formatPct, formatNum, el } from "../../../core/utils.js";

const EMPTY_VALUE = "\u2014";

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
        <th>Entry Reason</th>
        <th>Exit Reason</th>
      </tr>
    </thead>
  `;
  const tbody = el("tbody");
  trades.forEach((trade) => {
    const profitPct = parseFloat(trade.profit_ratio ?? trade.profit_pct ?? 0) * 100;
    const row = el("tr");
    row.innerHTML = `
      <td>${escapeHtml(displayText(trade.pair))}</td>
      <td class="${profitPct >= 0 ? "positive" : "negative"}">${formatPct(profitPct)}</td>
      <td class="mono">${formatNum(trade.profit_abs ?? trade.profit_absolute, 4)}</td>
      <td class="mono">${escapeHtml(displayText(trade.open_date))}</td>
      <td class="mono">${escapeHtml(displayText(trade.close_date))}</td>
      <td>${escapeHtml(formatTradeDurationValue(trade.trade_duration ?? trade.duration))}</td>
      <td>${escapeHtml(formatEntryReason(trade.enter_tag))}</td>
      <td>${escapeHtml(displayText(trade.exit_reason))}</td>
    `;
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  wrapper.innerHTML = "";
  wrapper.appendChild(table);
}

function renderSummarySection({ title, items, note, positive, negative }) {
  const tableConfig = !Array.isArray(items) ? items?.table : null;
  const sectionClasses = ["results-context"];
  if (tableConfig?.rows?.length) sectionClasses.push("results-context--table");
  if (positive) sectionClasses.push("results-context--positive");
  if (negative) sectionClasses.push("results-context--negative");

  const section = el("section", {
    class: sectionClasses.join(" "),
  });

  section.appendChild(el("div", { class: "results-context__title" }, title));

  const visibleItems = Array.isArray(items)
    ? items.filter((item) => item?.value && item.value !== EMPTY_VALUE)
    : [];
  if (visibleItems.length) {
    const meta = el("div", { class: "results-context__meta" });
    visibleItems.forEach((item) => {
      const pill = el("span");
      pill.innerHTML = `<strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.value)}</span>`;
      meta.appendChild(pill);
    });
    section.appendChild(meta);
  }

  if (tableConfig?.rows?.length) {
    const tableWrapper = el("div", { class: "table-wrapper results-context__table" });
    tableWrapper.appendChild(renderSummaryBreakdownTable(tableConfig));
    section.appendChild(tableWrapper);
  }

  if (note) {
    section.appendChild(el("div", { class: "results-context__note" }, note));
  }

  return section;
}

function renderSummaryBreakdownTable(tableConfig) {
  const table = el("table", { class: "data-table" });
  table.innerHTML = `
    <thead>
      <tr>
        <th>${escapeHtml(tableConfig.labelHeader)}</th>
        <th>Trades</th>
        <th>Win Rate</th>
        <th>Total Profit %</th>
        <th>Profit Abs</th>
        <th>Avg Duration</th>
      </tr>
    </thead>
  `;

  const tbody = el("tbody");
  tableConfig.rows.forEach((rowData) => {
    const row = el("tr");
    row.innerHTML = `
      <td>${escapeHtml(rowData.label)}</td>
      <td>${escapeHtml(rowData.trades)}</td>
      <td>${escapeHtml(rowData.winRate)}</td>
      <td class="${classifyValue(rowData.profitTotalPctValue)}">${rowData.profitTotalPct}</td>
      <td class="${classifyValue(rowData.profitAbsValue)}">${escapeHtml(rowData.profitAbs)}</td>
      <td>${escapeHtml(rowData.avgDuration)}</td>
    `;
    tbody.appendChild(row);
  });

  table.appendChild(tbody);
  return table;
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function toNumber(value) {
  if (value == null) return null;
  const n = typeof value === "number" ? value : parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

function isTotalKey(value) {
  return String(value ?? "") === "TOTAL";
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
  return rows.find((row) => isTotalKey(row?.key ?? row?.pair)) ?? null;
}

function toPercent(value, fallbackRatio) {
  const pct = toNumber(value);
  if (pct != null) return pct;
  const ratio = toNumber(fallbackRatio);
  return ratio == null ? null : ratio * 100;
}

function buildSummarySnapshot(summaryInput) {
  const { strategyName, block } = unwrapStrategyEntry(summaryInput);
  const s = block ?? {};
  const total = findTotalRow(s);
  const currency = s.stake_currency ?? "";
  const pairRows = Array.isArray(s.results_per_pair)
    ? s.results_per_pair.filter((row) => isObject(row) && !isTotalKey(row?.key ?? row?.pair))
    : [];

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

  const cagrRatio = toNumber(total?.cagr) ?? toNumber(s.cagr);
  const marketChangeRatio = toNumber(s.market_change);

  return {
    strategyName: s.strategy_name ?? strategyName,
    block: s,
    total,
    currency,
    profitTotalPct,
    absoluteProfit: toNumber(total?.profit_total_abs) ?? toNumber(s.profit_total_abs),
    profitMeanPct: toPercent(total?.profit_mean_pct ?? s.profit_mean_pct, total?.profit_mean ?? s.profit_mean),
    profitMedianPct: toPercent(total?.profit_median_pct ?? s.profit_median_pct, total?.profit_median ?? s.profit_median),
    winRatePct,
    totalTrades: toNumber(total?.trades) ?? toNumber(s.total_trades),
    avgDuration: total?.duration_avg ?? s.holding_avg ?? null,
    maxDrawdownPct,
    maxDrawdownAbs: toNumber(total?.max_drawdown_abs) ?? toNumber(s.max_drawdown_abs),
    sharpe: toNumber(total?.sharpe) ?? toNumber(s.sharpe) ?? toNumber(s.sharpe_ratio),
    sortino: toNumber(total?.sortino) ?? toNumber(s.sortino) ?? toNumber(s.sortino_ratio),
    calmar: toNumber(total?.calmar) ?? toNumber(s.calmar),
    cagrPct: cagrRatio == null ? null : cagrRatio * 100,
    profitFactor: toNumber(total?.profit_factor) ?? toNumber(s.profit_factor),
    sqn: toNumber(total?.sqn) ?? toNumber(s.sqn),
    expectancy: toNumber(total?.expectancy) ?? toNumber(s.expectancy),
    expectancyRatio: toNumber(total?.expectancy_ratio) ?? toNumber(s.expectancy_ratio),
    tradesPerDay: toNumber(total?.trades_per_day) ?? toNumber(s.trades_per_day),
    finalBalance: toNumber(s.final_balance),
    startingBalance: toNumber(s.starting_balance) ?? toNumber(s.dry_run_wallet),
    stakeAmount: s.stake_amount ?? null,
    avgStakeAmount: toNumber(s.avg_stake_amount),
    totalVolume: toNumber(s.total_volume),
    pairCount: Array.isArray(s.pairlist) ? s.pairlist.length : pairRows.length || null,
    bestPair: s.best_pair,
    worstPair: s.worst_pair,
    bestDayAbs: toNumber(s.backtest_best_day_abs),
    worstDayAbs: toNumber(s.backtest_worst_day_abs),
    winningDays: toNumber(s.winning_days),
    drawDays: toNumber(s.draw_days),
    losingDays: toNumber(s.losing_days),
    maxConsecutiveWins: toNumber(s.max_consecutive_wins),
    maxConsecutiveLosses: toNumber(s.max_consecutive_losses),
    tradeCountLong: toNumber(s.trade_count_long),
    tradeCountShort: toNumber(s.trade_count_short),
    winnerHoldingMin: s.winner_holding_min ?? null,
    winnerHoldingMax: s.winner_holding_max ?? null,
    winnerHoldingAvg: s.winner_holding_avg ?? null,
    loserHoldingMin: s.loser_holding_min ?? null,
    loserHoldingMax: s.loser_holding_max ?? null,
    loserHoldingAvg: s.loser_holding_avg ?? null,
    drawdownStart: s.drawdown_start ?? null,
    drawdownEnd: s.drawdown_end ?? null,
    drawdownDuration: s.drawdown_duration ?? null,
    timeframe: s.timeframe ?? null,
    timerange: s.timerange ?? null,
    backtestStart: s.backtest_start ?? null,
    backtestEnd: s.backtest_end ?? null,
    backtestDays: toNumber(s.backtest_days),
    tradingMode: s.trading_mode ?? null,
    marketChangePct: marketChangeRatio == null ? null : marketChangeRatio * 100,
    mixTagStats: s.mix_tag_stats,
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
        label: "Expectancy",
        value: formatRatio(snapshot.expectancy),
        positive: snapshot.expectancy > 0,
        negative: snapshot.expectancy < 0,
      },
      {
        label: "Avg Trade %",
        value: formatPct(snapshot.profitMeanPct),
        positive: snapshot.profitMeanPct > 0,
        negative: snapshot.profitMeanPct < 0,
      },
      {
        label: "Trades / Day",
        value: formatRate(snapshot.tradesPerDay),
      },
      {
        label: "CAGR",
        value: formatPct(snapshot.cagrPct),
        positive: snapshot.cagrPct > 0,
        negative: snapshot.cagrPct < 0,
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
  const pairCountLabel =
    snapshot.pairCount == null
      ? null
      : `${formatCount(snapshot.pairCount)} ${snapshot.pairCount === 1 ? "pair" : "pairs"}`;

  return compactSections([
    {
      title: "Run Context",
      positive: tonePositive,
      negative: toneNegative,
      items: [
        { label: "Strategy", value: displayText(snapshot.strategyName) },
        { label: "Timeframe", value: displayText(snapshot.timeframe) },
        { label: "Requested Range", value: formatTimerange(snapshot.timerange) },
        { label: "Backtest Window", value: formatDateTimeRange(snapshot.backtestStart, snapshot.backtestEnd) },
        { label: "Backtest Days", value: formatCount(snapshot.backtestDays) },
        { label: "Mode", value: displayText(snapshot.tradingMode) },
      ],
      note: buildNote([
        snapshot.strategyName ? `Latest persisted summary for ${displayText(snapshot.strategyName)}` : null,
        pairCountLabel ? `Universe ${pairCountLabel}` : null,
      ]),
    },
    {
      title: "Capital & Risk",
      items: [
        { label: "Starting Balance", value: formatMoney(snapshot.startingBalance, snapshot.currency) },
        { label: "Final Balance", value: formatMoney(snapshot.finalBalance, snapshot.currency) },
        { label: "Absolute Profit", value: formatSignedMoney(snapshot.absoluteProfit, snapshot.currency) },
        { label: "Max Drawdown", value: formatPct(snapshot.maxDrawdownPct) },
        { label: "Drawdown Abs", value: formatMoney(snapshot.maxDrawdownAbs, snapshot.currency) },
        { label: "Drawdown Duration", value: displayText(snapshot.drawdownDuration) },
        { label: "CAGR", value: formatPct(snapshot.cagrPct) },
      ],
      note: buildNote([
        snapshot.marketChangePct != null ? `Market change ${formatPct(snapshot.marketChangePct)}` : null,
        snapshot.drawdownStart || snapshot.drawdownEnd
          ? `Drawdown window ${formatDateTimeRange(snapshot.drawdownStart, snapshot.drawdownEnd)}`
          : null,
      ]),
    },
    {
      title: "Execution Quality",
      items: [
        { label: "Profit Factor", value: formatRatio(snapshot.profitFactor) },
        { label: "Expectancy", value: formatRatio(snapshot.expectancy) },
        { label: "Expectancy Ratio", value: formatRatio(snapshot.expectancyRatio) },
        { label: "Sharpe", value: formatRatio(snapshot.sharpe) },
        { label: "Sortino", value: formatRatio(snapshot.sortino) },
        { label: "Calmar", value: formatRatio(snapshot.calmar) },
        { label: "SQN", value: formatRatio(snapshot.sqn) },
        { label: "Avg Trade", value: formatPct(snapshot.profitMeanPct) },
        { label: "Median Trade", value: formatPct(snapshot.profitMedianPct) },
        { label: "Trades / Day", value: formatRate(snapshot.tradesPerDay) },
      ],
      note: buildNote([
        snapshot.bestDayAbs != null ? `Best day ${formatSignedMoney(snapshot.bestDayAbs, snapshot.currency)}` : null,
        snapshot.worstDayAbs != null ? `Worst day ${formatSignedMoney(snapshot.worstDayAbs, snapshot.currency)}` : null,
      ]),
    },
    {
      title: "Trade Distribution",
      items: [
        { label: "Best Pair", value: formatPairDisplay(snapshot.bestPair) },
        { label: "Worst Pair", value: formatPairDisplay(snapshot.worstPair) },
        { label: "Pairs", value: formatCount(snapshot.pairCount) },
        { label: "Long Trades", value: formatCount(snapshot.tradeCountLong) },
        { label: "Short Trades", value: formatCount(snapshot.tradeCountShort) },
        { label: "Max Win Streak", value: formatCount(snapshot.maxConsecutiveWins) },
        { label: "Max Loss Streak", value: formatCount(snapshot.maxConsecutiveLosses) },
        { label: "Stake Size", value: formatStakeAmount(snapshot.stakeAmount, snapshot.currency) },
        { label: "Avg Stake", value: formatMoney(snapshot.avgStakeAmount, snapshot.currency) },
      ],
      note: buildNote([
        snapshot.winRatePct != null && snapshot.totalTrades != null
          ? `Win rate ${formatPct(snapshot.winRatePct, 1)} across ${formatCount(snapshot.totalTrades)} trades`
          : null,
        snapshot.totalVolume != null ? `Volume ${formatMoney(snapshot.totalVolume, snapshot.currency)}` : null,
      ]),
    },
    {
      title: "Day Outcomes",
      items: [
        { label: "Winning Days", value: formatCount(snapshot.winningDays) },
        { label: "Flat Days", value: formatCount(snapshot.drawDays) },
        { label: "Losing Days", value: formatCount(snapshot.losingDays) },
        { label: "Best Day", value: formatSignedMoney(snapshot.bestDayAbs, snapshot.currency) },
        { label: "Worst Day", value: formatSignedMoney(snapshot.worstDayAbs, snapshot.currency) },
        { label: "Trades / Day", value: formatRate(snapshot.tradesPerDay) },
      ],
      note: buildNote([
        snapshot.backtestStart || snapshot.backtestEnd
          ? `Backtest window ${formatDateTimeRange(snapshot.backtestStart, snapshot.backtestEnd)}`
          : null,
        snapshot.backtestDays != null ? `${formatCount(snapshot.backtestDays)} calendar days covered` : null,
      ]),
    },
    {
      title: "Holding Profile",
      items: [
        { label: "Avg Hold", value: displayText(snapshot.avgDuration) },
        { label: "Winner Avg", value: displayText(snapshot.winnerHoldingAvg) },
        { label: "Winner Range", value: formatRangeText(snapshot.winnerHoldingMin, snapshot.winnerHoldingMax) },
        { label: "Loser Avg", value: displayText(snapshot.loserHoldingAvg) },
        { label: "Loser Range", value: formatRangeText(snapshot.loserHoldingMin, snapshot.loserHoldingMax) },
      ],
      note: buildNote([
        snapshot.drawdownDuration ? `Drawdown duration ${displayText(snapshot.drawdownDuration)}` : null,
        snapshot.absoluteProfit != null ? `Net result ${formatSignedMoney(snapshot.absoluteProfit, snapshot.currency)}` : null,
      ]),
    },
    buildBreakdownSection({
      title: "Entry Tags",
      labelHeader: "Tag",
      rows: snapshot.block?.results_per_enter_tag,
      currency: snapshot.currency,
      emptyKeyLabel: "Default",
    }),
    buildBreakdownSection({
      title: "Exit Reasons",
      labelHeader: "Reason",
      rows: snapshot.block?.exit_reason_summary,
      currency: snapshot.currency,
      emptyKeyLabel: "Default",
    }),
    buildBreakdownSection({
      title: "Entry / Exit Mix",
      labelHeader: "Path",
      rows: snapshot.mixTagStats,
      currency: snapshot.currency,
      emptyKeyLabel: "Default",
    }),
  ]);
}

function buildBreakdownSection({ title, labelHeader, rows, currency, emptyKeyLabel = EMPTY_VALUE }) {
  const normalizedRows = normalizeBreakdownRows(rows, { currency, emptyKeyLabel });
  if (!normalizedRows.length) return null;

  return {
    title,
    items: {
      table: {
        labelHeader,
        rows: normalizedRows,
      },
    },
  };
}

function normalizeBreakdownRows(rows, { currency = "", emptyKeyLabel = EMPTY_VALUE } = {}) {
  if (!Array.isArray(rows)) return [];

  return rows
    .filter((row) => isObject(row) && !isTotalKey(row?.key ?? row?.pair))
    .map((row) => {
      const winRateRatio = toNumber(row.winrate);
      const wins = toNumber(row.wins);
      const trades = toNumber(row.trades);
      const winRatePct =
        winRateRatio != null
          ? winRateRatio * 100
          : wins != null && trades != null && trades !== 0
            ? (wins / trades) * 100
            : null;

      let profitTotalPct = toNumber(row.profit_total_pct);
      if (profitTotalPct == null) {
        const profitRatio = toNumber(row.profit_total);
        profitTotalPct = profitRatio == null ? null : profitRatio * 100;
      }

      const profitAbs = toNumber(row.profit_total_abs);

      return {
        label: formatBreakdownKey(row.key ?? row.pair, emptyKeyLabel),
        trades: formatCount(row.trades),
        winRate: formatPct(winRatePct, 1),
        profitTotalPct: formatPct(profitTotalPct),
        profitTotalPctValue: profitTotalPct,
        profitAbs: formatSignedMoney(profitAbs, currency),
        profitAbsValue: profitAbs,
        avgDuration: displayText(row.duration_avg),
      };
    });
}

function compactMetrics(metrics) {
  return metrics.filter((metric) => metric?.value && metric.value !== EMPTY_VALUE);
}

function compactSections(sections) {
  return sections.filter((section) => {
    if (!section) return false;
    if (Array.isArray(section.items) && section.items.some((item) => item?.value && item.value !== EMPTY_VALUE)) {
      return true;
    }
    return Boolean(section.items?.table?.rows?.length);
  });
}

function displayText(value) {
  if (value == null || value === "") return EMPTY_VALUE;
  return String(value);
}

function formatEntryReason(value) {
  if (value === "") return "Default";
  return displayText(value);
}

function formatBreakdownKey(value, emptyKeyLabel = EMPTY_VALUE) {
  if (Array.isArray(value)) {
    return value.map((part) => formatBreakdownKey(part, emptyKeyLabel)).join(" -> ");
  }
  if (value === "") return emptyKeyLabel;
  return displayText(value);
}

function formatCount(value) {
  const n = toNumber(value);
  return n == null ? EMPTY_VALUE : `${Math.round(n)}`;
}

function formatRatio(value, decimals = 3) {
  return value == null ? EMPTY_VALUE : formatNum(value, decimals);
}

function formatRate(value, decimals = 2) {
  const n = toNumber(value);
  return n == null ? EMPTY_VALUE : formatNum(n, decimals);
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

function formatStakeAmount(value, currency = "") {
  const numeric = toNumber(value);
  if (numeric != null) return formatMoney(numeric, currency);
  return displayText(value);
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

function formatDateTimeRange(start, end) {
  const startText = formatDateTimeValue(start);
  const endText = formatDateTimeValue(end);
  if (startText !== EMPTY_VALUE && endText !== EMPTY_VALUE) {
    return `${startText} to ${endText}`;
  }
  return startText !== EMPTY_VALUE ? startText : endText;
}

function formatDateTimeValue(value) {
  return displayText(value);
}

function formatRangeText(min, max) {
  const minText = displayText(min);
  const maxText = displayText(max);
  if (minText !== EMPTY_VALUE && maxText !== EMPTY_VALUE) {
    return `${minText} to ${maxText}`;
  }
  return minText !== EMPTY_VALUE ? minText : maxText;
}

function formatTradeDurationValue(value) {
  if (value == null || value === "") return EMPTY_VALUE;
  if (typeof value === "string" && /[:a-zA-Z]/.test(value)) {
    return displayText(value);
  }

  const totalMinutes = toNumber(value);
  if (totalMinutes == null) return displayText(value);

  const roundedMinutes = Math.max(0, Math.round(totalMinutes));
  const days = Math.floor(roundedMinutes / 1440);
  const hours = Math.floor((roundedMinutes % 1440) / 60);
  const minutes = roundedMinutes % 60;
  const hhmm = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  return days > 0 ? `${days}d ${hhmm}` : hhmm;
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
  const pct = toNumber(pairStat.profit_total_pct);
  if (pct != null) return pct;
  const ratio = toNumber(pairStat.profit_total);
  return ratio == null ? null : ratio * 100;
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

function buildNote(parts) {
  const filtered = parts.filter(Boolean);
  return filtered.length ? `${filtered.join(" | ")}.` : null;
}

function classifyValue(value) {
  const n = toNumber(value);
  if (n == null || n === 0) return "";
  return n > 0 ? "positive" : "negative";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
