import api from "../../core/api.js";
import { getState, setState, on as onState } from "../../core/state.js";
import { on as onEvent, EVENTS } from "../../core/events.js";

const container = document.getElementById("version-list");
const countEl = document.getElementById("version-count");

let selectedVersionId = null;

export function initVersionListPanel() {
  onState("backtest.strategy", handleStrategyChange);
  onState("versions.selectedVersionId", handleSelectionChange);

  const strategy = getState("backtest.strategy");
  if (strategy) {
    loadVersions(strategy);
  }
}

function handleStrategyChange(strategy) {
  if (!strategy) {
    setState("versions.list", []);
    setState("versions.activeVersionId", null);
    setState("versions.selectedVersionId", null);
    renderList([]);
    return;
  }
  loadVersions(strategy);
}

async function loadVersions(strategy) {
  setState("versions.status", "loading");
  renderLoading();

  try {
    const response = await api.versions.listVersions(strategy, true);
    setState("versions.list", response.versions || []);
    setState("versions.activeVersionId", response.active_version_id || null);
    setState("versions.status", "ready");
    setState("versions.error", null);
    renderList(response.versions || []);
  } catch (error) {
    setState("versions.status", "error");
    setState("versions.error", error.message);
    renderError(error.message);
  }
}

function handleSelectionChange(versionId) {
  selectedVersionId = versionId;
  updateSelection();
}

function updateSelection() {
  const items = container.querySelectorAll(".version-item");
  items.forEach((item) => {
    const id = item.dataset.versionId;
    item.classList.toggle("is-selected", id === selectedVersionId);
  });
}

function renderList(versions) {
  if (!versions || versions.length === 0) {
    container.innerHTML = `
      <div class="versions-empty">
        <div class="versions-empty__icon">📋</div>
        <p class="versions-empty__title">No versions</p>
        <p class="versions-empty__message">Run a backtest to create versions</p>
      </div>
    `;
    countEl.textContent = "0";
    return;
  }

  countEl.textContent = versions.length;

  container.innerHTML = versions
    .map(
      (v) => `
    <div class="version-item${v.version_id === selectedVersionId ? " is-selected" : ""}" data-version-id="${v.version_id}">
      <div class="version-item__header">
        <span class="version-item__id">${v.version_id.substring(0, 8)}</span>
        <span class="version-item__status version-item__status--${v.status}">${v.status}</span>
      </div>
      <div class="version-item__meta">
        <span class="version-item__change-type">${v.change_type || "unknown"}</span>
        <span class="version-item__date">${formatDate(v.created_at)}</span>
      </div>
    </div>
  `
    )
    .join("");

  container.querySelectorAll(".version-item").forEach((item) => {
    item.addEventListener("click", () => {
      const versionId = item.dataset.versionId;
      setState("versions.selectedVersionId", versionId);
    });
  });
}

function renderLoading() {
  container.innerHTML = `
    <div class="versions-loading">
      <span>Loading versions...</span>
    </div>
  `;
}

function renderError(message) {
  container.innerHTML = `
    <div class="versions-error">
      <span>Error loading versions</span>
      <span>${message}</span>
    </div>
  `;
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString();
  } catch {
    return dateStr;
  }
}

export function refreshVersions() {
  const strategy = getState("backtest.strategy");
  if (strategy) {
    loadVersions(strategy);
  }
}

window.refreshVersions = refreshVersions;