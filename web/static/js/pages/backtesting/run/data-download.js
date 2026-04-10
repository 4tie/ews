/**
 * data-download.js — Handles the data download button and status display.
 */

import api from "../../../core/api.js";
import { getState } from "../../../core/state.js";
import showToast from "../../../components/toast.js";
import { setButtonLoading } from "../../../components/loading-state.js";

const downloadBtn    = document.getElementById("btn-download-data");
const downloadOutput = document.getElementById("data-download-output");

export function initDataDownload() {
  downloadBtn?.addEventListener("click", async () => {
    const strategy  = getState("backtest.strategy");
    const timeframe = getState("backtest.timeframe");
    const pairs     = getState("backtest.pairs") || [];
    const startDate = getState("backtest.startDate");
    const endDate   = getState("backtest.endDate");
    const timerange = (startDate && endDate)
      ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
      : undefined;

    if (!pairs.length) {
      showToast("Add at least one pair before downloading data.", "warning");
      return;
    }

    setButtonLoading(downloadBtn, true, "Downloading…");
    if (downloadOutput) downloadOutput.textContent = "Downloading data…";

    try {
      const res = await api.backtest.downloadData({ strategy, timeframe, pairs, timerange });
      if (downloadOutput) downloadOutput.textContent = `Status: ${res.status} — ${res.message || ""}`;
      showToast("Data download queued.", "info");
    } catch (e) {
      showToast("Download failed: " + e.message, "error");
      if (downloadOutput) downloadOutput.textContent = "Error: " + e.message;
    } finally {
      setButtonLoading(downloadBtn, false);
    }
  });
}
