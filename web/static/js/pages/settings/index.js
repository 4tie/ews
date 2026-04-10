/**
 * index.js — Settings page entry point.
 */

import { initPathsSettings }   from "./paths-settings.js";
import { initDefaultsSettings } from "./defaults-settings.js";
import { initThemeSettings }   from "./theme-settings.js";
import api                     from "../../core/api.js";
import { populateForm }        from "../../components/form-helpers.js";
import showToast               from "../../components/toast.js";

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const settings = await api.settings.get();
    populateForm(document.body, settings);
  } catch (e) {
    console.warn("Could not load settings:", e.message);
  }

  initPathsSettings();
  initDefaultsSettings();
  initThemeSettings();

  document.getElementById("btn-save-settings")?.addEventListener("click", async () => {
    const { getFormValues } = await import("../../components/form-helpers.js");
    const data = getFormValues(document.body);
    try {
      await api.settings.save(data);
      const status = document.getElementById("settings-save-status");
      if (status) { status.textContent = "Saved"; status.className = "save-status is-saved"; }
      showToast("Settings saved.", "success");
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
    }
  });
});
