/**
 * time-panel.js — Manages start/end date inputs and persistence.
 */

import { setState, getState } from "../../../core/state.js";
import persistence, { KEYS } from "../../../core/persistence.js";

const startInput = document.getElementById("input-start-date");
const endInput   = document.getElementById("input-end-date");

export function initTimePanel() {
  if (!startInput || !endInput) return;

  const saved = persistence.load(KEYS.BACKTEST_CONFIG, {});
  if (saved.startDate) { startInput.value = saved.startDate; setState("backtest.startDate", saved.startDate); }
  if (saved.endDate)   { endInput.value = saved.endDate;     setState("backtest.endDate",   saved.endDate); }

  startInput.addEventListener("change", () => {
    setState("backtest.startDate", startInput.value);
    _persist();
  });
  endInput.addEventListener("change", () => {
    setState("backtest.endDate", endInput.value);
    _persist();
  });
}

function _persist() {
  const cfg = persistence.load(KEYS.BACKTEST_CONFIG, {});
  cfg.startDate = getState("backtest.startDate");
  cfg.endDate   = getState("backtest.endDate");
  persistence.save(KEYS.BACKTEST_CONFIG, cfg);
}
