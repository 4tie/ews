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
  const body = document.createElement("div");
  body.innerHTML = `
    <div class="form-group">
      <label class="form-label" for="header-config-name-input">Config Name</label>
      <input class="form-input" type="text" id="header-config-name-input" placeholder="Enter a name for this configuration" autofocus />
      <div class="field-hint">Save your current strategy, timeframe, pairs, and time range settings.</div>
    </div>
  `;

  const footer = `
    <button class="btn btn--secondary" id="modal-cancel">Cancel</button>
    <button class="btn btn--primary" id="modal-save">Save Config</button>
  `;

  openModal({
    title: "Save Configuration",
    body,
    footer,
    onClose: () => {
      document.getElementById("modal-cancel")?.removeEventListener("click", closeModal);
      document.getElementById("modal-save")?.removeEventListener("click", handleSave);
    }
  });

  const nameInput = document.getElementById("header-config-name-input");
  const cancelBtn = document.getElementById("modal-cancel");
  const saveBtn = document.getElementById("modal-save");

  cancelBtn?.addEventListener("click", closeModal);

  async function handleSave() {
    const name = nameInput?.value?.trim();
    if (!name) {
      showToast("Please enter a config name.", "error");
      return;
    }

    try {
      await api.backtest.saveConfig({ name, data: collectCurrentConfigData() });
      showToast(`Config "${name}" saved.`, "success");
      closeModal();
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
    }
  }

  saveBtn?.addEventListener("click", handleSave);
  nameInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleSave();
    if (e.key === "Escape") closeModal();
  });
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

  const body = document.createElement("div");
  body.innerHTML = `
    <div class="form-group">
      <label class="form-label">Select a configuration to load</label>
      <div class="config-list" id="config-pick-list">
        ${configs.map((name) =>
          `<button class="btn btn--ghost btn--sm config-pick-btn" data-name="${name}">${name}</button>`
        ).join("")}
      </div>
    </div>
  `;

  const footer = `
    <button class="btn btn--secondary" id="modal-cancel">Cancel</button>
  `;

  openModal({
    title: "Load Configuration",
    body,
    footer,
  });

  document.getElementById("modal-cancel")?.addEventListener("click", closeModal);

  document.getElementById("config-pick-list")?.addEventListener("click", async (e) => {
    const name = e.target.closest(".config-pick-btn")?.dataset.name;
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
