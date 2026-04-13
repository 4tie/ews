/**
 * index.js - Backtesting page entry point. Initializes all modules.
 */

import { loadOptions } from "./setup/options-loader.js";
import { initStrategyPanel } from "./setup/strategy-panel.js";
import { initTimePanel } from "./setup/time-panel.js";
import { initPairsPanel } from "./setup/pairs-panel.js";
import { initRunController } from "./run/run-controller.js";
import { initLogPanel } from "./run/log-panel.js";
import { initDataDownload } from "./run/data-download.js";
import { initDataValidator } from "./run/data-validator.js";
import { initTradesTable } from "./trades/table.js";
import { initPairSummary } from "./trades/pair-summary.js";
import { initChartsPanel } from "./charts/charts-panel.js";
import { initComparePanel } from "./compare/compare-panel.js";
import { initHistoryPanel } from "./history/history-panel.js";
import { initExportPanel } from "./export/export-panel.js";
import { initResultsController } from "./results/results-controller.js";
import { initProposalWorkflow } from "./results/proposal-workflow.js";
import { initConfigsPanel } from "./configs/configs-panel.js";
import { initHeaderConfigButtons } from "./configs/header-config-buttons.js";
import { getState, setState } from "../../core/state.js";

document.addEventListener("DOMContentLoaded", async () => {
  const optionsResult = await loadOptions({ persistBacktestSelections: true });

  setState("backtest.availableStrategies", Array.isArray(optionsResult.strategies) ? [...optionsResult.strategies] : []);
  setState("backtest.strategy", optionsResult.selected.strategy || "");
  setState("backtest.timeframe", optionsResult.selected.timeframe || "");
  setState("backtest.exchange", optionsResult.selected.exchange || "");

  if (optionsResult.defaults.startDate || optionsResult.defaults.endDate) {
    setState("backtest.startDate", optionsResult.defaults.startDate || "");
    setState("backtest.endDate", optionsResult.defaults.endDate || "");
  }
  if (optionsResult.defaults.dryRunWallet !== null) {
    setState("backtest.dry_run_wallet", optionsResult.defaults.dryRunWallet);
  }
  if (optionsResult.defaults.maxOpenTrades !== null) {
    setState("backtest.maxOpenTrades", optionsResult.defaults.maxOpenTrades);
  }

  const walletInput = document.getElementById("input-dry-run-wallet");
  const walletVal = getState("backtest.dry_run_wallet");
  if (walletInput && walletVal != null) {
    walletInput.value = walletVal;
  }

  const maxTradesInput = document.getElementById("input-max-trades");
  const maxTradesVal = getState("backtest.maxOpenTrades");
  if (maxTradesInput && maxTradesVal != null) {
    maxTradesInput.value = maxTradesVal;
  }

  initStrategyPanel();
  initTimePanel();
  initPairsPanel();
  initRunController();
  initLogPanel();
  initDataDownload();
  initDataValidator();
  initTradesTable();
  initPairSummary();
  initChartsPanel();
  initComparePanel();
  initHistoryPanel();
  initExportPanel();
  initConfigsPanel();
  initHeaderConfigButtons();
  initResultsController();
  initProposalWorkflow();

  const tfSelect = document.getElementById("select-timeframe");
  tfSelect?.addEventListener("change", () => {
    setState("backtest.timeframe", tfSelect.value);
  });

  const exchangeSelect = document.getElementById("select-exchange");
  exchangeSelect?.addEventListener("change", () => {
    setState("backtest.exchange", exchangeSelect.value);
  });

  walletInput?.addEventListener("change", () => {
    const value = parseFloat(walletInput.value) || null;
    setState("backtest.dry_run_wallet", value);
  });

  const maxOpenTradesInput = document.getElementById("input-max-trades");
  maxOpenTradesInput?.addEventListener("change", () => {
    const value = parseInt(maxOpenTradesInput.value, 10) || null;
    setState("backtest.maxOpenTrades", value);
  });
});
