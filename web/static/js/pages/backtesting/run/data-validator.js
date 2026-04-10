/**
 * data-validator.js - Validate data availability before running backtest.
 */

import api from "../../../core/api.js";
import { getState } from "../../../core/state.js";
import showToast from "../../../components/toast.js";
import { setButtonLoading } from "../../../components/loading-state.js";

const validateBtn = document.getElementById("btn-validate-data");
const validationOutput = document.getElementById("data-validation-output");

function renderResult(results) {
  if (!validationOutput) return;

  if (!results.length) {
    validationOutput.innerHTML = '<span class="muted">No validation results were returned.</span>';
    showToast("No validation results were returned.", "warning");
    return;
  }

  let html = '<ul class="validation-list">';
  let hasIssues = false;

  for (const item of results) {
    const status = item.status;
    let icon = "";
    let cls = "";

    if (status === "valid") {
      icon = "[ok]";
      cls = "valid";
    } else if (status === "missing") {
      icon = "[!]";
      cls = "warning";
      hasIssues = true;
    } else if (status === "unconfigured") {
      icon = "[ ]";
      cls = "neutral";
      hasIssues = true;
    }

    html += `<li class="${cls}"><span class="icon">${icon}</span> ${item.pair}: ${item.message || status}</li>`;
  }
  html += "</ul>";

  validationOutput.innerHTML = html;

  if (hasIssues) {
    showToast("Some pairs have data issues.", "warning");
  } else {
    showToast("All pairs have valid data.", "success");
  }
}

export function initDataValidator() {
  validateBtn?.addEventListener("click", async () => {
    const pairs = getState("backtest.pairs") || [];
    const timeframe = getState("backtest.timeframe");
    if (!pairs.length) {
      showToast("Add pairs first.", "warning");
      return;
    }
    if (!timeframe) {
      showToast("Select a timeframe first.", "warning");
      return;
    }

    setButtonLoading(validateBtn, true, "Checking...");
    if (validationOutput) validationOutput.textContent = "Checking data availability...";

    try {
      const data = await api.backtest.validateData({ pairs, timeframe });
      renderResult(data.results || []);
    } catch (err) {
      const message = err?.message || String(err);
      if (validationOutput) validationOutput.textContent = `Error: ${message}`;
      showToast("Validation failed: " + message, "error");
    } finally {
      setButtonLoading(validateBtn, false);
    }
  });
}
