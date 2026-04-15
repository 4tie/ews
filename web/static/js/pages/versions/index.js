import { initVersionListPanel } from "./version-list-panel.js";
import { initVersionDetailsPanel } from "./version-details-panel.js";
import { initVersionLineageView } from "./version-lineage-view.js";
import { getState, setState } from "../../core/state.js";
import { loadOptions } from "../backtesting/setup/options-loader.js";

document.addEventListener("DOMContentLoaded", async () => {
  // Ensure options are loaded first
  const optionsResult = await loadOptions({ persistBacktestSelections: false });
  
  setState("backtest.availableStrategies", Array.isArray(optionsResult.strategies) ? [...optionsResult.strategies] : []);
  if (!getState("backtest.strategy") && optionsResult.selected.strategy) {
    setState("backtest.strategy", optionsResult.selected.strategy);
  }
  if (!getState("backtest.timeframe") && optionsResult.selected.timeframe) {
    setState("backtest.timeframe", optionsResult.selected.timeframe);
  }
  if (!getState("backtest.exchange") && optionsResult.selected.exchange) {
    setState("backtest.exchange", optionsResult.selected.exchange);
  }

  initVersionListPanel();
  initVersionDetailsPanel();
  initVersionLineageView();

  console.log("Versions page initialized");

  const strategy = getState("backtest.strategy");
  if (!strategy) {
    console.log("No strategy selected - waiting for strategy selection");
  }
});