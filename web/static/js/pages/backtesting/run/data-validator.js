/**
 * data-validator.js — Handle data validation requests.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import { getState } from "../../../core/state.js";

export function initDataValidator() {
  const validateBtn = document.getElementById("btn-validate-data");
  const validationOutput = document.getElementById("data-validation-output");
  
  validateBtn?.addEventListener("click", async () => {
    const pairs = getState("backtest.pairs") || [];
    const timeframe = document.getElementById("select-timeframe")?.value;
    const exchange = document.getElementById("select-exchange")?.value || "binance";
    const startDate = document.getElementById("input-start-date")?.value;
    const endDate = document.getElementById("input-end-date")?.value;
    
    if (!pairs.length) {
      showToast("Please add pairs first", "warning");
      return;
    }
    
    if (!timeframe) {
      showToast("Please select a timeframe", "warning");
      return;
    }
    
    validateBtn.disabled = true;
    if (validationOutput) {
      validationOutput.innerHTML = '<span class="muted">Validating...</span>';
    }
    
    try {
      const timerange = startDate && endDate 
        ? `${formatDateToYYYYMMDD(startDate)}-${formatDateToYYYYMMDD(endDate)}`
        : null;
      
      const response = await api.post("/api/backtest/validate-data", {
        pairs,
        timeframe,
        exchange,
        timerange,
      });
      
      renderValidationResults(response, validationOutput);
      
    } catch (error) {
      showToast("Validation failed: " + error.message, "error");
      if (validationOutput) {
        validationOutput.innerHTML = `<span class="error">${error.message}</span>`;
      }
    } finally {
      validateBtn.disabled = false;
    }
  });
}

function renderValidationResults(response, container) {
  if (!container) return;
  
  const { valid, message, summary } = response;
  
  let html = `<div class="validation-result ${valid ? "valid" : "invalid"}">`;
  html += `<p>${message}</p>`;
  
  if (summary) {
    html += `<div class="validation-summary">`;
    html += `<p>Exchange: ${summary.exchange}</p>`;
    html += `<p>Timeframe: ${summary.timeframe}</p>`;
    if (summary.timerange) html += `<p>Requested: ${summary.timerange}</p>`;
    html += `<p>Ready: ${summary.ready_count} / ${summary.pair_count}</p>`;
    if (summary.partial) html += `<p>Partial: ${summary.partial}</p>`;
    html += `</div>`;
  }
  
  html += `</div>`;
  container.innerHTML = html;
}

function formatDateToYYYYMMDD(dateStr) {
  if (dateStr.includes("/")) {
    const [month, day, year] = dateStr.split("/");
    return `${year}${month.padStart(2, "0")}${day.padStart(2, "0")}`;
  }
  if (dateStr.includes("-")) {
    const [year, month, day] = dateStr.split("-");
    return `${year}${month}${day}`;
  }
  return dateStr;
}
