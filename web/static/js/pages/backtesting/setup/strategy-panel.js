/**
 * strategy-panel.js — Handle strategy selection.
 */

import { setState } from "../../../core/state.js";

export function initStrategyPanel() {
  const strategySelect = document.getElementById("select-strategy");
  
  strategySelect?.addEventListener("change", () => {
    setState("backtest.strategy", strategySelect.value);
  });
}
