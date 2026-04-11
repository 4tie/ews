/**
 * run-controller.js — Handle backtest run execution and status updates.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import { getFormValues } from "../../../components/form-helpers.js";
import { setState, getState } from "../../../core/state.js";
import { emit, EVENTS } from "../../../core/events.js";

const runBtn = document.getElementById("btn-run-backtest");
const stopBtn = document.getElementById("btn-stop-backtest");
const statusLabel = document.getElementById("run-status-label");
const statusDot = document.getElementById("run-status-dot");

let currentRunId = null;

export function initRunController() {
  runBtn?.addEventListener("click", onRunBacktest);
  stopBtn?.addEventListener("click", onStopBacktest);
}

async function onRunBacktest() {
  const formData = getFormValues(document.querySelector(".panel--setup"));
  
  // Validate required fields
  if (!formData.strategy) {
    showToast("Please select a strategy", "warning");
    return;
  }
  
  if (!formData.timeframe) {
    showToast("Please select a timeframe", "warning");
    return;
  }
  
  const pairs = getState("backtest.pairs") || [];
  if (!pairs.length) {
    showToast("Please add at least one pair", "warning");
    return;
  }
  
  // Build request
  const payload = {
    strategy: formData.strategy,
    timeframe: formData.timeframe,
    exchange: formData.exchange || "binance",
    pairs: pairs,
    max_open_trades: parseInt(formData.max_open_trades) || 3,
    dry_run_wallet: parseFloat(formData.dry_run_wallet) || 1000,
    timerange: formData.start_date && formData.end_date 
      ? `${formatDateToYYYYMMDD(formData.start_date)}-${formatDateToYYYYMMDD(formData.end_date)}`
      : null,
    trigger_source: "ui",
  };
  
  // Disable run button, enable stop button
  runBtn.disabled = true;
  stopBtn.disabled = false;
  
  updateStatus("running", "Running...");
  
  try {
    const response = await api.backtest.run(payload);
    currentRunId = response.run_id;
    
    showToast(`Backtest started: ${currentRunId}`, "success");
    emit(EVENTS.BACKTEST_STARTED, { run_id: currentRunId });
    
    // Start streaming logs
    streamLogs(currentRunId);
    
  } catch (error) {
    showToast("Failed to start backtest: " + error.message, "error");
    runBtn.disabled = false;
    stopBtn.disabled = true;
    updateStatus("idle", "Ready");
  }
}

function onStopBacktest() {
  if (!currentRunId) return;
  
  showToast("Stop requested (not yet implemented)", "info");
  // TODO: Implement stop endpoint
}

function updateStatus(status, label) {
  setState("backtest.isRunning", status === "running");
  
  if (statusDot) {
    statusDot.className = `status-dot status-dot--${status}`;
  }
  
  if (statusLabel) {
    statusLabel.textContent = label;
  }
}

async function streamLogs(runId) {
  try {
    const eventSource = new EventSource(`/api/backtest/runs/${runId}/logs/stream`);
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const line = data.line || "";
      
      // Emit log line event
      emit("backtest:log", { line, runId });
      
      // Check for completion
      if (line.includes("[done]")) {
        eventSource.close();
        onBacktestComplete(runId, data);
      }
    };
    
    eventSource.onerror = (error) => {
      console.error("Log stream error:", error);
      eventSource.close();
      showToast("Log stream disconnected", "warning");
      runBtn.disabled = false;
      stopBtn.disabled = true;
      updateStatus("idle", "Ready");
    };
    
  } catch (error) {
    showToast("Failed to stream logs: " + error.message, "error");
    runBtn.disabled = false;
    stopBtn.disabled = true;
    updateStatus("idle", "Ready");
  }
}

function onBacktestComplete(runId, finalData) {
  const status = finalData.status || "unknown";
  const exitCode = finalData.exit_code;
  const error = finalData.error;
  
  runBtn.disabled = false;
  stopBtn.disabled = true;
  
  if (status === "completed" && exitCode === 0) {
    updateStatus("completed", "Completed");
    showToast("Backtest completed successfully", "success");
    emit(EVENTS.BACKTEST_COMPLETE, { run_id: runId });
  } else {
    updateStatus("failed", "Failed");
    showToast(`Backtest failed: ${error || "Unknown error"}`, "error");
    emit(EVENTS.BACKTEST_FAILED, { run_id: runId, error });
  }
  
  currentRunId = null;
}

function formatDateToYYYYMMDD(dateStr) {
  // Handle MM/DD/YYYY format
  if (dateStr.includes("/")) {
    const [month, day, year] = dateStr.split("/");
    return `${year}${month.padStart(2, "0")}${day.padStart(2, "0")}`;
  }
  // Handle YYYY-MM-DD format
  if (dateStr.includes("-")) {
    const [year, month, day] = dateStr.split("-");
    return `${year}${month}${day}`;
  }
  return dateStr;
}
