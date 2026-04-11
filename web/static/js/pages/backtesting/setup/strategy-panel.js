/**
 * strategy-panel.js — Manages strategy select state and persistence.
 */

import { setState, getState } from "../../../core/state.js";
import { emit, EVENTS } from "../../../core/events.js";
import persistence, { KEYS } from "../../../core/persistence.js";
import { usePersistentState } from "../../../core/usePersistentState.js";

const select = document.getElementById("select-strategy");

export function initStrategyPanel() {
  if (!select) return;

  const [savedConfig, setSavedConfig] = usePersistentState(KEYS.BACKTEST_CONFIG, {});
  
  if (savedConfig.strategy) {
    select.value = savedConfig.strategy;
    setState("backtest.strategy", savedConfig.strategy);
  }

  select.addEventListener("change", () => {
    const val = select.value;
    setState("backtest.strategy", val);
    setSavedConfig(prev => ({ ...prev, strategy: val }));
  });
}
