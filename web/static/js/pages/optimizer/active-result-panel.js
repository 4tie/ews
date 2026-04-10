/**
 * active-result-panel.js — Displays the current accepted best optimizer result.
 */

import { renderSummaryCards } from "../shared/backtest/result_renderer.js";
import { on, EVENTS } from "../../core/events.js";
import { formatPct } from "../../core/utils.js";

const panel     = document.getElementById("opt-active-result");
const bestBadge = document.getElementById("opt-best-badge");

export function initActiveResultPanel() {
  on(EVENTS.CHECKPOINT_SAVED, (checkpoint) => {
    updateActiveResult(checkpoint);
  });
}

export function updateActiveResult(checkpoint) {
  if (!checkpoint) return;
  if (bestBadge) {
    const pct = checkpoint.profit_pct ?? 0;
    bestBadge.textContent = formatPct(pct);
    bestBadge.className = `badge ${pct >= 0 ? "badge--success" : "badge--danger"}`;
  }
  renderSummaryCards(panel, checkpoint.result ?? null);
}
