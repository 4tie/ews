/**
 * options-loader.js — Fetch strategies, timeframes, exchanges from backend
 * and populate the setup form selects.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";

export async function loadOptions() {
  const strategySelect  = document.getElementById("select-strategy");
  const timeframeSelect = document.getElementById("select-timeframe");
  if (!strategySelect && !timeframeSelect) return;

  try {
    const { strategies, timeframes } = await api.backtest.options();

    if (strategySelect) {
      strategySelect.innerHTML = '<option value="">Select strategy…</option>';
      strategies.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s; opt.textContent = s;
        strategySelect.appendChild(opt);
      });
    }

    if (timeframeSelect) {
      timeframeSelect.innerHTML = '<option value="">Select timeframe…</option>';
      timeframes.forEach(tf => {
        const opt = document.createElement("option");
        opt.value = tf; opt.textContent = tf;
        timeframeSelect.appendChild(opt);
      });
    }
  } catch (e) {
    showToast("Failed to load options: " + e.message, "error");
  }
}
