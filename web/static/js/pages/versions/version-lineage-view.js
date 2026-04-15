function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value) {
  return String(value ?? "").replace(/[^a-z0-9_-]/gi, "-").toLowerCase();
}

function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function shortVersionId(versionId) {
  const raw = String(versionId || "");
  if (!raw) return "-";
  return raw.length > 24 ? `${raw.slice(0, 24)}...` : raw;
}

function formatCompactDate(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return String(value);
  }
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
  const status = escapeAttr(version?.status || "draft");
  const isSelected = versionId === selectedVersionId;
  const isActive = versionId === activeVersionId;
  const children = childrenMap.get(versionId) || [];

  return `
    <div class="lineage-branch">
      <button
        type="button"
        class="lineage-node lineage-node--status-${status}${isSelected ? " is-selected" : ""}${isActive ? " is-active" : ""}"
        data-version-id="${escapeHtml(versionId)}"
        title="${escapeHtml(versionId)}"
      >
        <div class="lineage-node__top">
          <span class="lineage-node__id">${escapeHtml(shortVersionId(versionId))}</span>
          <span class="version-pill version-pill--status-${status}">${escapeHtml(labelize(version?.status || "draft"))}</span>
        </div>
        <div class="lineage-node__meta">
          <span>${escapeHtml(labelize(version?.change_type || "-"))}</span>
          <span>${escapeHtml(formatCompactDate(version?.created_at))}</span>
        </div>
        <div class="lineage-node__footer">
          ${isActive ? '<span class="version-pill version-pill--active">Live</span>' : ""}
          ${children.length ? `<span class="lineage-node__children">${children.length} child${children.length === 1 ? "" : "ren"}</span>` : ""}
        </div>
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
        <span>Select a strategy with saved versions to see parent and child branches.</span>
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
