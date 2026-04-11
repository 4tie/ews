/**
 * log-panel.js � Manages the backtesting live log viewer.
 */

import { appendLogLine, clearLog } from "../../shared/backtest/log_renderer.js";

const viewer   = document.getElementById("log-viewer");
const clearBtn = document.getElementById("btn-clear-log");

let _source = null;
const MAX_LINES = 2000;

function trimViewer() {
  if (!viewer) return;
  const extra = viewer.childElementCount - MAX_LINES;
  if (extra <= 0) return;
  for (let i = 0; i < extra; i++) {
    if (!viewer.firstElementChild) break;
    viewer.removeChild(viewer.firstElementChild);
  }
}

export function startStream(url, { onDone } = {}) {
  stopStream();
  if (!viewer) return;

  clearLog(viewer);

  _source = new EventSource(url);
  _source.onmessage = (e) => {
    let payload = null;
    try {
      payload = JSON.parse(e.data);
    } catch {
      payload = null;
    }

    const line = payload?.line ?? e.data;
    appendLogLine(viewer, line);
    trimViewer();

    if (payload?.status) {
      onDone?.(payload.status, payload.exit_code, payload.error);
      stopStream();
    }
  };

  _source.onerror = () => {
    appendLogLine(viewer, "[stream] Connection closed.");
    onDone?.("disconnected", null);
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
  clearBtn?.addEventListener("click", () => clearLog(viewer));
}

export function appendLine(line) {
  appendLogLine(viewer, line);
  trimViewer();
}
