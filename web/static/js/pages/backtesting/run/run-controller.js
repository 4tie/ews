/**
 * run-controller.js — Handles the Run / Stop backtest buttons and status.
 */

import api from "../../../core/api.js";
import { getState, setState } from "../../../core/state.js";
import { emit, EVENTS } from "../../../core/events.js";
import showToast from "../../../components/toast.js";
import { setButtonLoading } from "../../../components/loading-state.js";

const runBtn    = document.getElementById("btn-run-backtest");
const stopBtn   = document.getElementById("btn-stop-backtest");
const statusDot = document.getElementById("run-status-dot");
const statusLbl = document.getElementById("run-status-label");

function setStatus(state, label) {
  if (statusDot) statusDot.className = `status-dot status-dot--${state}`;
  if (statusLbl) statusLbl.textContent = label;
}

export function initRunController() {
  runBtn?.addEventListener("click", async () => {
    const strategy  = getState("backtest.strategy");
    const timeframe = getState("backtest.timeframe");
    if (!strategy)  { showToast("Please select a strategy.", "warning"); return; }
    if (!timeframe) { showToast("Please select a timeframe.", "warning"); return; }

    const startDate = getState("backtest.startDate");
    const endDate   = getState("backtest.endDate");
    const timerange = (startDate && endDate)
      ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
      : undefined;

    const payload = {
      strategy,
      timeframe,
      timerange,
      pairs:    getState("backtest.pairs") || [],
      exchange: getState("backtest.exchange") || "binance",
    };

    setButtonLoading(runBtn, true, "Running…");
    if (stopBtn) stopBtn.disabled = false;
    setStatus("running", "Running…");
    setState("backtest.isRunning", true);
    emit(EVENTS.BACKTEST_STARTED, payload);

    try {
      const res = await api.backtest.run(payload);
      showToast("Backtest queued: " + (res.message || res.status), "info");
      // TODO: poll or stream log output; on completion call emit(EVENTS.BACKTEST_COMPLETE, result)
    } catch (e) {
      showToast("Run failed: " + e.message, "error");
      setStatus("error", "Error");
      emit(EVENTS.BACKTEST_FAILED, e);
    } finally {
      setButtonLoading(runBtn, false);
      if (stopBtn) stopBtn.disabled = true;
      setState("backtest.isRunning", false);
    }
  });

  stopBtn?.addEventListener("click", () => {
    // TODO: wire stop signal to backend
    setStatus("idle", "Stopped");
    setState("backtest.isRunning", false);
    emit(EVENTS.BACKTEST_STOPPED);
    if (stopBtn) stopBtn.disabled = true;
    setButtonLoading(runBtn, false);
    showToast("Stop signal sent.", "warning");
  });
}
