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

function formatBacktestFailure(error) {
  const raw = String(error || "").trim();
  if (!raw) {
    return "";
  }

  let message = raw
    .replace(/^process_failed:\s*/, "")
    .replace(/^launch_failed:\s*/, "")
    .replace(/^exit_code=\d+\s*\|\s*/, "")
    .trim();

  if (message.includes("Use `freqtrade download-data`")) {
    return message.replace("Use `freqtrade download-data` to download the data", "Use Download Data first");
  }

  if (message.includes("No data found")) {
    return "No historical data matched this request. Use Download Data first.";
  }

  return message;
}

function finishRun(status, exitCode, error) {
  const s = String(status || "");
  const failureMessage = formatBacktestFailure(error);
  if (s === "completed") {
    setStatus("done", `Completed (exit ${exitCode ?? 0})`);
    showToast("Backtest completed.", "success");
    emit(EVENTS.BACKTEST_COMPLETE, { run_id: _currentRunId, status: s, exit_code: exitCode, error });
  } else if (s === "failed") {
    setStatus("error", exitCode != null ? `Failed (exit ${exitCode})` : "Failed");
    showToast(failureMessage ? `Backtest failed: ${failureMessage}` : "Backtest failed.", "error");
    emit(EVENTS.BACKTEST_FAILED, { run_id: _currentRunId, status: s, exit_code: exitCode, error: failureMessage || error });
  } else {
    setStatus("idle", s || "Done");
    emit(EVENTS.BACKTEST_COMPLETE, { run_id: _currentRunId, status: s, exit_code: exitCode, error });
  }

  if (stopBtn) stopBtn.disabled = true;
  setButtonLoading(runBtn, false);
  setState("backtest.isRunning", false);
}

export async function startBacktestRun(payload, options = {}) {
  const previewContext = options.previewContext || null;

  if (previewContext) {
    await refreshBacktestPreview(previewContext);
  }

  setButtonLoading(runBtn, true, "Running...");
  if (stopBtn) stopBtn.disabled = false;
  setStatus("running", "Running...");
  setState("backtest.isRunning", true);
  emit(EVENTS.BACKTEST_STARTED, payload);

  try {
    const res = await api.backtest.run(payload);
    _currentRunId = res.run_id;

    if (res.status === "failed" || res.error) {
      const message = formatBacktestFailure(res.error);
      stopStream();
      if (stopBtn) stopBtn.disabled = true;
      setButtonLoading(runBtn, false);
      setState("backtest.isRunning", false);
      setStatus("error", res.exit_code != null ? `Failed (exit ${res.exit_code})` : "Failed");
      emit(EVENTS.BACKTEST_FAILED, {
        run_id: _currentRunId,
        status: res.status || "failed",
        exit_code: res.exit_code,
        error: message || res.error,
      });
      throw new Error(message || res.error || "Backtest failed.");
    }

    showToast(`Backtest started: ${_currentRunId}`, "info");

    startStream(`/api/backtest/runs/${_currentRunId}/logs/stream`, {
      onDone: (status, exitCode, error) => finishRun(status, exitCode, error),
    });
    return res;
  } catch (error) {
    const message = formatBacktestFailure(error?.message || error);
    stopStream();
    showToast(message ? `Run failed: ${message}` : "Run failed.", "error");
    setStatus("error", "Failed");
    emit(EVENTS.BACKTEST_FAILED, {
      run_id: _currentRunId,
      status: "failed",
      error: message || error?.message || String(error),
    });
    if (stopBtn) stopBtn.disabled = true;
    setButtonLoading(runBtn, false);
    setState("backtest.isRunning", false);
    throw error;
  }
}

function buildFormPayload() {
  const strategy = getState("backtest.strategy");
  const timeframe = getState("backtest.timeframe");
  const startDate = getState("backtest.startDate");
  const endDate = getState("backtest.endDate");
  const timerange = startDate && endDate
    ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
    : undefined;

  return {
    strategy,
    timeframe,
    timerange,
    pairs: getState("backtest.pairs") || [],
    exchange: getState("backtest.exchange") || "binance",
    dry_run_wallet: getState("backtest.dry_run_wallet") || undefined,
    max_open_trades: getState("backtest.maxOpenTrades") || undefined,
  };
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

    const payload = buildFormPayload();
    const startDate = getState("backtest.startDate");
    const endDate = getState("backtest.endDate");

    try {
      await startBacktestRun(payload, {
        previewContext: {
          strategy: payload.strategy,
          timeframe: payload.timeframe,
          pairs: payload.pairs,
          startDate,
          endDate,
          dryRunWallet: payload.dry_run_wallet,
          maxOpenTrades: payload.max_open_trades,
        },
      });
    } catch (error) {
      // startBacktestRun already updates UI and toasts.
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
