/**
 * data-download.js - Handles the data download button and status display.
 */

import api from "../../../core/api.js";
import { getState } from "../../../core/state.js";
import showToast from "../../../components/toast.js";
import { setButtonLoading } from "../../../components/loading-state.js";
import { refreshDownloadPreview } from "../../../components/command-preview.js";
import { startStream } from "./log-panel.js";

const downloadBtn = document.getElementById("btn-download-data");
const downloadOutput = document.getElementById("data-download-output");

export function initDataDownload() {
  downloadBtn?.addEventListener("click", async () => {
    const strategy = getState("backtest.strategy");
    const timeframe = getState("backtest.timeframe");
    const pairs = getState("backtest.pairs") || [];
    const startDate = getState("backtest.startDate");
    const endDate = getState("backtest.endDate");
    const timerange = startDate && endDate
      ? `${startDate.replace(/-/g, "")}-${endDate.replace(/-/g, "")}`
      : undefined;

    if (!pairs.length) {
      showToast("Add at least one pair before downloading data.", "warning");
      return;
    }

    const prepend = true;

    await refreshDownloadPreview({
      strategy,
      timeframe,
      pairs,
      startDate,
      endDate,
      prepend,
    });

    setButtonLoading(downloadBtn, true, "Downloading...");
    if (downloadOutput) downloadOutput.textContent = "Starting download...";

    try {
      const res = await api.backtest.downloadData({ strategy, timeframe, pairs, timerange, prepend });
      if (res.error) throw new Error(res.error);

      const downloadId = res.download_id;
      if (downloadOutput) downloadOutput.textContent = `Download ${downloadId} - ${res.status}`;
      showToast(`Data download started: ${downloadId}`, "info");

      startStream(`/api/backtest/download-data/${downloadId}/logs/stream`, {
        onDone: (status, exitCode) => {
          const s = String(status || "");
          if (downloadOutput) {
            downloadOutput.textContent = `Download ${downloadId} - ${s} (exit ${exitCode ?? "?"})`;
          }

          if (s === "completed") {
            showToast("Data download completed.", "success");
          } else if (s === "failed") {
            showToast("Data download failed.", "error");
          } else {
            showToast(`Data download stream ended: ${s || "unknown"}`, "warning");
          }

          setButtonLoading(downloadBtn, false);
        },
      });
    } catch (e) {
      showToast("Download failed: " + e.message, "error");
      if (downloadOutput) downloadOutput.textContent = "Error: " + e.message;
      setButtonLoading(downloadBtn, false);
    }
  });
}
