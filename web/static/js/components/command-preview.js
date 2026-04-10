/**
 * command-preview.js - Live command preview panel.
 *
 * The preview stays reactive while the user edits the form, and launch actions
 * force a final refresh immediately before the request is sent.
 */

import { $, copyToClipboard } from "../core/utils.js";
import { getState, on as onState } from "../core/state.js";

const previewEl = $("#command-preview-output");
const copyBtn = $("#btn-copy-command");

let configPath = "/path/to/config.json";
let configPathPromise = null;
let activePreviewMode = "backtest";

function buildTimerange(startDate, endDate) {
  return startDate && endDate
    ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
    : "";
}

function getPreviewState(overrides = {}) {
  return {
    strategy: getState("backtest.strategy") || "",
    timeframe: getState("backtest.timeframe") || "",
    pairs: getState("backtest.pairs") || [],
    startDate: getState("backtest.startDate") || "",
    endDate: getState("backtest.endDate") || "",
    dryRunWallet: getState("backtest.dry_run_wallet") || "",
    maxOpenTrades: getState("backtest.maxOpenTrades") || "",
    ...overrides,
  };
}

async function ensureConfigPath() {
  if (!configPathPromise) {
    configPathPromise = (async () => {
      try {
        const res = await fetch("/api/settings");
        const data = await res.json();
        if (data?.config_path) {
          configPath = data.config_path;
        }
      } catch (e) {
        console.warn("Failed to fetch config path:", e);
      }
      return configPath;
    })();
  }

  return configPathPromise;
}

function buildBacktestCommand(state) {
  if (!state.strategy) {
    return "# Select a strategy to preview the command";
  }

  const timerange = buildTimerange(state.startDate, state.endDate);
  const runId = "<run_id>";
  const backtestDir = `user_data/backtest_results\\${state.strategy}`;

  let cmd = `freqtrade backtesting --strategy ${state.strategy} --config ${configPath}`;
  if (state.timeframe) cmd += ` --timeframe ${state.timeframe}`;
  if (timerange) cmd += ` --timerange ${timerange}`;
  if (state.pairs.length) cmd += ` --pairs ${state.pairs.join(" ")}`;
  if (state.dryRunWallet) cmd += ` --dry-run-wallet ${state.dryRunWallet}`;
  if (state.maxOpenTrades) cmd += ` --max-open-trades ${state.maxOpenTrades}`;
  cmd += ` --export trades --backtest-directory ${backtestDir} --notes ${runId} --cache none`;
  return cmd;
}

function buildDownloadCommand(state) {
  if (!state.timeframe) {
    return "# Select a timeframe to preview the download command";
  }
  if (!state.pairs.length) {
    return "# Add at least one pair to preview the download command";
  }

  const timerange = buildTimerange(state.startDate, state.endDate);

  let cmd = `freqtrade download-data --config ${configPath} --pairs ${state.pairs.join(" ")}`;
  cmd += ` --timeframes ${state.timeframe}`;
  if (timerange) cmd += ` --timerange ${timerange}`;
  cmd += " --prepend";
  return cmd;
}

function buildCommandPreview(mode = activePreviewMode, overrides = {}) {
  const state = getPreviewState(overrides);
  return mode === "download"
    ? buildDownloadCommand(state)
    : buildBacktestCommand(state);
}

function renderPreview(commandText) {
  if (!previewEl) return "";
  previewEl.textContent = commandText;
  return commandText;
}

function refresh(mode = activePreviewMode, overrides = {}) {
  activePreviewMode = mode;
  return renderPreview(buildCommandPreview(activePreviewMode, overrides));
}

async function refreshWithConfig(mode = activePreviewMode, overrides = {}) {
  await ensureConfigPath();
  return refresh(mode, overrides);
}

export async function refreshBacktestPreview(overrides = {}) {
  return refreshWithConfig("backtest", overrides);
}

export async function refreshDownloadPreview(overrides = {}) {
  return refreshWithConfig("download", overrides);
}

["backtest.strategy", "backtest.timeframe", "backtest.pairs", "backtest.startDate", "backtest.endDate", "backtest.dry_run_wallet", "backtest.maxOpenTrades"]
  .forEach((path) => onState(path, () => refresh(activePreviewMode)));

copyBtn?.addEventListener("click", () => {
  copyToClipboard(previewEl?.textContent || "");
  copyBtn.textContent = "Copied!";
  setTimeout(() => {
    copyBtn.textContent = "Copy";
  }, 1500);
});

document.addEventListener("DOMContentLoaded", () => {
  refreshBacktestPreview();
});
