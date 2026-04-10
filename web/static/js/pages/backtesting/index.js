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

  // Timeframe select → state
  const tfSelect = document.getElementById("select-timeframe");
  tfSelect?.addEventListener("change", () => {
    setState("backtest.timeframe", tfSelect.value);
  });
});
