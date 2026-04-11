/**
 * log-panel.js - Manages the backtesting live log viewer.
 */

import { appendLogLine, clearLog } from "../../shared/backtest/log_renderer.js";

const viewer = document.getElementById("log-viewer");
const clearBtn = document.getElementById("btn-clear-log");
const logPanel = document.getElementById("log-panel");

let _source = null;
let _listenerAbortController = null;
const MAX_LINES = 2000;

function trimViewer() {
  if (!viewer) return;
  const extra = viewer.childElementCount - MAX_LINES;
  if (extra <= 0) return;
  for (let i = 0; i < extra; i += 1) {
    if (!viewer.firstElementChild) break;
    viewer.removeChild(viewer.firstElementChild);
  }
}

function clearPanelAttention() {
  logPanel?.classList.remove("panel--attention");
}

function focusErrorState() {
  if (viewer) {
    viewer.scrollTop = viewer.scrollHeight;
  }
  logPanel?.classList.add("panel--attention");
  logPanel?.scrollIntoView({ block: "start", behavior: "smooth" });
}

export function startStream(url, { onDone, onProgress, onDisconnect, resetViewer = true } = {}) {
  stopStream();
  if (!viewer) return;

  clearPanelAttention();
  if (resetViewer) {
    clearLog(viewer);
  }

  _source = new EventSource(url);
  _source.onmessage = (event) => {
    let payload = null;
    try {
      payload = JSON.parse(event.data);
    } catch {
      payload = null;
    }

    const line = payload?.line;
    if (line != null) {
      appendLogLine(viewer, line);
      trimViewer();
    }

    if (payload?.progress) {
      onProgress?.(payload.progress, payload);
    }

    if (payload?.status) {
      if (payload.status === "failed" || payload.status === "stopped") {
        focusErrorState();
      } else {
        clearPanelAttention();
      }
      onDone?.(payload.status, payload.exit_code, payload.error, payload.progress, payload);
      stopStream();
    }
  };

  _source.onerror = () => {
    appendLogLine(viewer, "[stream] Connection closed.");
    trimViewer();
    onDisconnect?.();
    stopStream();
  };
}

export function stopStream() {
  if (_source) {
    _source.close();
    _source = null;
  }
}

export function initLogPanel() {
  _listenerAbortController?.abort();
  _listenerAbortController = new AbortController();
  clearBtn?.addEventListener("click", () => clearLog(viewer), { signal: _listenerAbortController.signal });
  return () => _listenerAbortController?.abort();
}

export function appendLine(line) {
  appendLogLine(viewer, line);
  trimViewer();
}
