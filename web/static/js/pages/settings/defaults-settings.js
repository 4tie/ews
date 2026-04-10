/**
 * defaults-settings.js — Persistence/defaults controls.
 */

import persistence from "../../core/persistence.js";
import showToast from "../../components/toast.js";

export function initDefaultsSettings() {
  document.getElementById("btn-clear-persistence")?.addEventListener("click", () => {
    if (!confirm("Clear all saved state? This will reset pairs, configs, and UI state.")) return;
    persistence.clearAll();
    showToast("All saved state cleared.", "warning");
  });
}
