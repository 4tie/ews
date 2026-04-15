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

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

function formatPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${number.toFixed(2)}%`;
}

function shortVersionId(versionId) {
  const raw = String(versionId || "");
  if (!raw) return "-";
  return raw.length > 18 ? `${raw.slice(0, 18)}...` : raw;
}

export function renderVersionListPanel({
  container,
  countEl,
  versions = [],
  selectedVersionId = "",
  activeVersionId = "",
  loading = false,
  error = "",
  onSelect = null,
} = {}) {
  if (!container || !countEl) return;

  countEl.textContent = String(Array.isArray(versions) ? versions.length : 0);

  if (loading) {
    container.innerHTML = '<div class="versions-state">Loading versions...</div>';
    return;
  }

  if (error) {
    container.innerHTML = `
      <div class="versions-state versions-state--error">
        <strong>Versions could not be loaded.</strong>
        <span>${escapeHtml(error)}</span>
      </div>
    `;
    return;
  }

  if (!Array.isArray(versions) || !versions.length) {
    container.innerHTML = `
      <div class="versions-state versions-state--empty">
        <strong>No versions found.</strong>
        <span>Create or bootstrap a version for this strategy to start the lifecycle.</span>
      </div>
    `;
    return;
  }

  container.innerHTML = versions
    .map((version) => {
      const versionId = String(version?.version_id || "");
      const isSelected = versionId === selectedVersionId;
      const isActive = versionId === activeVersionId;
      const profit = formatPct(version?.backtest_profit_pct);
      const sourceTitle = version?.source_context?.title || version?.summary || version?.source_ref || "";

      return `
        <button
          type="button"
          class="version-list-item${isSelected ? " is-selected" : ""}${isActive ? " is-active" : ""}"
          data-version-id="${escapeHtml(versionId)}"
          title="${escapeHtml(versionId)}"
        >
          <div class="version-list-item__header">
            <div class="version-list-item__title-group">
              <span class="version-list-item__id">${escapeHtml(shortVersionId(versionId))}</span>
              ${isActive ? '<span class="version-pill version-pill--active">Live</span>' : ""}
            </div>
            <span class="version-pill version-pill--status-${escapeHtml(String(version?.status || "draft"))}">
              ${escapeHtml(labelize(version?.status || "draft"))}
            </span>
          </div>
          <div class="version-list-item__meta">
            <span>${escapeHtml(labelize(version?.change_type || "-"))}</span>
            <span>${escapeHtml(String(version?.created_by || "system"))}</span>
          </div>
          <div class="version-list-item__meta">
            <span>${escapeHtml(formatDate(version?.created_at))}</span>
            <span class="version-list-item__profit${profit && Number(version?.backtest_profit_pct) >= 0 ? " is-positive" : ""}${profit && Number(version?.backtest_profit_pct) < 0 ? " is-negative" : ""}">
              ${escapeHtml(profit || "No run")}
            </span>
          </div>
          <div class="version-list-item__summary">${escapeHtml(sourceTitle || "No summary recorded.")}</div>
        </button>
      `;
    })
    .join("");

  if (typeof onSelect === "function") {
    container.querySelectorAll("[data-version-id]").forEach((node) => {
      node.addEventListener("click", () => {
        onSelect(node.getAttribute("data-version-id") || "");
      });
    });
  }
}
