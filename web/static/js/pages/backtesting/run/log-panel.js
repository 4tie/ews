/**
 * log-panel.js — Consume and display SSE log stream.
 */

import { on, EVENTS } from "../../../core/events.js";

const logViewer = document.getElementById("log-viewer");
const clearBtn = document.getElementById("btn-clear-log");

export function initLogPanel() {
  clearBtn?.addEventListener("click", clearLogs);
  
  // Listen for log events
  on("backtest:log", onLogLine);
}

function onLogLine(data) {
  if (!data || !data.line) return;
  
  const line = data.line;
  
  // Create log entry
  const entry = document.createElement("div");
  entry.className = "log-entry";
  
  // Color code based on content
  if (line.includes("[error]") || line.includes("Error") || line.includes("FAILED")) {
    entry.className += " log-entry--error";
  } else if (line.includes("[warn]") || line.includes("Warning")) {
    entry.className += " log-entry--warning";
  } else if (line.includes("[done]") || line.includes("Completed")) {
    entry.className += " log-entry--success";
  } else if (line.includes("[stream]")) {
    entry.className += " log-entry--info";
  }
  
  entry.textContent = line;
  
  if (logViewer) {
    logViewer.appendChild(entry);
    // Auto-scroll to bottom
    logViewer.scrollTop = logViewer.scrollHeight;
  }
}

function clearLogs() {
  if (logViewer) {
    logViewer.innerHTML = "";
  }
}
