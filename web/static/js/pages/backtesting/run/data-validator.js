/**
 * data-validator.js — Validate data availability before running backtest.
 */

import { getState } from "../../../core/state.js";
import showToast from "../../../components/toast.js";
import { setButtonLoading } from "../../../components/loading-state.js";

const validateBtn    = document.getElementById("btn-validate-data");
const validationOutput = document.getElementById("data-validation-output");

export function initDataValidator() {
  validateBtn?.addEventListener("click", async () => {
    const pairs     = getState("backtest.pairs") || [];
    const timeframe = getState("backtest.timeframe");
    if (!pairs.length)  { showToast("Add pairs first.", "warning"); return; }
    if (!timeframe)     { showToast("Select a timeframe first.", "warning"); return; }

    setButtonLoading(validateBtn, true, "Checking…");
    if (validationOutput) validationOutput.textContent = "Checking data availability…";

    // TODO: call backend validation endpoint when implemented
    await new Promise(r => setTimeout(r, 600));

    if (validationOutput) {
      validationOutput.textContent = `${pairs.length} pair(s) checked for ${timeframe}. Backend validation wiring pending.`;
    }
    setButtonLoading(validateBtn, false);
  });
}
