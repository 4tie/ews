/**
 * header-config-buttons.js — Load Config / Save Config buttons in the setup panel header.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import { openModal, closeModal } from "../../../components/modal.js";
import { emit, on, EVENTS } from "../../../core/events.js";
import { getFormValues, populateForm } from "../../../components/form-helpers.js";
import { getState, setState } from "../../../core/state.js";

const SETUP_FORM_SELECTOR = ".panel--setup";

export function initHeaderConfigButtons() {
  document.getElementById("btn-save-config")?.addEventListener("click", onSaveConfig);
  document.getElementById("btn-load-config")?.addEventListener("click", onLoadConfig);
}

async function onSaveConfig() {
  const name = prompt("Save config as:");
  if (!name?.trim()) return;

  const formData = getFormValues(document.querySelector(SETUP_FORM_SELECTOR));
  formData.pairs = getState("backtest.pairs") ?? [];

  try {
    await api.backtest.saveConfig({ name: name.trim(), data: formData });
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

  const listHtml = configs.map(name =>
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
    await applyConfig(name);
  });
}

async function applyConfig(name) {
  let data;
  try {
    // loadConfig is not in api.js — fetch directly
    const res = await fetch(`/api/backtest/configs/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    ({ data } = await res.json());
  } catch (e) {
    showToast("Load failed: " + e.message, "error");
    return;
  }

  if (!data) {
    showToast(`Config "${name}" is empty.`, "warning");
    return;
  }

  populateForm(document.querySelector(SETUP_FORM_SELECTOR), data);

  if (Array.isArray(data.pairs)) {
    setState("backtest.pairs", data.pairs);
    emit(EVENTS.PAIRS_UPDATED, data.pairs);
  }

  emit(EVENTS.CONFIG_LOADED, { name, data });
  showToast(`Config "${name}" loaded.`, "success");
}
