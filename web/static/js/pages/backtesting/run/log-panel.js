/**
 * log-panel.js — Manages the backtesting live log viewer.
 */

import { appendLogLine, clearLog } from "../../shared/backtest/log_renderer.js";

const viewer   = document.getElementById("log-viewer");
const clearBtn = document.getElementById("btn-clear-log");

export function initLogPanel() {
  clearBtn?.addEventListener("click", () => clearLog(viewer));
}

export function appendLine(line) {
  appendLogLine(viewer, line);
}
