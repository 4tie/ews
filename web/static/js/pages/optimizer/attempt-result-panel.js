/**
 * attempt-result-panel.js — Displays the latest optimizer epoch attempt.
 */

import { renderSummaryCards } from "../shared/backtest/result_renderer.js";
import { on, EVENTS } from "../../core/events.js";

const panel    = document.getElementById("opt-attempt-result");
const epochBadge = document.getElementById("opt-current-epoch");

export function initAttemptResultPanel() {
  on(EVENTS.OPTIMIZER_EPOCH, (data) => {
    if (epochBadge) epochBadge.textContent = `epoch ${data?.epoch ?? "—"}`;
    renderSummaryCards(panel, data?.result ?? null);
  });
}

export function updateAttemptResult(epoch, result) {
  if (epochBadge) epochBadge.textContent = `epoch ${epoch}`;
  renderSummaryCards(panel, result);
}
