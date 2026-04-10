/**
 * log_renderer.js — Renders log lines into a .log-viewer element.
 * Shared between backtesting and optimizer pages.
 */

/**
 * Append a log line to a viewer element with color classification.
 * @param {HTMLElement} viewer
 * @param {string} line
 * @param {boolean} autoScroll
 */
export function appendLogLine(viewer, line, autoScroll = true) {
  if (!viewer) return;
  const div = document.createElement("div");
  div.className = "log-line " + classifyLine(line);
  div.textContent = line;
  viewer.appendChild(div);

  if (autoScroll && isScrolledToBottom(viewer)) {
    viewer.scrollTop = viewer.scrollHeight;
  }
}

/**
 * Render an array of log lines (replacing existing content).
 * @param {HTMLElement} viewer
 * @param {string[]} lines
 */
export function renderLogLines(viewer, lines) {
  if (!viewer) return;
  viewer.innerHTML = "";
  lines.forEach(line => appendLogLine(viewer, line, false));
  viewer.scrollTop = viewer.scrollHeight;
}

/**
 * Clear a log viewer element.
 */
export function clearLog(viewer) {
  if (viewer) viewer.innerHTML = "";
}

function classifyLine(line) {
  const l = line.toLowerCase();
  if (l.includes("error") || l.includes("exception"))  return "log-line--error";
  if (l.includes("warn"))                               return "log-line--warn";
  if (l.includes("profit") || l.includes("completed")
    || l.includes("done") || l.includes("finished"))   return "log-line--ok";
  return "log-line--info";
}

function isScrolledToBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 40;
}
