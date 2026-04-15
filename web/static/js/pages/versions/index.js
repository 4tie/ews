import { initVersionListPanel } from "./version-list-panel.js";
import { initVersionDetailsPanel } from "./version-details-panel.js";
import { initVersionLineageView } from "./version-lineage-view.js";
import { getState, setState } from "../../core/state.js";
import api from "../../core/api.js";

async function loadStrategies() {
  try {
    const response = await api.backtest.options();
    const strategies = response?.strategies || [];
    setState("backtest.availableStrategies", strategies);
    
    // Get saved strategy or use first available
    let strategy = getState("backtest.strategy");
    if (!strategy && strategies.length > 0) {
      strategy = strategies[0];
    }
    if (strategy) {
      setState("backtest.strategy", strategy);
    }
    console.log("[versions] Strategies loaded:", strategies.length);
    return strategy;
  } catch (error) {
    console.error("[versions] Failed to load strategies:", error);
    return "";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  console.log("Versions page initializing...");
  
  // Load strategies from API
  await loadStrategies();

  initVersionListPanel();
  initVersionDetailsPanel();
  initVersionLineageView();

  console.log("Versions page initialized");

  const strategy = getState("backtest.strategy");
  if (!strategy) {
    console.log("No strategy selected - waiting for strategy selection");
  }
});