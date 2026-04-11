import api from "../../core/api.js";
import showToast from "../../components/toast.js";

const state = {
  lastResult: null,
  initialModel: "",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function setConnectionStatus(text, kind = "") {
  const el = document.getElementById("ollama-connection-status");
  if (!el) return;
  el.textContent = text;
  el.className = `field-hint${kind ? ` is-${kind}` : ""}`;
}

function renderSummary(result) {
  const summaryEl = document.getElementById("ollama-summary");
  if (!summaryEl) return;
  if (!result) {
    summaryEl.innerHTML = "";
    return;
  }

  const models = safeArray(result.models);
  const localCount = models.filter((model) => model?.source === "local").length;
  const cloudCount = models.filter((model) => model?.source === "cloud").length;
  summaryEl.innerHTML = `
    <div class="settings-ai-pill"><strong>Host:</strong> ${escapeHtml(result.host || "")}</div>
    <div class="settings-ai-pill"><strong>Version:</strong> ${escapeHtml(result.version || "Unavailable")}</div>
    <div class="settings-ai-pill"><strong>Local Models:</strong> ${escapeHtml(localCount)}</div>
    <div class="settings-ai-pill"><strong>Cloud via Ollama:</strong> ${escapeHtml(cloudCount)}</div>
  `;
}

function renderDefaultModelOptions(result) {
  const select = document.getElementById("set-ollama-default-model");
  if (!select) return;

  const currentValue = String(select.value || state.initialModel || "").trim();
  const localModels = safeArray(result?.models).filter((model) => model?.source === "local" && model?.name);
  const selectedValue = localModels.some((model) => model.name === currentValue)
    ? currentValue
    : localModels[0]?.name || "";

  const options = ['<option value="">No local model available</option>'];
  localModels.forEach((model) => {
    const selected = model.name === selectedValue ? " selected" : "";
    options.push(`<option value="${escapeHtml(model.name)}"${selected}>${escapeHtml(model.name)}</option>`);
  });
  select.innerHTML = options.join("");
  select.value = selectedValue;
}

function renderCapabilityList(items) {
  const values = safeArray(items).filter(Boolean);
  if (!values.length) {
    return '<div class="settings-ai-list settings-ai-list--empty">No guidance available.</div>';
  }
  return `<ul class="settings-ai-list">${values.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderModels(result) {
  const grid = document.getElementById("ollama-models-grid");
  if (!grid) return;

  const models = safeArray(result?.models);
  if (!models.length) {
    grid.innerHTML = '<div class="settings-ai-empty">No models were returned from this Ollama host.</div>';
    return;
  }

  grid.innerHTML = models.map((model) => {
    const capabilities = safeArray(model.raw_capabilities);
    const sourceClass = model.source === "cloud" ? "is-cloud" : "is-local";
    return `
      <article class="settings-ai-card ${sourceClass}">
        <header class="settings-ai-card__header">
          <div>
            <h3 class="settings-ai-card__title">${escapeHtml(model.name || "Unknown model")}</h3>
            <div class="settings-ai-card__meta">
              <span>${escapeHtml(model.source_label || model.source || "")}</span>
              <span>${escapeHtml(model.family || "Unknown family")}</span>
              <span>${escapeHtml(model.parameter_size || "Unknown size")}</span>
              <span>${escapeHtml(model.quantization_level || "")}</span>
            </div>
          </div>
          <div class="settings-ai-card__badges">
            <span class="settings-ai-badge">Tool calling: ${model.tool_calling_supported_by_model ? "Supported by model" : "No"}</span>
            <span class="settings-ai-badge ${model.tool_calling_can_be_enabled ? "settings-ai-badge--interactive" : "settings-ai-badge--muted"}">
              App tools: 
              ${model.tool_calling_can_be_enabled 
                ? `<label class="toggle-inline" style="margin-left: 4px;"><input type="checkbox" class="toggle-tools" data-model="${escapeHtml(model.name)}" ${model.tool_calling_enabled_in_app ? "checked" : ""}> <span>${model.tool_calling_enabled_in_app ? "Enabled" : "Disabled"}</span></label>`
                : "Disabled"
              }
            </span>
          </div>
        </header>
        <div class="settings-ai-card__caps">
          ${capabilities.length ? capabilities.map((capability) => `<span class="settings-ai-badge">${escapeHtml(capability)}</span>`).join("") : '<span class="settings-ai-badge settings-ai-badge--muted">No raw capabilities reported</span>'}
        </div>
        <div class="settings-ai-card__body">
          <section>
            <h4>Can Do</h4>
            ${renderCapabilityList(model.app_recommended_for)}
          </section>
          <section>
            <h4>What Not To Use It For</h4>
            ${renderCapabilityList(model.app_not_recommended_for)}
          </section>
        </div>
      </article>
    `;
  }).join("");
}

async function discover({ silent = false } = {}) {
  const hostInput = document.getElementById("set-ollama-host");
  const refreshBtn = document.getElementById("btn-discover-ollama");
  const host = String(hostInput?.value || "").trim();
  if (!host) {
    showToast("Enter an Ollama host first.", "warning");
    return;
  }

  refreshBtn?.setAttribute("disabled", "disabled");
  setConnectionStatus("Checking Ollama host?");

  try {
    const result = await api.settings.discoverOllama({ host });
    state.lastResult = result;
    renderSummary(result);
    renderDefaultModelOptions(result);
    renderModels(result);

    if (result.reachable) {
      setConnectionStatus(`Connected to ${result.host} (v${result.version || "unknown"}).`, "success");
      if (!silent) {
        showToast("Ollama models refreshed.", "success");
      }
    } else {
      setConnectionStatus(result.errors?.[0] || "Could not reach the Ollama host.", "error");
      if (!silent) {
        showToast("Ollama host is not reachable.", "error");
      }
    }
  } catch (error) {
    renderSummary(null);
    renderModels({ models: [] });
    setConnectionStatus(`Discovery failed: ${error.message}`, "error");
    if (!silent) {
      showToast(`Ollama discovery failed: ${error.message}`, "error");
    }
  } finally {
    refreshBtn?.removeAttribute("disabled");
  }
}

export async function initOllamaSettings(initialSettings = {}) {
  const hostInput = document.getElementById("set-ollama-host");
  const refreshBtn = document.getElementById("btn-discover-ollama");
  if (!hostInput || !refreshBtn) return;

  if (!hostInput.value.trim()) {
    hostInput.value = String(initialSettings?.ollama_host || "").trim();
  }
  state.initialModel = String(initialSettings?.ollama_default_model || "").trim();

  refreshBtn.addEventListener("click", () => {
    void discover();
  });
  hostInput.addEventListener("change", () => {
    setConnectionStatus("Host changed. Refresh models to verify connectivity.");
  });

  if (hostInput.value.trim()) {
    await discover({ silent: true });
  }
}
