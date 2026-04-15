import { getState, setState, on as onState } from "../../core/state.js";

const container = document.getElementById("lineage-tree");

export function initVersionLineageView() {
  onState("versions.list", handleListChange);
  onState("versions.selectedVersionId", handleSelectionChange);
  onState("versions.activeVersionId", handleActiveChange);
}

function handleListChange() {
  renderLineage();
}

function handleSelectionChange() {
  updateLineageSelection();
}

function handleActiveChange() {
  updateLineageSelection();
}

function renderLineage() {
  const versions = getState("versions.list") || [];
  const selectedId = getState("versions.selectedVersionId");
  const activeId = getState("versions.activeVersionId");

  if (versions.length === 0) {
    container.innerHTML = `
      <div class="versions-empty">
        <p class="versions-empty__message">Select a strategy to view version lineage</p>
      </div>
    `;
    return;
  }

  const sorted = [...versions].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

  container.innerHTML = sorted
    .map((v, idx) => {
      const isSelected = v.version_id === selectedId;
      const isActive = v.version_id === activeId;
      const classes = [
        isActive ? "is-active" : "",
        isSelected ? "is-selected" : "",
      ].filter(Boolean).join(" ");

      const statusIcon = getStatusIcon(v.status);

      return `
        <div class="lineage-node">
          <div class="lineage-node__item ${classes}" data-version-id="${v.version_id}">
            <span class="lineage-node__id">${v.version_id.substring(0, 6)}</span>
            <span class="lineage-node__status version-item__status--${v.status}">${statusIcon} ${v.status}</span>
          </div>
          ${idx < sorted.length - 1 ? '<span class="lineage-connector">→</span>' : ""}
        </div>
      `;
    })
    .join("");

  container.querySelectorAll(".lineage-node__item").forEach((item) => {
    item.addEventListener("click", () => {
      const versionId = item.dataset.versionId;
      setState("versions.selectedVersionId", versionId);
    });
  });
}

function updateLineageSelection() {
  const selectedId = getState("versions.selectedVersionId");
  const activeId = getState("versions.activeVersionId");

  container.querySelectorAll(".lineage-node__item").forEach((item) => {
    const id = item.dataset.versionId;
    item.classList.remove("is-selected", "is-active");
    if (id === selectedId) item.classList.add("is-selected");
    if (id === activeId) item.classList.add("is-active");
  });
}

function getStatusIcon(status) {
  const icons = {
    active: "✅",
    candidate: "🔶",
    draft: "📝",
    rejected: "❌",
    archived: "📦",
  };
  return icons[status] || "⚪";
}

export function refreshLineage() {
  renderLineage();
}