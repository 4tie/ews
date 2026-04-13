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

function setValidationStatus(statusId, message = "", tone = "") {
  const status = document.getElementById(statusId);
  if (!status) return;

  status.textContent = message;
  status.className = tone ? `field-hint ${tone === "success" ? "is-success" : "is-error"}` : "field-hint";
}

function clearValidationStatus(statusId) {
  setValidationStatus(statusId, "", "");
}

async function validatePath(inputId, statusId, kind = "path") {
  const input = document.getElementById(inputId);
  const path = normalizePath(input?.value);
  if (input && path !== input.value) {
    input.value = path;
  }
  if (!path) {
    clearValidationStatus(statusId);
    showToast("Enter a path first.", "warning");
    return;
  }

  setValidationStatus(statusId, "Validating...");
  try {
    const res = await fetch("/api/settings/validate-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, kind }),
    });
    const { valid, error, resolved_path: resolvedPath } = await res.json();
    if (valid && kind === "freqtrade" && resolvedPath) {
      if (input) {
        input.value = resolvedPath;
      }
      autofillDerived(resolvedPath);
      setValidationStatus(statusId, `Resolved executable: ${resolvedPath}`, "success");
    } else if (valid) {
      setValidationStatus(statusId, "Path exists", "success");
    } else {
      setValidationStatus(statusId, error || "Path not found", "error");
    }
  } catch (e) {
    setValidationStatus(statusId, "Validation failed", "error");
  }
}

export function initPathsSettings() {
  const ftInput = document.getElementById("set-ft-path");
  const configInput = document.getElementById("set-config-path");

  ftInput?.addEventListener("input", () => {
    clearValidationStatus("ft-path-status");
    autofillDerived(ftInput.value.trim());
  });
  ftInput?.addEventListener("change", () => {
    clearValidationStatus("ft-path-status");
    autofillDerived(ftInput.value.trim());
  });
  configInput?.addEventListener("input", () => clearValidationStatus("config-path-status"));
  configInput?.addEventListener("change", () => clearValidationStatus("config-path-status"));

  document.getElementById("btn-validate-ft-path")
    ?.addEventListener("click", () => validatePath("set-ft-path", "ft-path-status", "freqtrade"));
  document.getElementById("btn-validate-config-path")
    ?.addEventListener("click", () => validatePath("set-config-path", "config-path-status"));

  if (ftInput?.value?.trim()) {
    autofillDerived(ftInput.value.trim());
    void validatePath("set-ft-path", "ft-path-status", "freqtrade");
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



