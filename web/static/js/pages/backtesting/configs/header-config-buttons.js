/**
 * header-config-buttons.js — Load Config / Save Config buttons in the setup panel header.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import { openModal, closeModal } from "../../../components/modal.js";
import { emit, EVENTS } from "../../../core/events.js";
import { getFormValues, populateForm } from "../../../components/form-helpers.js";
import { getState, setState } from "../../../core/state.js";
import { setPairsFromArray } from "../../../components/pair-input.js";

export const SETUP_FORM_SELECTOR = ".panel--setup";

export function initHeaderConfigButtons() {
  document.getElementById("btn-save-config")?.addEventListener("click", onSaveConfig);
  document.getElementById("btn-load-config")?.addEventListener("click", onLoadConfig);
}

export function collectCurrentConfigData() {
  const formData = getFormValues(document.querySelector(SETUP_FORM_SELECTOR));
  formData.pairs = getState("backtest.pairs") ?? [];
  return formData;
}

async function onSaveConfig() {
  const name = prompt("Save config as:");
  if (!name?.trim()) return;

  try {
    await api.backtest.saveConfig({ name: name.trim(), data: collectCurrentConfigData() });
    showToast(`Config "${name.trim()}" saved.`, "success");
  } catch (e) {
    showToast("Save failed: " + e.message, "error");
  }
}

async function onLoadConfig() {
  let configs;
  try {
    ({ configs } = await api.backtest.listConfigs());
  } catch (e) {
    showToast("Failed to load configs: " + e.message, "error");
    return;
  }

  if (!configs.length) {
    showToast("No saved configs.", "info");
    return;
  }

  const listHtml = configs.map((name) =>
    `<button class="btn btn--ghost btn--sm config-pick-btn" data-name="${name}" style="display:block;width:100%;text-align:left;margin-bottom:4px">${name}</button>`
  ).join("");

  openModal({
    title: "Load Config",
    body: `<div id="config-pick-list">${listHtml}</div>`,
    footer: `<button class="btn btn--ghost btn--sm" id="modal-cancel-btn">Cancel</button>`,
  });

  document.getElementById("modal-cancel-btn")?.addEventListener("click", closeModal);

  document.getElementById("config-pick-list")?.addEventListener("click", async (e) => {
    const name = e.target.dataset.name;
    if (!name) return;

    closeModal();

    try {
      await applyConfig(name);
      showToast(`Config "${name}" loaded.`, "success");
    } catch (err) {
      showToast("Load failed: " + err.message, "error");
    }
  });
}

function parseNumber(value) {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

function syncConfigState(data) {
  setState("backtest.strategy", data.strategy ?? "");
  setState("backtest.timeframe", data.timeframe ?? "");
  setState("backtest.exchange", data.exchange ?? "binance");
  setState("backtest.startDate", data.start_date ?? "");
  setState("backtest.endDate", data.end_date ?? "");
  setState("backtest.dry_run_wallet", parseNumber(data.dry_run_wallet));
  setState("backtest.maxOpenTrades", parseNumber(data.max_open_trades));
}

export async function applyConfig(name) {
  const { data } = await api.backtest.loadConfig(name);

  if (!data) {
    throw new Error(`Config "${name}" is empty.`);
  }

  populateForm(document.querySelector(SETUP_FORM_SELECTOR), data);
  syncConfigState(data);

  if (Array.isArray(data.pairs)) {
    setPairsFromArray(data.pairs);
  }

  emit(EVENTS.CONFIG_LOADED, { name, data });
  return data;
}
