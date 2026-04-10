/**
 * paths-settings.js — Handles path auto-population and validation.
 */

import showToast from "../../components/toast.js";

const DERIVED = [
  { id: "set-config-path",   suffix: "/user_data/config.json"          },
  { id: "set-results-path",  suffix: "/user_data/backtest_results"      },
  { id: "set-userdata-path", suffix: "/user_data"                       },
];

async function validatePath(inputId, statusId) {
  const input  = document.getElementById(inputId);
  const status = document.getElementById(statusId);
  const path   = input?.value?.trim();
  if (!path) { showToast("Enter a path first.", "warning"); return; }

  if (status) status.textContent = "Validating…";
  try {
    const res = await fetch("/api/settings/validate-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const { valid } = await res.json();
    if (status) {
      status.textContent = valid ? "✓ Path exists" : "✗ Path not found";
      status.className   = `field-hint ${valid ? "is-success" : "is-error"}`;
    }
  } catch (e) {
    if (status) { status.textContent = "Validation failed"; status.className = "field-hint is-error"; }
  }
}

export function initPathsSettings() {
  const ftInput = document.getElementById("set-ft-path");

  // Auto-populate derived paths when the base directory is typed/pasted
  ftInput?.addEventListener("input", () => autofillDerived(ftInput.value.trim()));
  ftInput?.addEventListener("change", () => autofillDerived(ftInput.value.trim()));

  document.getElementById("btn-validate-ft-path")
    ?.addEventListener("click", () => validatePath("set-ft-path", "ft-path-status"));
  document.getElementById("btn-validate-config-path")
    ?.addEventListener("click", () => validatePath("set-config-path", "config-path-status"));
}

function autofillDerived(base) {
  if (!base) return;
  const cleanBase = base.replace(/\/+$/, ""); // strip trailing slashes
  DERIVED.forEach(({ id, suffix }) => {
    const el = document.getElementById(id);
    if (el && !el.value.trim()) {
      el.value = cleanBase + suffix;
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
}
