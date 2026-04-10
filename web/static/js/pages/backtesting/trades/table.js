/**
 * table.js â€” Loads and renders the trades table.
 */

import api from "../../../core/api.js";
import { renderTradesTable } from "../../shared/backtest/result_renderer.js";
import { on, EVENTS } from "../../../core/events.js";
import { getState } from "../../../core/state.js";
import showToast from "../../../components/toast.js";

const wrapper = document.getElementById("trades-table-wrapper");

export function initTradesTable() {
  on(EVENTS.RESULTS_LOADED, async (data) => {
    if (Array.isArray(data?.trades)) {
      renderTradesTable(wrapper, data.trades);
      return;
    }

    const strategy = getState("backtest.strategy");
    if (!strategy) return;
    try {
      const { trades } = await api.backtest.trades(strategy);
      renderTradesTable(wrapper, trades);
    } catch (e) {
      showToast("Failed to load trades: " + e.message, "error");
    }
  });
}
