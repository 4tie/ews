/**
 * table.js — Render trades table from backtest results.
 */

import api from "../../../core/api.js";
import { on, EVENTS } from "../../../core/events.js";
import showToast from "../../../components/toast.js";

const tradesWrapper = document.getElementById("trades-table-wrapper");

export function initTradesTable() {
  on(EVENTS.BACKTEST_COMPLETE, onBacktestComplete);
}

async function onBacktestComplete(data) {
  const runId = data.run_id;
  if (!runId) return;
  
  try {
    // Load run details
    const response = await api.get(`/api/backtest/runs/${runId}`);
    const run = response.run;
    
    if (!run.summary_available) {
      if (tradesWrapper) {
        tradesWrapper.innerHTML = '<div class="info-empty">Summary not yet available.</div>';
      }
      return;
    }
    
    // Load trades
    const tradesResponse = await api.backtest.trades(run.strategy);
    const trades = tradesResponse.trades || [];
    
    renderTradesTable(trades);
    
  } catch (error) {
    showToast("Failed to load trades: " + error.message, "error");
  }
}

function renderTradesTable(trades) {
  if (!tradesWrapper) return;
  
  if (!trades || trades.length === 0) {
    tradesWrapper.innerHTML = '<div class="info-empty">No trades found.</div>';
    return;
  }
  
  const table = document.createElement("table");
  table.className = "trades-table";
  
  // Header
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  
  const headers = ["Pair", "Open Date", "Close Date", "Profit %", "Profit Abs", "Trade Duration"];
  headers.forEach(header => {
    const th = document.createElement("th");
    th.textContent = header;
    headerRow.appendChild(th);
  });
  
  thead.appendChild(headerRow);
  table.appendChild(thead);
  
  // Body
  const tbody = document.createElement("tbody");
  
  trades.forEach(trade => {
    const row = document.createElement("tr");
    
    const pair = trade.pair || "";
    const openDate = formatDate(trade.open_date);
    const closeDate = formatDate(trade.close_date);
    const profitPct = formatNumber(trade.profit_ratio ? trade.profit_ratio * 100 : 0, 2);
    const profitAbs = formatNumber(trade.profit_abs || 0, 8);
    const duration = formatDuration(trade.trade_duration);
    
    const cells = [pair, openDate, closeDate, profitPct + "%", profitAbs, duration];
    
    cells.forEach((cell, idx) => {
      const td = document.createElement("td");
      td.textContent = cell;
      
      // Color code profit column
      if (idx === 3) {
        const profit = parseFloat(profitPct);
        if (profit > 0) {
          td.className = "profit-positive";
        } else if (profit < 0) {
          td.className = "profit-negative";
        }
      }
      
      row.appendChild(td);
    });
    
    tbody.appendChild(row);
  });
  
  table.appendChild(tbody);
  tradesWrapper.innerHTML = "";
  tradesWrapper.appendChild(table);
}

function formatDate(dateStr) {
  if (!dateStr) return "-";
  try {
    const date = new Date(dateStr);
    return date.toLocaleString();
  } catch {
    return dateStr;
  }
}

function formatNumber(num, decimals = 2) {
  if (num === null || num === undefined) return "-";
  return parseFloat(num).toFixed(decimals);
}

function formatDuration(minutes) {
  if (!minutes) return "-";
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours > 0) {
    return `${hours}h ${mins}m`;
  }
  return `${mins}m`;
}
