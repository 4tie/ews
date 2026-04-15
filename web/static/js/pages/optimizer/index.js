/**
 * index.js - Optimizer page entry point. Initializes the optimizer panel.
 */

import { initAutoOptimizePanel } from "../backtesting/optimizer/auto-optimize-panel.js";

document.addEventListener("DOMContentLoaded", () => {
  initAutoOptimizePanel();
});
