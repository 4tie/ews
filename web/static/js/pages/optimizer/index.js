/**
 * index.js — Optimizer page entry point.
 */

import { initRunForm }           from "./run-form.js";
import { initLogStream }         from "./live-log-stream.js";
import { initAttemptResultPanel } from "./attempt-result-panel.js";
import { initActiveResultPanel }  from "./active-result-panel.js";
import { initOptimizer }          from "./optimizer.js";
import api                        from "../../core/api.js";

document.addEventListener("DOMContentLoaded", async () => {
  initRunForm();
  initLogStream();
  initAttemptResultPanel();
  initActiveResultPanel();
  initOptimizer();

  // Populate strategy + timeframe selects
  try {
    const { strategies, timeframes } = await api.backtest.options();
    const stratSel = document.getElementById("opt-select-strategy");
    const tfSel    = document.getElementById("opt-select-timeframe");

    strategies.forEach(s => {
      const o = document.createElement("option");
      o.value = s; o.textContent = s;
      stratSel?.appendChild(o);
    });
    timeframes.forEach(tf => {
      const o = document.createElement("option");
      o.value = tf; o.textContent = tf;
      tfSel?.appendChild(o);
    });
  } catch (e) {
    console.warn("Could not load options:", e.message);
  }
});
