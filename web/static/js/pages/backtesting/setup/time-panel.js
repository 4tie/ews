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

function setPreset(days, setSavedConfig) {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  
  const startDate = {
    year: start.getFullYear(),
    month: start.getMonth() + 1,
    day: start.getDate()
  };
  const endDate = {
    year: end.getFullYear(),
    month: end.getMonth() + 1,
    day: end.getDate()
  };
  
  startInput.value = toDisplayFormat(startDate);
  endInput.value = toDisplayFormat(endDate);
  
  const backendStart = toBackendFormat(startDate);
  const backendEnd = toBackendFormat(endDate);
  setState("backtest.startDate", backendStart);
  setState("backtest.endDate", backendEnd);
  setSavedConfig(prev => ({ ...prev, startDate: backendStart, endDate: backendEnd }));
}

function setYtdPreset(setSavedConfig) {
  const end = new Date();
  const start = new Date();
  start.setMonth(0, 1);
  
  const startDate = {
    year: start.getFullYear(),
    month: start.getMonth() + 1,
    day: start.getDate()
  };
  const endDate = {
    year: end.getFullYear(),
    month: end.getMonth() + 1,
    day: end.getDate()
  };
  
  startInput.value = toDisplayFormat(startDate);
  endInput.value = toDisplayFormat(endDate);
  
  const backendStart = toBackendFormat(startDate);
  const backendEnd = toBackendFormat(endDate);
  setState("backtest.startDate", backendStart);
  setState("backtest.endDate", backendEnd);
  setSavedConfig(prev => ({ ...prev, startDate: backendStart, endDate: backendEnd }));
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
  
  const presetButtons = document.querySelectorAll("[data-preset]");
  presetButtons.forEach(btn => btn.addEventListener("click", (e) => handlePresetClick(e, setSavedConfig)));
}
