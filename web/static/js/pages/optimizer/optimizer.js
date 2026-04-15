/**
 * optimizer.js — Start/stop controls and run orchestration.
 */

import api from "../../core/api.js";
import { getOptimizerPayload } from "./run-form.js";
import { startLogStream, stopLogStream } from "./live-log-stream.js";
import { loadCheckpoints } from "./checkpoint-panel.js";
import { setState } from "../../core/state.js";
import { emit, EVENTS } from "../../core/events.js";
import showToast from "../../components/toast.js";
import { setButtonLoading } from "../../components/loading-state.js";

const startBtn = document.getElementById("btn-start-optimizer");
const stopBtn  = document.getElementById("btn-stop-optimizer");
const pauseBtn = document.getElementById("btn-pause-optimizer");

let _currentRunId = null;

export function initOptimizer() {
  startBtn?.addEventListener("click", async () => {
    const payload = getOptimizerPayload();
    if (!payload.strategy) { showToast("Select a strategy.", "warning"); return; }
    if (!payload.timeframe){ showToast("Select a timeframe.", "warning"); return; }

    setButtonLoading(startBtn, true, "Starting…");
    if (stopBtn)  stopBtn.disabled  = false;
    if (pauseBtn) pauseBtn.disabled = false;

    try {
      const res = await api.optimizer.startRun(payload);
      _currentRunId = res.run_id;
      setState("optimizer.runId", _currentRunId);
      setState("optimizer.isRunning", true);
      emit(EVENTS.OPTIMIZER_STARTED, { runId: _currentRunId });
      startLogStream(_currentRunId);
      showToast("Optimizer started: " + _currentRunId, "info");
    } catch (e) {
      showToast("Failed to start optimizer: " + e.message, "error");
      setButtonLoading(startBtn, false);
      if (stopBtn)  stopBtn.disabled  = true;
      if (pauseBtn) pauseBtn.disabled = true;
    }
  });

  stopBtn?.addEventListener("click", async () => {
    if (!_currentRunId) return;
    if (stopBtn) stopBtn.disabled = true;

    try {
      await api.optimizer.stopRun(_currentRunId);
      stopLogStream();
      setState("optimizer.isRunning", false);
      emit(EVENTS.OPTIMIZER_STOPPED);
      setButtonLoading(startBtn, false);
      if (stopBtn)  stopBtn.disabled  = true;
      if (pauseBtn) pauseBtn.disabled = true;
      showToast("Optimizer stopped.", "warning");
    } catch (e) {
      if (stopBtn) stopBtn.disabled = false;
      showToast("Failed to stop optimizer: " + e.message, "error");
    }
  });
}
