/**
 * pair-summary.js â€” Renders the per-pair results table.
 */

import { on, EVENTS } from "../../../core/events.js";
import { formatPct, el } from "../../../core/utils.js";

const wrapper = document.getElementById("pairs-summary-wrapper");

export function initPairSummary() {
  on(EVENTS.RESULTS_LOADED, (data) => {
    const pairs = data?.results_per_pair || [];
    renderPairSummary(wrapper, pairs);
  });
}

function renderPairSummary(container, pairs) {
  if (!container) return;
  if (!pairs.length) {
    container.innerHTML = '<div class="info-empty">No per-pair data.</div>';
    return;
  }
  const table = el("table", { class: "data-table" });
  table.innerHTML = `
    <thead><tr>
      <th>Pair</th><th>Profit %</th><th>Trades</th><th>Wins</th><th>Losses</th>
    </tr></thead>
  `;
  const tbody = el("tbody");
  pairs.forEach(p => {
    let pct = p?.profit_total_pct;
    if (pct == null) pct = (p?.profit_total ?? 0) * 100;
    pct = parseFloat(pct ?? 0);
    if (!Number.isFinite(pct)) pct = 0;

    const row = el("tr");
    row.innerHTML = `
      <td>${p.key ?? p.pair ?? "â€”"}</td>
      <td class="${pct >= 0 ? "positive" : "negative"}">${formatPct(pct)}</td>
      <td>${p.trades ?? "â€”"}</td>
      <td>${p.wins ?? "â€”"}</td>
      <td>${p.losses ?? "â€”"}</td>
    `;
    tbody.appendChild(row);
  });
  table.appendChild(tbody);
  container.innerHTML = "";
  container.appendChild(table);
}
