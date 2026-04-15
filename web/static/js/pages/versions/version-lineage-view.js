function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortVersionId(versionId) {
  const raw = String(versionId || "");
  if (!raw) return "-";
  return raw.length > 14 ? `${raw.slice(0, 14)}...` : raw;
}

function sortByCreatedAtAsc(left, right) {
  return String(left?.created_at || "").localeCompare(String(right?.created_at || ""));
}

function buildChildrenMap(versions) {
  const children = new Map();
  const versionIds = new Set(versions.map((version) => String(version?.version_id || "")));

  versions.forEach((version) => {
    const parentId = String(version?.parent_version_id || "");
    const key = parentId && versionIds.has(parentId) ? parentId : "__root__";
    if (!children.has(key)) {
      children.set(key, []);
    }
    children.get(key).push(version);
  });

  children.forEach((items) => items.sort(sortByCreatedAtAsc));
  return children;
}

function renderBranch(version, childrenMap, selectedVersionId, activeVersionId) {
  const versionId = String(version?.version_id || "");
  const isSelected = versionId === selectedVersionId;
  const isActive = versionId === activeVersionId;
  const children = childrenMap.get(versionId) || [];

  return `
    <div class="lineage-branch">
      <button
        type="button"
        class="lineage-node${isSelected ? " is-selected" : ""}${isActive ? " is-active" : ""}"
        data-version-id="${escapeHtml(versionId)}"
        title="${escapeHtml(versionId)}"
      >
        <span class="lineage-node__id">${escapeHtml(shortVersionId(versionId))}</span>
        <span class="lineage-node__meta">${escapeHtml(labelize(version?.status || "draft"))} · ${escapeHtml(labelize(version?.change_type || "-"))}</span>
      </button>
      ${
        children.length
          ? `<div class="lineage-children">${children.map((child) => renderBranch(child, childrenMap, selectedVersionId, activeVersionId)).join("")}</div>`
          : ""
      }
    </div>
  `;
}

export function renderVersionLineageView({
  container,
  versions = [],
  selectedVersionId = "",
  activeVersionId = "",
  onSelect = null,
} = {}) {
  if (!container) return;

  if (!Array.isArray(versions) || !versions.length) {
    container.innerHTML = `
      <div class="versions-state versions-state--empty">
        <strong>No lineage to display.</strong>
        <span>Select a strategy with saved versions to see its parent and child branches.</span>
      </div>
    `;
    return;
  }

  const childrenMap = buildChildrenMap(versions);
  const roots = childrenMap.get("__root__") || [];

  container.innerHTML = `
    <div class="lineage-roots">
      ${roots.map((root) => renderBranch(root, childrenMap, selectedVersionId, activeVersionId)).join("")}
    </div>
  `;

  if (typeof onSelect === "function") {
    container.querySelectorAll("[data-version-id]").forEach((node) => {
      node.addEventListener("click", () => {
        onSelect(node.getAttribute("data-version-id") || "");
      });
    });
  }
}
