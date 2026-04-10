/**
 * index.js â€” Backtesting page entry point. Initializes all modules.
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
import { initResultsController } from "./results/results-controller.js";
import { initConfigsPanel }  from "./configs/configs-panel.js";
import { initHeaderConfigButtons } from "./configs/header-config-buttons.js";
import { getState, setState } from "../../core/state.js";
import showToast             from "../../components/toast.js";

document.addEventListener("DOMContentLoaded", async () => {
  await loadOptions();

  // Populate inputs from state (loaded from app settings)
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
  initResultsController();
  initConfigsPanel();
  initHeaderConfigButtons();

  // Timeframe select â†’ state
  const tfSelect = document.getElementById("select-timeframe");
  tfSelect?.addEventListener("change", () => {
    setState("backtest.timeframe", tfSelect.value);
  });

  // Dry run wallet → state
  walletInput?.addEventListener("change", () => {
    const value = parseFloat(walletInput.value) || null;
    setState("backtest.dry_run_wallet", value);
  });

  // Max open trades → state
  const maxOpenTradesInput = document.getElementById("input-max-trades");
  maxOpenTradesInput?.addEventListener("change", () => {
    const value = parseInt(maxOpenTradesInput.value, 10) || null;
    setState("backtest.maxOpenTrades", value);
  });
});
