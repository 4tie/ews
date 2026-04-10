/**
 * live-log-stream.js — Connects to SSE log stream for a running optimizer run.
 */

import { appendLogLine, clearLog } from "../shared/backtest/log_renderer.js";

const viewer   = document.getElementById("opt-log-viewer");
const clearBtn = document.getElementById("btn-clear-opt-log");

let _source = null;

export function startLogStream(runId) {
  stopLogStream();
  if (!viewer) return;

  _source = new EventSource(`/api/optimizer/runs/${runId}/logs/stream`);
  _source.onmessage = (e) => {
    try {
      const { line } = JSON.parse(e.data);
      appendLogLine(viewer, line);
    } catch {
      appendLogLine(viewer, e.data);
    }
  };
  _source.onerror = () => {
    appendLogLine(viewer, "[stream] Connection closed.");
    stopLogStream();
  };
}

export function stopLogStream() {
  if (_source) { _source.close(); _source = null; }
}

export function initLogStream() {
  clearBtn?.addEventListener("click", () => clearLog(viewer));
}
