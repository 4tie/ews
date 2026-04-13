/**
 * strategy-panel.js — Manages strategy select state and persistence.
 */

import { setState } from "../../../core/state.js";
import { KEYS } from "../../../core/persistence.js";
import { usePersistentState } from "../../../core/usePersistentState.js";

const select = document.getElementById("select-strategy");
let persistBacktestConfig = null;

function applyStrategySelection(strategyName) {
  if (!select) return false;

  const next = String(strategyName || "").trim();
  const hasOption = !next || Array.from(select.options).some((option) => option.value === next);
  if (!hasOption) return false;

  select.value = next;
  setState("backtest.strategy", next);
  persistBacktestConfig?.((prev) => ({ ...prev, strategy: next }));
  return true;
}

export function switchBacktestStrategy(strategyName) {
  return applyStrategySelection(strategyName);
}

export function initStrategyPanel() {
  if (!select) return;

  const [savedConfig, setSavedConfig] = usePersistentState(KEYS.BACKTEST_CONFIG, {});
  persistBacktestConfig = setSavedConfig;

  if (savedConfig.strategy) {
    applyStrategySelection(savedConfig.strategy);
  }

  select.addEventListener("change", () => {
    applyStrategySelection(select.value);
  });
}
