/**
 * time-panel.js — Handle date range picker with presets.
 */

import { setState } from "../../../core/state.js";

export function initTimePanel() {
  const startDateInput = document.getElementById("input-start-date");
  const endDateInput = document.getElementById("input-end-date");
  const presetBtns = document.querySelectorAll(".date-presets button");
  
  // Handle preset buttons
  presetBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const preset = btn.dataset.preset;
      const [start, end] = getPresetDates(preset);
      
      if (startDateInput) startDateInput.value = start;
      if (endDateInput) endDateInput.value = end;
      
      setState("backtest.startDate", start);
      setState("backtest.endDate", end);
    });
  });
  
  // Handle manual date changes
  startDateInput?.addEventListener("change", () => {
    setState("backtest.startDate", startDateInput.value);
  });
  
  endDateInput?.addEventListener("change", () => {
    setState("backtest.endDate", endDateInput.value);
  });
}

function getPresetDates(preset) {
  const today = new Date();
  const end = formatDate(today);
  let start;
  
  switch (preset) {
    case "7":
      start = formatDate(new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000));
      break;
    case "30":
      start = formatDate(new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000));
      break;
    case "90":
      start = formatDate(new Date(today.getTime() - 90 * 24 * 60 * 60 * 1000));
      break;
    case "ytd":
      start = formatDate(new Date(today.getFullYear(), 0, 1));
      break;
    default:
      return ["", ""];
  }
  
  return [start, end];
}

function formatDate(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const year = date.getFullYear();
  return `${month}/${day}/${year}`;
}
