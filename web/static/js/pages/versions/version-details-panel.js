import api from "../../core/api.js";
import { getState, setState, on as onState } from "../../core/state.js";

const titleEl = document.getElementById("version-detail-title");
const actionsEl = document.getElementById("version-actions");
const bodyEl = document.getElementById("version-details-body");

export function initVersionDetailsPanel() {
  onState("versions.selectedVersionId", handleSelectionChange);
  onState("versions.list", handleListChange);
  onState("versions.activeVersionId", handleActiveChange);
}

function handleSelectionChange(versionId) {
  if (!versionId) {
    clearDetails();
    return;
  }
  const versions = getState("versions.list") || [];
  const version = versions.find((v) => v.version_id === versionId);
  if (version) {
    renderDetails(version);
  }
}

function handleListChange() {
  const versionId = getState("versions.selectedVersionId");
  if (versionId) {
    const versions = getState("versions.list") || [];
    const version = versions.find((v) => v.version_id === versionId);
    if (version) {
      renderDetails(version);
    }
  }
}

function handleActiveChange() {
  const versionId = getState("versions.selectedVersionId");
  if (versionId) {
    const versions = getState("versions.list") || [];
    const version = versions.find((v) => v.version_id === versionId);
    if (version) {
      renderDetails(version);
    }
  }
}

function clearDetails() {
  titleEl.textContent = "Select a version";
  actionsEl.innerHTML = "";
  bodyEl.innerHTML = `
    <div class="versions-empty">
      <div class="versions-empty__icon">👈</div>
      <p class="versions-empty__title">No version selected</p>
      <p class="versions-empty__message">Select a version from the list to view its details</p>
    </div>
  `;
}

function renderDetails(version) {
  const activeVersionId = getState("versions.activeVersionId");
  const isActive = version.version_id === activeVersionId;
  const isCandidate = version.status === "candidate";

  titleEl.textContent = `Version ${version.version_id.substring(0, 8)}`;

  actionsEl.innerHTML = `
    ${!isActive && isCandidate ? `<button class="btn btn--success btn--sm" data-action="accept" data-version="${version.version_id}">Accept</button>` : ""}
    ${isCandidate ? `<button class="btn btn--danger btn--sm" data-action="reject" data-version="${version.version_id}">Reject</button>` : ""}
    ${!isActive ? `<button class="btn btn--secondary btn--sm" data-action="rollback" data-version="${version.version_id}">Rollback</button>` : ""}
    <button class="btn btn--ghost btn--sm" data-action="run" data-version="${version.version_id}">Run</button>
    <button class="btn btn--ghost btn--sm" data-action="compare" data-version="${version.version_id}">Compare</button>
  `;

  actionsEl.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", (e) => handleAction(e.target.dataset.action, e.target.dataset.version));
  });

  bodyEl.innerHTML = `
    <div class="version-section">
      <h4 class="version-section__title">Overview</h4>
      <div class="version-metrics-grid">
        <div class="version-metric">
          <span class="version-metric__label">Status</span>
          <span class="version-metric__value version-metric__value--${version.status}">${version.status}</span>
        </div>
        <div class="version-metric">
          <span class="version-metric__label">Change Type</span>
          <span class="version-metric__value">${version.change_type || "unknown"}</span>
        </div>
        <div class="version-metric">
          <span class="version-metric__label">Created</span>
          <span class="version-metric__value">${formatDate(version.created_at)}</span>
        </div>
        <div class="version-metric">
          <span class="version-metric__label">Created By</span>
          <span class="version-metric__value">${version.created_by || "system"}</span>
        </div>
        ${version.profit_pct != null ? `
        <div class="version-metric">
          <span class="version-metric__label">Profit %</span>
          <span class="version-metric__value ${version.profit_pct >= 0 ? 'version-metric__value--positive' : 'version-metric__value--negative'}">${version.profit_pct.toFixed(2)}%</span>
        </div>
        ` : ""}
        ${version.linked_run_id ? `
        <div class="version-metric">
          <span class="version-metric__label">Linked Run</span>
          <a href="/backtesting?run=${version.linked_run_id}" class="version-backtest-link">${version.linked_run_id.substring(0, 8)}</a>
        </div>
        ` : ""}
      </div>
    </div>

    ${version.code_snapshot ? `
    <div class="version-section">
      <h4 class="version-section__title">Code Snapshot</h4>
      <pre class="version-code-block">${escapeHtml(version.code_snapshot.substring(0, 2000))}${version.code_snapshot.length > 2000 ? "\n...(truncated)" : ""}</pre>
    </div>
    ` : ""}

    ${version.parameters && Object.keys(version.parameters).length > 0 ? `
    <div class="version-section">
      <h4 class="version-section__title">Parameters</h4>
      <div class="version-params-list">
        ${Object.entries(version.parameters).map(([key, value]) => `
          <div class="version-param">
            <span class="version-param__name">${key}</span>
            <span class="version-param__value">${typeof value === "object" ? JSON.stringify(value) : value}</span>
          </div>
        `).join("")}
      </div>
    </div>
    ` : ""}

    ${version.summary ? `
    <div class="version-section">
      <h4 class="version-section__title">Summary</h4>
      <div class="version-metrics-grid">
        ${version.total_trades ? `<div class="version-metric"><span class="version-metric__label">Total Trades</span><span class="version-metric__value">${version.total_trades}</span></div>` : ""}
        ${version.win_rate != null ? `<div class="version-metric"><span class="version-metric__label">Win Rate</span><span class="version-metric__value">${(version.win_rate * 100).toFixed(1)}%</span></div>` : ""}
        ${version.max_drawdown != null ? `<div class="version-metric"><span class="version-metric__label">Max Drawdown</span><span class="version-metric__value version-metric__value--negative">${version.max_drawdown.toFixed(2)}%</span></div>` : ""}
      </div>
    </div>
    ` : ""}

    ${version.notes ? `
    <div class="version-section">
      <h4 class="version-section__title">Notes</h4>
      <p>${escapeHtml(version.notes)}</p>
    </div>
    ` : ""}
  `;
}

async function handleAction(action, versionId) {
  const strategy = getState("backtest.strategy");
  if (!strategy) return;

  try {
    switch (action) {
      case "accept":
        if (confirm("Accept this version as the new active version?")) {
          const result = await api.versions.accept(strategy, { version_id: versionId, notes: "Accepted via UI" });
          alert(result.message || "Version accepted successfully");
          refreshVersions();
        }
        break;
      case "reject":
        if (confirm("Reject this candidate version?")) {
          const result = await api.versions.reject(strategy, { version_id: versionId, reason: "Rejected via UI" });
          alert(result.message || "Version rejected");
          refreshVersions();
        }
        break;
      case "rollback":
        if (confirm("Rollback to this version? This will create a new archived version.")) {
          const result = await api.versions.rollback(strategy, { target_version_id: versionId, reason: "Rolled back via UI" });
          alert(result.message || "Rollback complete");
          refreshVersions();
        }
        break;
      case "run":
        window.location.href = `/backtesting?version=${versionId}`;
        break;
      case "compare":
        window.location.href = `/backtesting?compare=${versionId}`;
        break;
    }
  } catch (error) {
    alert("Error: " + error.message);
  }
}

function formatDate(dateStr) {
  if (!dateStr) return "N/A";
  try {
    return new Date(dateStr).toLocaleString();
  } catch {
    return dateStr;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function refreshVersions() {
  if (window.refreshVersions) {
    window.refreshVersions();
  }
}

window.refreshVersionDetails = refreshVersions;