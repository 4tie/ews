/**
 * results-controller.js — Fetches backtest summary and fans out results rendering.
 */

import api from "../../../core/api.js";
import { getState } from "../../../core/state.js";
import { on, emit, EVENTS } from "../../../core/events.js";
import { renderSummaryCards } from "../../shared/backtest/result_renderer.js";

const summaryCards = document.getElementById("summary-cards");
let latestResultsPayload = null;

export function getLatestResultsPayload() {
  return latestResultsPayload;
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function resolveStrategyBlock(summary, strategy) {
  if (!isObject(summary)) return null;

  const direct = summary?.[strategy];
  if (isObject(direct)) return direct;

  for (const [key, value] of Object.entries(summary)) {
    if (key === "strategy_comparison") continue;
    if (isObject(value)) return value;
  }

  return null;
}

async function refresh() {
  const strategy = getState("backtest.strategy");
  if (!strategy) {
    latestResultsPayload = null;
    renderSummaryCards(summaryCards, null);
    return;
  }

  try {
    const { summary } = await api.backtest.summary(strategy);
    renderSummaryCards(summaryCards, summary ?? null);

    const block = resolveStrategyBlock(summary, strategy);
    latestResultsPayload = {
      strategy,
      summary: summary ?? null,
      trades: Array.isArray(block?.trades) ? block.trades : [],
      results_per_pair: Array.isArray(block?.results_per_pair) ? block.results_per_pair : [],
    };

    emit(EVENTS.RESULTS_LOADED, latestResultsPayload);
  } catch (e) {
    console.warn("[backtesting] Failed to load summary:", e);
  }
}

export function initResultsController() {
  refresh();
  on(EVENTS.BACKTEST_COMPLETE, () => refresh());
}
