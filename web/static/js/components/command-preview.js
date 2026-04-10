/**
 * command-preview.js — Live command preview panel that rebuilds as form fields change.
 */

import { $, copyToClipboard } from "../core/utils.js";
import { getState } from "../core/state.js";
import { on, EVENTS } from "../core/events.js";

const previewEl = $("#command-preview-output");
const copyBtn   = $("#btn-copy-command");

let configPath = "/path/to/config.json";

async function fetchConfigPath() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    if (data?.config_path) {
      configPath = data.config_path;
    }
  } catch (e) {
    console.warn("Failed to fetch config path:", e);
  }
}

function buildCommandPreview() {
  const strategy      = getState("backtest.strategy");
  const timeframe    = getState("backtest.timeframe");
  const pairs         = getState("backtest.pairs") || [];
  const startDate     = getState("backtest.startDate");
  const endDate       = getState("backtest.endDate");
  const exchange      = getState("backtest.exchange") || "binance";
  const dryRunWallet  = getState("backtest.dry_run_wallet");
  const maxOpenTrades = getState("backtest.max_open_trades");

  if (!strategy) {
    return "# Select a strategy to preview the command";
  }

  const timerange = (startDate && endDate)
    ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
    : "";

  const runId = "<run_id>";
  const exportPath = `user_data/backtest_results\\${strategy}\\${runId}.backtest.zip`;

  let cmd = `freqtrade backtesting --strategy ${strategy} --config ${configPath}`;
  if (timeframe)   cmd += ` --timeframe ${timeframe}`;
  if (timerange)   cmd += ` --timerange ${timerange}`;
  if (pairs.length) cmd += ` --pairs ${pairs.join(" ")}`;
  if (dryRunWallet) cmd += ` --dry-run-wallet ${dryRunWallet}`;
  if (maxOpenTrades) cmd += ` --max-open-trades ${maxOpenTrades}`;
  cmd += ` --export trades --export-filename ${exportPath}`;
  return cmd;
}

function refresh() {
  if (!previewEl) return;
  previewEl.textContent = buildCommandPreview();
}

// Re-render when state changes
["backtest.strategy", "backtest.timeframe", "backtest.pairs", "backtest.startDate", "backtest.endDate", "backtest.exchange", "backtest.dry_run_wallet", "backtest.max_open_trades"]
  .forEach(path => {
    import("../core/state.js").then(({ on: stateOn }) => stateOn(path, refresh));
  });

copyBtn?.addEventListener("click", () => {
  copyToClipboard(previewEl?.textContent || "");
  copyBtn.textContent = "Copied!";
  setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
});

document.addEventListener("DOMContentLoaded", () => {
  fetchConfigPath();
  refresh();
});
