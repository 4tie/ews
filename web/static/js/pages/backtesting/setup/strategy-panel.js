/**
 * strategy-panel.js — Manages strategy select state and persistence.
 */

import { setState, getState } from "../../../core/state.js";
import { emit, EVENTS } from "../../../core/events.js";
import persistence, { KEYS } from "../../../core/persistence.js";

const select = document.getElementById("select-strategy");

export function initStrategyPanel() {
  if (!select) return;

  // Restore saved strategy
  const saved = persistence.load(KEYS.BACKTEST_CONFIG, {});
  if (saved.strategy) {
    select.value = saved.strategy;
    setState("backtest.strategy", saved.strategy);
  }

  select.addEventListener("change", () => {
    const val = select.value;
    setState("backtest.strategy", val);
    _persist();
  });
}

function _persist() {
  const cfg = persistence.load(KEYS.BACKTEST_CONFIG, {});
  cfg.strategy = getState("backtest.strategy");
  persistence.save(KEYS.BACKTEST_CONFIG, cfg);
}
