/**
 * paths-settings.js - Handles path auto-population and validation.
 */

import showToast from "../../components/toast.js";

const DERIVED = [
  { id: "set-config-path", parts: ["user_data", "config.json"] },
  { id: "set-results-path", parts: ["user_data", "backtest_results"] },
  { id: "set-userdata-path", parts: ["user_data"] },
];

function normalizePath(value) {
  return String(value ?? "").trim();
}

function trimTrailingSeparators(value) {
  return normalizePath(value).replace(/[\\/]+$/, "");
}

function detectSeparator(value) {
  return normalizePath(value).includes("\\") ? "\\" : "/";
}

function removeLastSegment(value) {
  const trimmed = trimTrailingSeparators(value);
  return trimmed.replace(/[\\/][^\\/]+$/, "");
}

function lastSegment(value) {
  return trimTrailingSeparators(value).split(/[\\/]/).pop()?.toLowerCase() || "";
}

function inferFreqtradeRoot(rawPath) {
  let base = trimTrailingSeparators(rawPath);
  if (!base) return "";

  if (/(^|[\\/])freqtrade(?:\.exe)?$/i.test(base)) {
    base = removeLastSegment(base);
  }

  let tail = lastSegment(base);
  if (tail === "scripts" || tail === "bin") {
    base = removeLastSegment(base);
    tail = lastSegment(base);
  }

  if (tail === ".venv" || tail === "venv") {
    base = removeLastSegment(base);
  }

  return trimTrailingSeparators(base) || trimTrailingSeparators(rawPath);
}

function joinDerivedPath(base, parts) {
  const root = trimTrailingSeparators(base);
  if (!root) return "";
  const separator = detectSeparator(root);
  return [root, ...parts].join(separator);
}

async function validatePath(inputId, statusId, kind = "path") {
  const input = document.getElementById(inputId);
  const status = document.getElementById(statusId);
  const path = input?.value?.trim();
  if (!path) {
    showToast("Enter a path first.", "warning");
    return;
  }

  if (status) status.textContent = "Validating...";
  try {
    const res = await fetch("/api/settings/validate-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, kind }),
    });
    const { valid, error, resolved_path: resolvedPath } = await res.json();
    if (status) {
      if (valid && kind === "freqtrade" && resolvedPath) {
        status.textContent = `Resolved executable: ${resolvedPath}`;
      } else if (valid) {
        status.textContent = "Path exists";
      } else {
        status.textContent = error || "Path not found";
      }
      status.className = `field-hint ${valid ? "is-success" : "is-error"}`;
    }
  } catch (e) {
    if (status) {
      status.textContent = "Validation failed";
      status.className = "field-hint is-error";
    }
  }
}

export function initPathsSettings() {
  const ftInput = document.getElementById("set-ft-path");

  ftInput?.addEventListener("input", () => autofillDerived(ftInput.value.trim()));
  ftInput?.addEventListener("change", () => autofillDerived(ftInput.value.trim()));

  document.getElementById("btn-validate-ft-path")
    ?.addEventListener("click", () => validatePath("set-ft-path", "ft-path-status", "freqtrade"));
  document.getElementById("btn-validate-config-path")
    ?.addEventListener("click", () => validatePath("set-config-path", "config-path-status"));

  if (ftInput?.value?.trim()) {
    autofillDerived(ftInput.value.trim());
  }
}

function autofillDerived(base) {
  const inferredRoot = inferFreqtradeRoot(base);
  if (!inferredRoot) return;

  DERIVED.forEach(({ id, parts }) => {
    const el = document.getElementById(id);
    if (el && !el.value.trim()) {
      el.value = joinDerivedPath(inferredRoot, parts);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
}
