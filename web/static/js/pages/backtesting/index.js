/**
 * index.js — Backtesting page entry point. Initializes all modules.
 */

import { loadOptions }       from "./setup/options-loader.js";
import { initStrategyPanel } from "./setup/strategy-panel.js";
import { initTimePanel }     from "./setup/time-panel.js";
import { initPairsPanel }    from "./setup/pairs-panel.js";
import { initRunController } from "./run/run-controller.js";
import { initLogPanel }      from "./run/log-panel.js";
import { initDataDownload }  from "./run/data-download.js";
import { initDataValidator } from "./run/data-validator.js";
import { initTradesTable }   from "./trades/table.js";
import { initPairSummary }   from "./trades/pair-summary.js";
import { initConfigsPanel }  from "./configs/configs-panel.js";
import { initHeaderConfigButtons } from "./configs/header-config-buttons.js";
import { setState }          from "../../core/state.js";
import showToast             from "../../components/toast.js";

document.addEventListener("DOMContentLoaded", async () => {
  await loadOptions();
  initStrategyPanel();
  initTimePanel();
  initPairsPanel();
  initRunController();
  initLogPanel();
  initDataDownload();
  initDataValidator();
  initTradesTable();
  initPairSummary();
  initConfigsPanel();
  initHeaderConfigButtons();

  // Timeframe select → state
  const tfSelect = document.getElementById("select-timeframe");
  tfSelect?.addEventListener("change", () => {
    setState("backtest.timeframe", tfSelect.value);
  });

  // Dry run wallet → state
  const walletInput = document.getElementById("input-dry-run-wallet");
  walletInput?.addEventListener("change", () => {
    const value = parseFloat(walletInput.value) || null;
    setState("backtest.dry_run_wallet", value);
  });
});
