/**
 * history-panel.js — Shows the latest loaded result entry from the unified flow.
 */

import { on, EVENTS } from "../../../core/events.js";
import { getState } from "../../../core/state.js";
import { el, formatDate, formatPct } from "../../../core/utils.js";
import { getLatestResultsPayload } from "../results/results-controller.js";

const historyList = document.getElementById("history-list");
let latestCompletedRun = null;

export function initHistoryPanel() {
  if (!historyList) return;

  on(EVENTS.BACKTEST_COMPLETE, (event) => {
    if (event?.status === "completed" && event?.run_id) {
      latestCompletedRun = {
        runId: event.run_id,
        strategy: getState("backtest.strategy") || "",
      };
    }

    const cached = getLatestResultsPayload();
    if (cached) renderHistory(cached);
  });

  on(EVENTS.RESULTS_LOADED, renderHistory);
  renderHistory(getLatestResultsPayload());
}

function renderHistory(payload) {
  if (!historyList) return;

  if (!payload?.summary) {
    historyList.innerHTML = `
      <div class="info-empty">
        No latest persisted result is loaded yet. Full historical run browsing still needs backend support.
      </div>
    `;
    return;
  }

  const totalRow = findTotalRow(payload.results_per_pair);
  const profitPct = getProfitPct(totalRow);
  const profitLabel = profitPct == null ? "—" : formatPct(profitPct);
  const totalTrades = Number(totalRow?.trades ?? payload?.trades?.length ?? 0) || 0;
  const pairCount = Array.isArray(payload?.results_per_pair)
    ? payload.results_per_pair.filter((row) => String(row?.key ?? row?.pair ?? "") !== "TOTAL").length
    : 0;
  const tradeRange = getTradeRange(payload?.trades);
  const runId = latestCompletedRun?.strategy === payload.strategy ? latestCompletedRun.runId : null;

  const card = el("article", { class: "history-card" });
  card.innerHTML = `
    <div class="history-card__header">
      <div>
        <h3 class="history-card__title">Latest persisted result</h3>
        <p class="history-card__subtitle">${payload.strategy || "Unknown strategy"}</p>
      </div>
      <span class="history-card__badge">Latest only</span>
    </div>
    <div class="history-card__grid">
      <div><span class="history-card__label">Run ID</span><strong>${runId ?? "Not available in current payload"}</strong></div>
      <div><span class="history-card__label">Total Profit</span><strong>${profitLabel}</strong></div>
      <div><span class="history-card__label">Trades</span><strong>${totalTrades}</strong></div>
      <div><span class="history-card__label">Pairs</span><strong>${pairCount}</strong></div>
      <div><span class="history-card__label">Trade Range</span><strong>${tradeRange}</strong></div>
      <div><span class="history-card__label">Source</span><strong>Latest summary payload</strong></div>
    </div>
    <div class="history-card__footer">
      Full backtest history listing still needs backend support. This tab now reflects the current latest persisted result without adding a second fetch flow.
    </div>
  `;

  historyList.innerHTML = "";
  historyList.appendChild(card);
}

function findTotalRow(rows) {
  if (!Array.isArray(rows)) return null;
  return rows.find((row) => String(row?.key ?? row?.pair ?? "") === "TOTAL") ?? null;
}

function getProfitPct(totalRow) {
  const direct = Number(totalRow?.profit_total_pct);
  if (Number.isFinite(direct)) return direct;

  const ratio = Number(totalRow?.profit_total);
  if (Number.isFinite(ratio)) return ratio * 100;

  return null;
}

function getTradeRange(trades) {
  if (!Array.isArray(trades) || !trades.length) return "Latest persisted summary";

  const dates = trades
    .map((trade) => ({
      open: toTimestamp(trade?.open_date),
      close: toTimestamp(trade?.close_date),
    }))
    .filter((item) => item.open != null || item.close != null);

  if (!dates.length) return "Latest persisted summary";

  const start = Math.min(...dates.map((item) => item.open ?? item.close));
  const end = Math.max(...dates.map((item) => item.close ?? item.open));
  return `${formatDate(new Date(start).toISOString())} → ${formatDate(new Date(end).toISOString())}`;
}

function toTimestamp(value) {
  if (!value) return null;
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
}
