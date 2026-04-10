/**
 * time-panel.js — Manages start/end date inputs and persistence.
 */

import { setState, getState } from "../../../core/state.js";
import persistence, { KEYS } from "../../../core/persistence.js";
import { usePersistentState } from "../../../core/usePersistentState.js";

const startInput = document.getElementById("input-start-date");
const endInput   = document.getElementById("input-end-date");

export function initTimePanel() {
  if (!startInput || !endInput) return;

  const [savedConfig, setSavedConfig] = usePersistentState(KEYS.BACKTEST_CONFIG, {});
  
  if (savedConfig.startDate) { 
    startInput.value = savedConfig.startDate; 
    setState("backtest.startDate", savedConfig.startDate); 
  }
  if (savedConfig.endDate)   { 
    endInput.value = savedConfig.endDate;     
    setState("backtest.endDate",   savedConfig.endDate); 
  }

  startInput.addEventListener("change", () => {
    setState("backtest.startDate", startInput.value);
    setSavedConfig(prev => ({ ...prev, startDate: startInput.value }));
  });
  endInput.addEventListener("change", () => {
    setState("backtest.endDate", endInput.value);
    setSavedConfig(prev => ({ ...prev, endDate: endInput.value }));
  });
}
