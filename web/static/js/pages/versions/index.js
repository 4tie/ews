import { initVersionListPanel } from "./version-list-panel.js";
import { initVersionDetailsPanel } from "./version-details-panel.js";
import { initVersionLineageView } from "./version-lineage-view.js";
import { getState } from "../../core/state.js";

document.addEventListener("DOMContentLoaded", () => {
  initVersionListPanel();
  initVersionDetailsPanel();
  initVersionLineageView();

  console.log("Versions page initialized");

  const strategy = getState("backtest.strategy");
  if (!strategy) {
    console.log("No strategy selected - waiting for strategy selection");
  }
});