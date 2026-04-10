/**
 * command-preview.js — Live command preview panel that rebuilds as form fields change.
 */

import { $, copyToClipboard } from "../core/utils.js";
import { getState } from "../core/state.js";
import { on, EVENTS } from "../core/events.js";

const previewEl = $("#command-preview-output");
const copyBtn   = $("#btn-copy-command");

function buildCommandPreview() {
  const strategy  = getState("backtest.strategy");
  const timeframe = getState("backtest.timeframe");
  const pairs     = getState("backtest.pairs") || [];
  const startDate = getState("backtest.startDate");
  const endDate   = getState("backtest.endDate");
  const exchange  = getState("backtest.exchange") || "binance";

  if (!strategy) {
    return "# Select a strategy to preview the command";
  }

  const timerange = (startDate && endDate)
    ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
    : "";

  let cmd = `freqtrade backtesting \\\n  --strategy ${strategy} \\\n  --config /path/to/config.json`;
  if (timeframe) cmd += ` \\\n  --timeframe ${timeframe}`;
  if (timerange)  cmd += ` \\\n  --timerange ${timerange}`;
  if (pairs.length) cmd += ` \\\n  --pairs ${pairs.join(" ")}`;
  return cmd;
}

function refresh() {
  if (!previewEl) return;
  previewEl.textContent = buildCommandPreview();
}

// Re-render when state changes
["backtest.strategy", "backtest.timeframe", "backtest.pairs", "backtest.startDate", "backtest.endDate", "backtest.exchange"]
  .forEach(path => {
    import("../core/state.js").then(({ on: stateOn }) => stateOn(path, refresh));
  });

copyBtn?.addEventListener("click", () => {
  copyToClipboard(previewEl?.textContent || "");
  copyBtn.textContent = "Copied!";
  setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
});

document.addEventListener("DOMContentLoaded", refresh);
