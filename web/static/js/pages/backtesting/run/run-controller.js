/**
 * run-controller.js - Handles the Run / Stop backtest buttons and status.
 */

import api from "../../../core/api.js";
import persistence, { KEYS } from "../../../core/persistence.js";
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

const ACTIVE_RUN_KEY = KEYS.BACKTEST_ACTIVE_RUN;
const ACTIVE_STATUSES = new Set(["queued", "running"]);
const TERMINAL_STATUSES = new Set(["completed", "failed", "stopped"]);

let _currentRunId = null;
let _listenersController = null;
let _lastTerminalEvent = null;
let _currentRunMeta = { trigger_source: null, version_id: null, strategy: null };

function setStatus(state, label) {
  if (statusDot) statusDot.className = `status-dot status-dot--${state}`;
  if (statusLbl) statusLbl.textContent = label;
}

function setCurrentRunId(runId) {
  _currentRunId = runId || null;
  _lastTerminalEvent = null;
}

function setCurrentRunMeta(meta = null) {
  _currentRunMeta = {
    trigger_source: meta?.trigger_source || null,
    version_id: meta?.version_id || null,
    strategy: meta?.strategy || null,
  };
}

function currentRunEventMeta(status, exitCode, error) {
  return {
    run_id: _currentRunId,
    status,
    exit_code: exitCode,
    error,
    trigger_source: _currentRunMeta.trigger_source,
    version_id: _currentRunMeta.version_id,
    strategy: _currentRunMeta.strategy,
  };
}

function persistActiveRun(runId, strategy) {
  if (!runId) return;
  persistence.save(ACTIVE_RUN_KEY, { runId, strategy: strategy || "" });
}

function loadActiveRun() {
  return persistence.load(ACTIVE_RUN_KEY, null);
}

