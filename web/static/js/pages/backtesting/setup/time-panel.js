/**
 * time-panel.js — Manages start/end date inputs and persistence.
 */

import { setState, getState } from "../../../core/state.js";
import persistence, { KEYS } from "../../../core/persistence.js";
import { usePersistentState } from "../../../core/usePersistentState.js";

const startInput = document.getElementById("input-start-date");
const endInput = document.getElementById("input-end-date");

function parseDateString(dateStr) {
  if (!dateStr) return null;
  
  let year, month, day;
  
  if (dateStr.includes("/")) {
    const parts = dateStr.split("/");
    if (parts.length === 3) {
      month = parseInt(parts[0], 10);
      day = parseInt(parts[1], 10);
      year = parseInt(parts[2], 10);
      if (year < 100) year += 2000;
    }
  } else if (dateStr.includes("-")) {
    const parts = dateStr.split("-");
    if (parts.length === 3) {
      year = parseInt(parts[0], 10);
      month = parseInt(parts[1], 10);
      day = parseInt(parts[2], 10);
    }
  }
  
  if (!year || !month || !day || isNaN(year) || isNaN(month) || isNaN(day)) {
    return null;
  }
  
  return { year, month, day };
}

function toBackendFormat(dateObj) {
  if (!dateObj) return "";
  const y = dateObj.year;
  const m = String(dateObj.month).padStart(2, "0");
  const d = String(dateObj.day).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function toDisplayFormat(dateObj) {
  if (!dateObj) return "";
  const m = String(dateObj.month).padStart(2, "0");
  const d = String(dateObj.day).padStart(2, "0");
  return `${m}/${d}/${dateObj.year}`;
}

function convertToDisplay(value) {
  if (!value) return "";
  const parsed = parseDateString(value);
  if (!parsed) return value;
  return toDisplayFormat(parsed);
}

function convertToBackend(value) {
  if (!value) return "";
  const parsed = parseDateString(value);
  if (!parsed) return value;
  return toBackendFormat(parsed);
}

export function initTimePanel() {
  if (!startInput || !endInput) return;

  const [savedConfig, setSavedConfig] = usePersistentState(KEYS.BACKTEST_CONFIG, {});
  
  if (savedConfig.startDate) { 
    startInput.value = convertToDisplay(savedConfig.startDate); 
    setState("backtest.startDate", savedConfig.startDate); 
  }
  if (savedConfig.endDate)   { 
    endInput.value = convertToDisplay(savedConfig.endDate);     
    setState("backtest.endDate",   savedConfig.endDate); 
  }

  startInput.addEventListener("change", () => {
    const backendValue = convertToBackend(startInput.value);
    setState("backtest.startDate", backendValue);
    setSavedConfig(prev => ({ ...prev, startDate: backendValue }));
  });
  endInput.addEventListener("change", () => {
    const backendValue = convertToBackend(endInput.value);
    setState("backtest.endDate", backendValue);
    setSavedConfig(prev => ({ ...prev, endDate: backendValue }));
  });
}
