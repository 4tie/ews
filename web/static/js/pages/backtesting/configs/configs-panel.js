/**
 * configs-panel.js — Manage saved backtest configs.
 */

import api from "../../../core/api.js";
import showToast from "../../../components/toast.js";
import { emit, EVENTS } from "../../../core/events.js";

const listEl  = document.getElementById("configs-list");
const saveBtn = document.getElementById("btn-save-current-config");

export async function initConfigsPanel() {
  await loadConfigs();

  saveBtn?.addEventListener("click", async () => {
    const name = prompt("Config name:");
    if (!name) return;
    try {
      // TODO: collect current form state into data object
      await api.backtest.saveConfig({ name, data: {} });
      showToast(`Config "${name}" saved.`, "success");
      await loadConfigs();
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
    }
  });
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
    configs.forEach(name => {
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

    listEl.addEventListener("click", async (e) => {
      const loadName   = e.target.dataset.load;
      const deleteName = e.target.dataset.delete;
      if (loadName) {
        emit(EVENTS.CONFIG_LOADED, { name: loadName });
        showToast(`Config "${loadName}" loaded.`, "info");
      }
      if (deleteName && confirm(`Delete config "${deleteName}"?`)) {
        await api.backtest.deleteConfig(deleteName);
        showToast(`Config "${deleteName}" deleted.`, "warning");
        await loadConfigs();
      }
    }, { once: true });
  } catch (e) {
    showToast("Failed to load configs: " + e.message, "error");
  }
}
