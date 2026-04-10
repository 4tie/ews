/**
 * run-controller.js - Handles the Run / Stop backtest buttons and status.
 */

import api from "../../../core/api.js";
import { getState, setState } from "../../../core/state.js";
import { emit, EVENTS } from "../../../core/events.js";
import showToast from "../../../components/toast.js";
import { setButtonLoading } from "../../../components/loading-state.js";
import { refreshBacktestPreview } from "../../../components/command-preview.js";
import { startStream, stopStream } from "./log-panel.js";

const runBtn = document.getElementById("btn-run-backtest");
const stopBtn = document.getElementById("btn-stop-backtest");
const statusDot = document.getElementById("run-status-dot");
const statusLbl = document.getElementById("run-status-label");

let _currentRunId = null;

function setStatus(state, label) {
  if (statusDot) statusDot.className = `status-dot status-dot--${state}`;
  if (statusLbl) statusLbl.textContent = label;
}

function finishRun(status, exitCode) {
  const s = String(status || "");
  if (s === "completed") {
    setStatus("done", `Completed (exit ${exitCode ?? 0})`);
    showToast("Backtest completed.", "success");
    emit(EVENTS.BACKTEST_COMPLETE, { run_id: _currentRunId, status: s, exit_code: exitCode });
  } else if (s === "failed") {
    setStatus("error", `Failed (exit ${exitCode ?? "?"})`);
    showToast("Backtest failed.", "error");
    emit(EVENTS.BACKTEST_FAILED, { run_id: _currentRunId, status: s, exit_code: exitCode });
  } else {
    setStatus("idle", s || "Done");
    emit(EVENTS.BACKTEST_COMPLETE, { run_id: _currentRunId, status: s, exit_code: exitCode });
  }

  if (stopBtn) stopBtn.disabled = true;
  setButtonLoading(runBtn, false);
  setState("backtest.isRunning", false);
}

export function initRunController() {
  runBtn?.addEventListener("click", async () => {
    const strategy = getState("backtest.strategy");
    const timeframe = getState("backtest.timeframe");
    if (!strategy) {
      showToast("Please select a strategy.", "warning");
      return;
    }
    if (!timeframe) {
      showToast("Please select a timeframe.", "warning");
      return;
    }

    const startDate = getState("backtest.startDate");
    const endDate = getState("backtest.endDate");
    const timerange = startDate && endDate
      ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
      : undefined;

    const payload = {
      strategy,
      timeframe,
      timerange,
      pairs: getState("backtest.pairs") || [],
      exchange: getState("backtest.exchange") || "binance",
      dry_run_wallet: getState("backtest.dry_run_wallet") || undefined,
      max_open_trades: getState("backtest.maxOpenTrades") || undefined,
    };

    await refreshBacktestPreview({
      strategy: payload.strategy,
      timeframe: payload.timeframe,
      pairs: payload.pairs,
      startDate,
      endDate,
      dryRunWallet: payload.dry_run_wallet,
      maxOpenTrades: payload.max_open_trades,
    });

    setButtonLoading(runBtn, true, "Running...");
    if (stopBtn) stopBtn.disabled = false;
    setStatus("running", "Running...");
    setState("backtest.isRunning", true);
    emit(EVENTS.BACKTEST_STARTED, payload);

    try {
      const res = await api.backtest.run(payload);
      _currentRunId = res.run_id;
      showToast(`Backtest started: ${_currentRunId}`, "info");

      startStream(`/api/backtest/runs/${_currentRunId}/logs/stream`, {
        onDone: (status, exitCode) => finishRun(status, exitCode),
      });
    } catch (e) {
      stopStream();
      showToast("Run failed: " + e.message, "error");
      setStatus("error", "Error");
      emit(EVENTS.BACKTEST_FAILED, e);
      if (stopBtn) stopBtn.disabled = true;
      setButtonLoading(runBtn, false);
      setState("backtest.isRunning", false);
    }
  });

  stopBtn?.addEventListener("click", () => {
    // TODO: wire stop signal to backend
    stopStream();
    setStatus("idle", "Stopped");
    setState("backtest.isRunning", false);
    emit(EVENTS.BACKTEST_STOPPED, { run_id: _currentRunId });
    if (stopBtn) stopBtn.disabled = true;
    setButtonLoading(runBtn, false);
    showToast("Stop signal sent.", "warning");
  });
}