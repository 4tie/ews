/**
 * data-download.js — Handle data download requests.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import { getState } from "../../../core/state.js";

export function initDataDownload() {
  const downloadBtn = document.getElementById("btn-download-data");
  const downloadOutput = document.getElementById("data-download-output");
  
  downloadBtn?.addEventListener("click", async () => {
    const pairs = getState("backtest.pairs") || [];
    const timeframe = document.getElementById("select-timeframe")?.value;
    const exchange = document.getElementById("select-exchange")?.value || "binance";
    
    if (!pairs.length) {
      showToast("Please add pairs first", "warning");
      return;
    }
    
    if (!timeframe) {
      showToast("Please select a timeframe", "warning");
      return;
    }
    
    downloadBtn.disabled = true;
    if (downloadOutput) {
      downloadOutput.innerHTML = '<span class="muted">Downloading...</span>';
    }
    
    try {
      const response = await api.backtest.downloadData({
        pairs,
        timeframe,
        exchange,
      });
      
      showToast("Download started", "success");
      if (downloadOutput) {
        downloadOutput.innerHTML = `<span>Download ID: ${response.download_id}</span>`;
      }
      
      // Stream logs
      streamDownloadLogs(response.download_id, downloadOutput);
      
    } catch (error) {
      showToast("Download failed: " + error.message, "error");
      if (downloadOutput) {
        downloadOutput.innerHTML = `<span class="error">${error.message}</span>`;
      }
    } finally {
      downloadBtn.disabled = false;
    }
  });
}

async function streamDownloadLogs(downloadId, outputEl) {
  try {
    const eventSource = new EventSource(`/api/backtest/download-data/${downloadId}/logs/stream`);
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const line = data.line || "";
      
      if (outputEl) {
        outputEl.innerHTML = `<span>${line}</span>`;
      }
      
      if (line.includes("[done]")) {
        eventSource.close();
      }
    };
    
    eventSource.onerror = () => {
      eventSource.close();
    };
    
  } catch (error) {
    console.error("Download stream error:", error);
  }
}
