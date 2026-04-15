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

function formatListDate(value) {
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

function formatPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${number.toFixed(2)}%`;
}

function shortVersionId(versionId) {
  const raw = String(versionId || "");
  if (!raw) return "-";
  return raw.length > 20 ? `${raw.slice(0, 20)}...` : raw;
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
      const status = String(version?.status || "draft");
      const isSelected = versionId === selectedVersionId;
      const isActive = versionId === activeVersionId;
      const profit = formatPct(version?.backtest_profit_pct);
      const sourceTitle = version?.source_context?.title || version?.summary || version?.source_ref || "";

      return `
        <button
          type="button"
          class="version-list-item version-list-item--status-${escapeAttr(status)}${isSelected ? " is-selected" : ""}${isActive ? " is-active" : ""}"
          data-version-id="${escapeHtml(versionId)}"
          title="${escapeHtml(versionId)}"
        >
          <div class="version-list-item__topline">
            <div class="version-list-item__title-group">
              <span class="version-list-item__id">${escapeHtml(shortVersionId(versionId))}</span>
              ${isActive ? '<span class="version-pill version-pill--active">Live</span>' : ""}
            </div>
            <span class="version-pill version-pill--status-${escapeAttr(status)}">
              ${escapeHtml(labelize(status))}
            </span>
          </div>

          <div class="version-list-item__summary">${escapeHtml(sourceTitle || "No summary recorded.")}</div>

          <div class="version-list-item__footer">
            <span class="version-list-item__meta-group">
              <span class="version-list-item__meta-label">Change</span>
              <span class="version-list-item__meta-value">${escapeHtml(labelize(version?.change_type || "-"))}</span>
            </span>
            <span class="version-list-item__meta-group">
              <span class="version-list-item__meta-label">By</span>
              <span class="version-list-item__meta-value">${escapeHtml(String(version?.created_by || "system"))}</span>
            </span>
            <span class="version-list-item__meta-group">
              <span class="version-list-item__meta-label">Created</span>
              <span class="version-list-item__meta-value">${escapeHtml(formatListDate(version?.created_at))}</span>
            </span>
            <span class="version-list-item__profit${profit && Number(version?.backtest_profit_pct) >= 0 ? " is-positive" : ""}${profit && Number(version?.backtest_profit_pct) < 0 ? " is-negative" : ""}">
              ${escapeHtml(profit || "No run")}
            </span>
          </div>
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