function clearActiveRun() {
  persistence.remove(ACTIVE_RUN_KEY);
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

function formatProgressLabel(progress, fallback = "Running...") {
  if (!progress || typeof progress !== "object") {
    return fallback;
  }

  const label = String(progress.label || fallback).trim() || fallback;
  const percent = Number(progress.percent);
  if (!Number.isFinite(percent)) {
    return label;
  }

  const normalized = Math.max(0, Math.min(100, Math.round(percent)));
  return `${label} (${normalized}%)`;
}

function syncRunningUi(progress = null, fallback = "Running...") {
  setButtonLoading(runBtn, true, "Running...");
  if (stopBtn) stopBtn.disabled = false;
  setState("backtest.isRunning", true);
  setStatus("running", formatProgressLabel(progress, fallback));
}

function resetRunUi() {
  if (stopBtn) stopBtn.disabled = true;
  setButtonLoading(runBtn, false);
  setState("backtest.isRunning", false);
}

function handleProgress(progress) {
  if (!getState("backtest.isRunning")) return;
  setStatus("running", formatProgressLabel(progress));
}

function finishRun(status, exitCode, error, progress) {
  const s = String(status || "");
  const terminalKey = _currentRunId ? `${_currentRunId}:${s}` : s;
  if (_lastTerminalEvent === terminalKey) {
    return;
  }
  if (TERMINAL_STATUSES.has(s)) {
    _lastTerminalEvent = terminalKey;
  }

  const failureMessage = formatBacktestFailure(error);
  if (s === "completed") {
    setStatus("done", `Completed (exit ${exitCode ?? 0})`);
    showToast("Backtest completed.", "success");
    emit(EVENTS.BACKTEST_COMPLETE, currentRunEventMeta(s, exitCode, error));
  } else if (s === "failed") {
    setStatus("error", exitCode != null ? `Failed (exit ${exitCode})` : "Failed");
    showToast(failureMessage ? `Backtest failed: ${failureMessage}` : "Backtest failed.", "error");
    emit(EVENTS.BACKTEST_FAILED, currentRunEventMeta(s, exitCode, failureMessage || error));
  } else if (s === "stopped") {
    setStatus("idle", "Stopped");
    showToast("Backtest stopped.", "warning");
    emit(EVENTS.BACKTEST_STOPPED, currentRunEventMeta(s, exitCode, error));
  } else {
    setStatus("idle", formatProgressLabel(progress, s || "Done"));
    emit(EVENTS.BACKTEST_COMPLETE, currentRunEventMeta(s, exitCode, error));
  }

  clearActiveRun();
  setCurrentRunMeta(null);
  resetRunUi();
}

function attachRunLogStream(runId, options = {}) {
  startStream(`/api/backtest/runs/${encodeURIComponent(runId)}/logs/stream`, {
    resetViewer: options.resetViewer !== false,
    onProgress: (progress) => handleProgress(progress),
    onDone: (status, exitCode, error, progress) => finishRun(status, exitCode, error, progress),
    onDisconnect: async () => {
      if (!getState("backtest.isRunning") || !_currentRunId || runId !== _currentRunId) {
        return;
      }

      setStatus("running", "Reconnecting...");
      try {
        const { run } = await api.backtest.getRun(runId);
        if (!run) {
          throw new Error("Run not found");
        }
        if (ACTIVE_STATUSES.has(run.status)) {
          handleProgress(run.progress);
          attachRunLogStream(runId, { resetViewer: true });
          return;
        }
        finishRun(run.status, run.exit_code, run.error, run.progress);
      } catch (error) {
        console.warn("[backtesting] Failed to reconnect log stream:", error);
        showToast("Log stream disconnected. Refresh to reattach if the run is still active.", "warning");
      }
    },
  });
}

async function restoreActiveRun() {
  const stored = loadActiveRun();
  if (!stored?.runId) {
    return null;
  }

  const currentStrategy = getState("backtest.strategy") || "";
  if (stored.strategy && currentStrategy && stored.strategy !== currentStrategy) {
    clearActiveRun();
    return null;
  }

  try {
    const { run } = await api.backtest.getRun(stored.runId);
    if (!run || !ACTIVE_STATUSES.has(run.status)) {
      clearActiveRun();
      return run || null;
    }

    setCurrentRunId(run.run_id || stored.runId);
    setCurrentRunMeta(run);
    persistActiveRun(_currentRunId, run.strategy || stored.strategy || currentStrategy);
    syncRunningUi(run.progress, run.status === "queued" ? "Queued" : "Running...");
    attachRunLogStream(_currentRunId, { resetViewer: true });
    showToast(`Reattached to backtest: ${_currentRunId}`, "info");
    return run;
  } catch (error) {
    console.warn("[backtesting] Failed to restore active run:", error);
    clearActiveRun();
    return null;
  }
}

export async function startBacktestRun(payload, options = {}) {
  if (getState("backtest.isRunning")) {
    const error = new Error("A backtest is already running.");
    showToast(error.message, "warning");
    throw error;
  }

  const previewContext = options.previewContext || null;
  if (previewContext) {
    await refreshBacktestPreview(previewContext);
  }

  syncRunningUi(null, "Running...");
  emit(EVENTS.BACKTEST_STARTED, payload);

  try {
    const res = await api.backtest.run(payload);
    setCurrentRunId(res.run_id);
    setCurrentRunMeta(payload);
    persistActiveRun(_currentRunId, payload.strategy);

    if (res.status === "failed" || res.error) {
      const message = formatBacktestFailure(res.error);
      stopStream();
      clearActiveRun();
      resetRunUi();
      setStatus("error", res.exit_code != null ? `Failed (exit ${res.exit_code})` : "Failed");
      emit(EVENTS.BACKTEST_FAILED, currentRunEventMeta(res.status || "failed", res.exit_code, message || res.error));
      throw new Error(message || res.error || "Backtest failed.");
    }

    showToast(`Backtest started: ${_currentRunId}`, "info");
    handleProgress(res.progress);
    attachRunLogStream(_currentRunId, { resetViewer: true });
    return res;
  } catch (error) {
    const message = formatBacktestFailure(error?.message || error);
    stopStream();
    clearActiveRun();
    showToast(message ? `Run failed: ${message}` : "Run failed.", "error");
    setStatus("error", "Failed");
    emit(EVENTS.BACKTEST_FAILED, currentRunEventMeta("failed", null, message || error?.message || String(error)));
    setCurrentRunMeta(null);
    resetRunUi();
    throw error;
  }
}

function buildFormPayload() {
  const strategy = getState("backtest.strategy");
  const timeframe = getState("backtest.timeframe");
  const startDate = getState("backtest.startDate");
  const endDate = getState("backtest.endDate");
  const timerange = startDate && endDate
    ? `${startDate.replaceAll("-", "")}-${endDate.replaceAll("-", "")}`
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

async function handleRunClick() {
  if (getState("backtest.isRunning")) {
    showToast("A backtest is already running.", "warning");
    return;
  }

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
  if (!payload.pairs.length) {
    showToast("Please add at least one pair.", "warning");
    return;
  }

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
  } catch {
    // startBacktestRun already updates UI and toasts.
  }
}

async function handleStopClick() {
  if (!getState("backtest.isRunning") || !_currentRunId) {
    return;
  }

  if (stopBtn) stopBtn.disabled = true;
  setStatus("running", "Stopping...");

  try {
    const response = await api.backtest.stopRun(_currentRunId);
    showToast("Stop signal sent.", "warning");
    const run = response?.run;
    if (run && TERMINAL_STATUSES.has(run.status)) {
      finishRun(run.status, run.exit_code, run.error, run.progress);
    }
  } catch (error) {
    if (stopBtn) stopBtn.disabled = false;
    handleProgress(null);
    showToast(`Failed to stop backtest: ${error?.message || error}`, "error");
  }
}

export function initRunController() {
  _listenersController?.abort();
  _listenersController = new AbortController();
  const signal = _listenersController.signal;

  runBtn?.addEventListener("click", handleRunClick, { signal });
  stopBtn?.addEventListener("click", handleStopClick, { signal });

  void restoreActiveRun();
  return () => _listenersController?.abort();
}
