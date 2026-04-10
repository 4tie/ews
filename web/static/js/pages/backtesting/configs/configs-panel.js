/**
 * configs-panel.js — Manage saved backtest configs.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import { on, EVENTS } from "../../../core/events.js";
import { formatPct } from "../../../core/utils.js";
import { getLatestResultsPayload } from "../results/results-controller.js";
import { applyConfig, collectCurrentConfigData } from "./header-config-buttons.js";

const panelEl = document.getElementById("configs-panel");
const listEl = document.getElementById("configs-list");
const saveBtn = document.getElementById("btn-save-current-config");
let configActionsBound = false;
let resultsBound = false;
let saveBound = false;

export async function initConfigsPanel() {
  bindSaveAction();
  bindConfigActions();
  bindResultsContext();
  renderResultsContext(getLatestResultsPayload());
  await loadConfigs();
}

function bindSaveAction() {
  if (saveBound || !saveBtn) return;

  saveBtn.addEventListener("click", async () => {
    const name = prompt("Config name:");
    if (!name?.trim()) return;

    try {
      await api.backtest.saveConfig({ name: name.trim(), data: collectCurrentConfigData() });
      showToast(`Config "${name.trim()}" saved.`, "success");
      await loadConfigs();
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
    }
  });

  saveBound = true;
}

async function loadConfigs() {
  if (!listEl) return;

  try {
    const { configs } = await api.backtest.listConfigs();
    if (!configs.length) {
      listEl.innerHTML = '<div class="info-empty">No saved configs.</div>';
      return;
    }

    listEl.innerHTML = "";
    configs.forEach((name) => {
      const item = document.createElement("div");
      item.className = "config-item";
      item.innerHTML = `
        <span class="config-item__name">${name}</span>
        <div class="config-item__actions">
          <button class="btn btn--ghost btn--sm" data-load="${name}">Load</button>
          <button class="btn btn--ghost btn--sm btn--danger" data-delete="${name}">Delete</button>
        </div>
      `;
      listEl.appendChild(item);
    });
  } catch (e) {
    showToast("Failed to load configs: " + e.message, "error");
  }
}

function bindConfigActions() {
  if (configActionsBound || !listEl) return;

  listEl.addEventListener("click", async (e) => {
    const target = e.target.closest("[data-load], [data-delete]");
    if (!target) return;

    const loadName = target.dataset.load;
    const deleteName = target.dataset.delete;

    if (loadName) {
      try {
        await applyConfig(loadName);
        showToast(`Config "${loadName}" loaded.`, "success");
      } catch (err) {
        showToast("Load failed: " + err.message, "error");
      }
      return;
    }

    if (deleteName && confirm(`Delete config "${deleteName}"?`)) {
      try {
        await api.backtest.deleteConfig(deleteName);
        showToast(`Config "${deleteName}" deleted.`, "warning");
        await loadConfigs();
      } catch (err) {
        showToast("Delete failed: " + err.message, "error");
      }
    }
  });

  configActionsBound = true;
}

function bindResultsContext() {
  if (resultsBound) return;
  on(EVENTS.RESULTS_LOADED, renderResultsContext);
  resultsBound = true;
}

function ensureResultsContext() {
  if (!panelEl) return null;

  let context = document.getElementById("configs-result-context");
  if (!context) {
    context = document.createElement("div");
    context.id = "configs-result-context";
    context.className = "results-context results-context--empty";
    if (listEl) {
      listEl.insertAdjacentElement("beforebegin", context);
    } else {
      panelEl.appendChild(context);
    }
  }

  return context;
}

function findTotalRow(rows) {
  if (!Array.isArray(rows)) return null;
  return rows.find((row) => String(row?.key ?? row?.pair ?? "") === "TOTAL") ?? null;
}

function getProfitPct(totalRow) {
  const direct = Number(totalRow?.profit_total_pct);
  if (Number.isFinite(direct)) return direct;

  const ratio = Number(totalRow?.profit_total);
  if (Number.isFinite(ratio)) return ratio * 100;

  return null;
}

function renderResultsContext(payload) {
  const context = ensureResultsContext();
  if (!context) return;

  if (!payload?.summary) {
    context.className = "results-context results-context--empty";
    context.innerHTML = `
      <div class="results-context__title">Latest result context</div>
      <div class="results-context__note">
        No latest result is loaded yet. Saved config management is available now, but exact result-to-config linkage still needs backend support.
      </div>
    `;
    return;
  }

  const totalRow = findTotalRow(payload.results_per_pair);
  const profitPct = getProfitPct(totalRow);
  const profitLabel = profitPct == null ? "—" : formatPct(profitPct);
  const trades = Number(totalRow?.trades ?? payload?.trades?.length ?? 0) || 0;
  const strategy = payload?.strategy || "No strategy";
  const classSuffix = profitPct > 0 ? " results-context--positive" : profitPct < 0 ? " results-context--negative" : "";

  context.className = `results-context${classSuffix}`;
  context.innerHTML = `
    <div class="results-context__title">Latest result context</div>
    <div class="results-context__meta">
      <span><strong>Strategy:</strong> ${strategy}</span>
      <span><strong>Profit:</strong> ${profitLabel}</span>
      <span><strong>Trades:</strong> ${trades}</span>
    </div>
    <div class="results-context__note">
      This tab now stays in sync with the latest loaded result. Exact config identity for that result still needs backend support.
    </div>
  `;
}
