/**
 * time-panel.js — Manages start/end date inputs and persistence.
 */

import { setState, getState } from "../../../core/state.js";
import persistence, { KEYS } from "../../../core/persistence.js";
import { usePersistentState } from "../../../core/usePersistentState.js";

const startInput = document.getElementById("input-start-date");
const endInput = document.getElementById("input-end-date");

/** Format Date to YYYY-MM-DD for native date inputs */
function toDateInputValue(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function setPreset(days, setSavedConfig) {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);

  const startStr = toDateInputValue(start);
  const endStr = toDateInputValue(end);

  startInput.value = startStr;
  endInput.value = endStr;

  setState("backtest.startDate", startStr);
  setState("backtest.endDate", endStr);
  setSavedConfig(prev => ({ ...prev, startDate: startStr, endDate: endStr }));
}

function setYtdPreset(setSavedConfig) {
  const end = new Date();
  const start = new Date();
  start.setMonth(0, 1);

  const startStr = toDateInputValue(start);
  const endStr = toDateInputValue(end);

  startInput.value = startStr;
  endInput.value = endStr;

  setState("backtest.startDate", startStr);
  setState("backtest.endDate", endStr);
  setSavedConfig(prev => ({ ...prev, startDate: startStr, endDate: endStr }));
}

function handlePresetClick(event, setSavedConfig) {
  const preset = event.target.dataset.preset;
  switch (preset) {
    case "7":
      setPreset(7, setSavedConfig);
      break;
    case "30":
      setPreset(30, setSavedConfig);
      break;
    case "90":
      setPreset(90, setSavedConfig);
      break;
    case "ytd":
      setYtdPreset(setSavedConfig);
      break;
  }
}

export function initTimePanel() {
  if (!startInput || !endInput) return;

  const [savedConfig, setSavedConfig] = usePersistentState(KEYS.BACKTEST_CONFIG, {});

  // Native date inputs use YYYY-MM-DD format directly
  if (savedConfig.startDate) {
    startInput.value = savedConfig.startDate;
    setState("backtest.startDate", savedConfig.startDate);
  }
  if (savedConfig.endDate) {
    endInput.value = savedConfig.endDate;
    setState("backtest.endDate", savedConfig.endDate);
  }

  startInput.addEventListener("change", () => {
    const value = startInput.value;
    setState("backtest.startDate", value);
    setSavedConfig(prev => ({ ...prev, startDate: value }));
  });
  endInput.addEventListener("change", () => {
    const value = endInput.value;
    setState("backtest.endDate", value);
    setSavedConfig(prev => ({ ...prev, endDate: value }));
  });

  const presetButtons = document.querySelectorAll("[data-preset]");
  presetButtons.forEach(btn => btn.addEventListener("click", (e) => handlePresetClick(e, setSavedConfig)));
}
