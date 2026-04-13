/**
 * index.js - Optimizer page entry point.
 */

import { loadOptions } from "../backtesting/setup/options-loader.js";
import { initRunForm } from "./run-form.js";
import { initLogStream } from "./live-log-stream.js";
import { initAttemptResultPanel } from "./attempt-result-panel.js";
import { initActiveResultPanel } from "./active-result-panel.js";
import { initOptimizer } from "./optimizer.js";

document.addEventListener("DOMContentLoaded", async () => {
  initRunForm();
  initLogStream();
  initAttemptResultPanel();
  initActiveResultPanel();
  initOptimizer();

  const optionsResult = await loadOptions({
    strategySelectId: "opt-select-strategy",
    timeframeSelectId: "opt-select-timeframe",
    exchangeSelectId: null,
    persistBacktestSelections: false,
  });

  if (!optionsResult.ok) {
    console.warn("[optimizer] Could not fully load shared options:", optionsResult.errors.options || optionsResult.errors.settings);
  }
});
