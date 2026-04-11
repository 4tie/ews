/**
 * pair-summary.js — Render per-pair summary table.
 */

import api from "../../../core/api.js";
import { on, EVENTS } from "../../../core/events.js";

const pairsSummaryWrapper = document.getElementById("pairs-summary-wrapper");

export function initPairSummary() {
  on(EVENTS.BACKTEST_COMPLETE, onBacktestComplete);
}

async function onBacktestComplete(data) {
  const runId = data.run_id;
  if (!runId) return;
  
  try {
    const response = await api.get(`/api/backtest/runs/${runId}`);
    const run = response.run;
    
    if (!run.summary_available) {
      if (pairsSummaryWrapper) {
        pairsSummaryWrapper.innerHTML = '<div class="info-empty">Summary not yet available.</div>';
      }
      return;
    }
    
    // Load summary
    const summaryResponse = await api.backtest.summary(run.strategy);
    const summary = summaryResponse.summary;
    
    if (summary && summary[run.strategy]) {
      const resultsPerPair = summary[run.strategy].results_per_pair || [];
      renderPairSummary(resultsPerPair);
    }
    
  } catch (error) {
    console.error("Failed to load pair summary:", error);
  }
}

function renderPairSummary(results) {
  if (!pairsSummaryWrapper) return;
  
  if (!results || results.length === 0) {
    pairsSummaryWrapper.innerHTML = '<div class="info-empty">No pair summary available.</div>';
    return;
  }
  
  const table = document.createElement("table");
  table.className = "pair-summary-table";
  
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  
  const headers = ["Pair", "Trades", "Profit %", "Profit Abs", "Win Rate"];
  headers.forEach(header => {
    const th = document.createElement("th");
    th.textContent = header;
    headerRow.appendChild(th);
  });
  
  thead.appendChild(headerRow);
  table.appendChild(thead);
  
  const tbody = document.createElement("tbody");
  
  results.forEach(result => {
    if (result.key === "TOTAL") return; // Skip total row
    
    const row = document.createElement("tr");
    
    const pair = result.pair || result.key || "";
    const trades = result.trades || 0;
    const profitPct = result.profit_total_pct ? (result.profit_total_pct * 100).toFixed(2) : "0.00";
    const profitAbs = result.profit_total_abs ? result.profit_total_abs.toFixed(8) : "0";
    const winRate = result.winrate ? (result.winrate * 100).toFixed(2) : "0.00";
    
    const cells = [pair, trades, profitPct + "%", profitAbs, winRate + "%"];
    
    cells.forEach((cell, idx) => {
      const td = document.createElement("td");
      td.textContent = cell;
      
      if (idx === 2) {
        const profit = parseFloat(profitPct);
        if (profit > 0) td.className = "profit-positive";
        else if (profit < 0) td.className = "profit-negative";
      }
      
      row.appendChild(td);
    });
    
    tbody.appendChild(row);
  });
  
  table.appendChild(tbody);
  pairsSummaryWrapper.innerHTML = "";
  pairsSummaryWrapper.appendChild(table);
}
