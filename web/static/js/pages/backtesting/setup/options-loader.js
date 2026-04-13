/**
 * options-loader.js — Fetch strategies, timeframes, exchanges from backend
 * and populate the setup form selects.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import { setState } from "../../../core/state.js";

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
      setState("backtest.availableStrategies", Array.isArray(strategies) ? [...strategies] : []);
    }

    if (timeframeSelect) {
      timeframeSelect.innerHTML = '<option value="">Select timeframe…</option>';
      timeframes.forEach(tf => {
        const opt = document.createElement("option");
        opt.value = tf; opt.textContent = tf;
        timeframeSelect.appendChild(opt);
      });
    }

    const settings = await api.settings.get();
    if (settings.default_timerange) {
      const [start, end] = settings.default_timerange.split("-");
      const startDate = start ? `${start.slice(0,4)}-${start.slice(4,6)}-${start.slice(6,8)}` : "";
      const endDate = end ? `${end.slice(0,4)}-${end.slice(4,6)}-${end.slice(6,8)}` : "";
      setState("backtest.startDate", startDate);
      setState("backtest.endDate", endDate);
    }
    if (settings.default_dry_run_wallet !== undefined) {
      setState("backtest.dry_run_wallet", settings.default_dry_run_wallet);
    }
    if (settings.default_max_open_trades !== undefined) {
      setState("backtest.maxOpenTrades", settings.default_max_open_trades);
    }
  } catch (e) {
    showToast("Failed to load options: " + e.message, "error");
  }
}
