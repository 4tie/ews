/**
 * history-panel.js - Renders persisted backtest run history from backend reads.
 */

import { el, formatDate, formatNum, formatPct } from "../../../core/utils.js";
import {
  initPersistedRunsStore,
  subscribePersistedRuns,
} from "../results/persisted-runs-store.js";

const historyList = document.getElementById("history-list");

export function initHistoryPanel() {
  if (!historyList) return;

  initPersistedRunsStore();
  subscribePersistedRuns(renderHistoryState);
}

function renderHistoryState(state) {
  if (!historyList) return;

  if (state.status === "loading" && !state.runs.length) {
    historyList.innerHTML = '<div class="info-empty">Loading persisted backtest history...</div>';
    return;
  }

  if (state.status === "error") {
    historyList.innerHTML = `<div class="info-empty">Failed to load persisted backtest history: ${escapeHtml(state.error)}</div>`;
    return;
  }

  renderHistory(Array.isArray(state.runs) ? state.runs : [], state.strategy || "");
}

function renderHistory(runs, strategy) {
  if (!historyList) return;

  historyList.innerHTML = "";

  if (!runs.length) {
    const scope = strategy ? ` for ${escapeHtml(strategy)}` : "";
    historyList.innerHTML = `<div class="info-empty">No persisted backtest runs are available${scope}.</div>`;
    return;
  }

  const stack = el("div", { class: "history-stack" });
  const summary = el(
    "div",
    { class: "history-summary" },
    strategy
      ? `Showing ${runs.length} persisted freqtrade run(s) for ${strategy}.`
      : `Showing ${runs.length} persisted freqtrade run(s).`
  );
  stack.appendChild(summary);

  runs.forEach((run) => stack.appendChild(buildHistoryCard(run)));
  historyList.appendChild(stack);
}

function buildHistoryCard(run) {
  const metrics = run?.summary_metrics || {};
  const profitLabel = metrics.profit_total_pct == null ? "No summary" : formatPct(metrics.profit_total_pct);
  const pairCount = metrics.pair_count == null ? "-" : `${metrics.pair_count}`;
  const tradeCount = metrics.total_trades == null ? "-" : `${metrics.total_trades}`;
  const tradeRange = formatTradeRange(metrics);
  const createdAt = formatDate(run?.created_at);
  const completedAt = run?.completed_at ? formatDate(run.completed_at) : "Not completed";
  const strategy = metrics.strategy || run?.strategy || "Unknown strategy";
  const footerText = buildFooterText(run, metrics);

  const card = el("article", { class: "history-card" });
  card.innerHTML = `
    <div class="history-card__header">
      <div>
        <h3 class="history-card__title">${escapeHtml(strategy)}</h3>
        <p class="history-card__subtitle">Created ${createdAt}</p>
      </div>
      <span class="history-card__badge history-card__badge--${escapeAttr(run?.status || "unknown")}">${escapeHtml(labelize(run?.status || "unknown"))}</span>
    </div>
    <div class="history-card__grid">
      <div><span class="history-card__label">Run ID</span><strong>${escapeHtml(run?.run_id || "-")}</strong></div>
      <div><span class="history-card__label">Version</span><strong>${escapeHtml(run?.version_id || "Base")}</strong></div>
      <div><span class="history-card__label">Total Profit</span><strong>${profitLabel}</strong></div>
      <div><span class="history-card__label">Trades</span><strong>${tradeCount}</strong></div>
      <div><span class="history-card__label">Pairs</span><strong>${pairCount}</strong></div>
      <div><span class="history-card__label">Trade Range</span><strong>${escapeHtml(tradeRange)}</strong></div>
      <div><span class="history-card__label">Completed</span><strong>${completedAt}</strong></div>
      <div><span class="history-card__label">Exit Code</span><strong>${formatExitCode(run?.exit_code)}</strong></div>
    </div>
    <div class="history-card__footer">${escapeHtml(footerText)}</div>
  `;

  return card;
}

function buildFooterText(run, metrics) {
  if (run?.error) {
    return `Trigger ${labelize(run?.trigger_source || "manual")} | ${run.error}`;
  }
  if (!run?.summary_available) {
    return `Trigger ${labelize(run?.trigger_source || "manual")} | Persisted run metadata exists, but no ingested summary artifact is linked to this run.`;
  }

  const parts = [`Trigger ${labelize(run?.trigger_source || "manual")}`];
  if (metrics?.timeframe) parts.push(`Timeframe ${metrics.timeframe}`);
  if (metrics?.max_drawdown_pct != null) parts.push(`Max drawdown ${formatPct(-Math.abs(metrics.max_drawdown_pct))}`);
  if (metrics?.profit_total_abs != null) {
    const currency = metrics?.stake_currency ? ` ${metrics.stake_currency}` : "";
    parts.push(`Abs profit ${formatSignedNumber(metrics.profit_total_abs)}${currency}`);
  }
  return parts.join(" | ");
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

function formatExitCode(value) {
  return value == null ? "-" : String(value);
}

function formatSignedNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value || "-");
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${formatNum(number, 2)}`;
}

function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value) {
  return String(value ?? "").replace(/[^a-z0-9_-]/gi, "-").toLowerCase();
}
