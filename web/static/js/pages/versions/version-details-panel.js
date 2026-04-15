function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
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

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

function formatPct(value, decimals = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${number.toFixed(decimals)}%`;
}

function formatNumber(value, decimals = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${number.toFixed(decimals)}`;
}

function formatJson(value) {
  if (value == null) return "{}";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function shortVersionId(versionId) {
  const raw = String(versionId || "");
  if (!raw) return "-";
  return raw.length > 24 ? `${raw.slice(0, 24)}...` : raw;
}

function metricCard(label, value, tone = "") {
  const toneClass = tone ? ` version-metric-card__value--${escapeAttr(tone)}` : "";
  return `
    <div class="version-metric-card">
      <span class="version-metric-card__label">${escapeHtml(label)}</span>
      <strong class="version-metric-card__value${toneClass}">${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderCompareSelector(compareOptions, selectedCompareVersionId) {
  if (!compareOptions.length) {
    return `
      <div class="versions-compare-toolbar__empty">
        No baseline version is available for comparison yet. Diff and metrics will appear here once the lineage has another version to compare against.
      </div>
    `;
  }

  return `
    <label class="versions-compare-toolbar__field">
      <span class="versions-compare-toolbar__label">Compare Against</span>
      <select class="form-select" id="versions-compare-target">
        ${compareOptions.map((option) => `
          <option value="${escapeHtml(option.value)}"${option.value === selectedCompareVersionId ? " selected" : ""}>${escapeHtml(option.label)}</option>
        `).join("")}
      </select>
    </label>
  `;
}

function renderRunComparison(runComparison) {
  if (!runComparison) {
    return `
      <div class="versions-note">
        No comparable completed runs are linked to both versions yet. The diff viewer still shows the exact code and parameter deltas.
      </div>
    `;
  }

  const metrics = Array.isArray(runComparison?.metrics) ? runComparison.metrics : [];
  const prioritizedKeys = ["profit_total_pct", "win_rate", "total_trades", "max_drawdown_pct", "sharpe"];
  const selectedMetrics = prioritizedKeys
    .map((key) => metrics.find((item) => item?.key === key))
    .filter(Boolean);

  const cards = selectedMetrics.length
    ? selectedMetrics.map((item) => {
        const delta = item?.format === "pct"
          ? formatPct(item?.delta)
          : item?.format === "count"
            ? formatNumber(item?.delta, 0)
            : formatNumber(item?.delta, item?.format === "ratio" ? 3 : 2);
        const tone = item?.classification === "improved"
          ? "positive"
          : item?.classification === "regressed"
            ? "negative"
            : "";
        return `
          <div class="version-compare-card">
            <span class="version-compare-card__label">${escapeHtml(item?.label || "-")}</span>
            <strong class="version-compare-card__delta${tone ? ` is-${tone}` : ""}">${escapeHtml(delta)}</strong>
            <span class="version-compare-card__range">
              ${escapeHtml(String(item?.left ?? "-"))} -> ${escapeHtml(String(item?.right ?? "-"))}
            </span>
            <span class="version-compare-card__reason">${escapeHtml(item?.reason || "No comparison reason recorded.")}</span>
          </div>
        `;
      }).join("")
    : '<div class="versions-note">No persisted run metrics were returned for this comparison.</div>';

  const baselineRunId = runComparison?.left?.run_id || "-";
  const candidateRunId = runComparison?.right?.run_id || "-";

  return `
    <div class="versions-note">
      Persisted run evidence compares baseline run ${escapeHtml(baselineRunId)} against candidate run ${escapeHtml(candidateRunId)}.
    </div>
    <div class="version-compare-grid">${cards}</div>
  `;
}

function renderParamDiffRows(comparison) {
  const rows = Array.isArray(comparison?.version_diff?.parameter_diff_rows)
    ? comparison.version_diff.parameter_diff_rows
    : [];

  if (!rows.length) {
    return '<div class="versions-note">No parameter diff was detected for this comparison target.</div>';
  }

  return `
    <div class="version-table-wrapper">
      <table class="version-table">
        <thead>
          <tr>
            <th>Path</th>
            <th>Status</th>
            <th>Before</th>
            <th>After</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td><code>${escapeHtml(row?.path || "-")}</code></td>
              <td><span class="version-pill version-pill--diff-${escapeAttr(row?.status || "changed")}">${escapeHtml(labelize(row?.status || "changed"))}</span></td>
              <td><code>${escapeHtml(formatJson(row?.before))}</code></td>
              <td><code>${escapeHtml(formatJson(row?.after))}</code></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderCodePreview(comparison) {
  const codeDiff = comparison?.version_diff?.code_diff || null;
  if (!codeDiff) {
    return '<div class="versions-note">No code diff summary is available for this version.</div>';
  }

  const previewBlocks = Array.isArray(codeDiff?.preview_blocks) ? codeDiff.preview_blocks : [];
  const summary = codeDiff?.summary || "No persisted code diff summary is available.";

  if (!previewBlocks.length) {
    return `<div class="versions-note">${escapeHtml(summary)}</div>`;
  }

  return `
    <div class="versions-note">${escapeHtml(summary)}</div>
    <div class="version-code-preview">
      ${previewBlocks.map((block) => `
        <div class="version-code-preview__block">
          <div class="version-code-preview__header">${escapeHtml(block?.header || "@@")}</div>
          <pre class="version-code-preview__body">${(Array.isArray(block?.lines) ? block.lines : []).map((line) => {
            const kind = escapeAttr(line?.kind || "context");
            const prefix = kind === "added" ? "+" : kind === "removed" ? "-" : " ";
            return `<span class="version-code-preview__line version-code-preview__line--${kind}">${escapeHtml(`${prefix}${line?.text || ""}`)}</span>`;
          }).join("\n")}</pre>
        </div>
      `).join("")}
      ${codeDiff?.preview_truncated ? '<div class="versions-note">Code preview is truncated. Open the full code snapshot below to inspect the complete resolved artifact.</div>' : ""}
    </div>
  `;
}

function renderLinkedRuns(linkedRuns) {
  if (!Array.isArray(linkedRuns) || !linkedRuns.length) {
    return '<div class="versions-note">No backtest runs are linked to this version yet.</div>';
  }

  return `
    <div class="version-table-wrapper">
      <table class="version-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Trigger</th>
            <th>Completed</th>
            <th>Profit</th>
            <th>Trades</th>
            <th>Drawdown</th>
          </tr>
        </thead>
        <tbody>
          ${linkedRuns.map((run) => {
            const metrics = run?.summary_metrics || {};
            const profit = metrics?.profit_total_pct != null ? formatPct(metrics.profit_total_pct) : "-";
            const drawdown = metrics?.max_drawdown_pct != null ? formatPct(-Math.abs(metrics.max_drawdown_pct)) : "-";
            return `
              <tr>
                <td><code>${escapeHtml(run?.run_id || "-")}</code></td>
                <td><span class="version-pill version-pill--status-${escapeAttr(run?.status || "unknown")}">${escapeHtml(labelize(run?.status || "unknown"))}</span></td>
                <td>${escapeHtml(labelize(run?.trigger_source || "manual"))}</td>
                <td>${escapeHtml(formatDate(run?.completed_at || run?.created_at))}</td>
                <td>${escapeHtml(profit)}</td>
                <td>${escapeHtml(String(metrics?.total_trades ?? "-"))}</td>
                <td>${escapeHtml(drawdown)}</td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderAuditTimeline(version) {
  const events = (Array.isArray(version?.audit_events) ? version.audit_events : [])
    .slice()
    .sort((left, right) => String(right?.created_at || "").localeCompare(String(left?.created_at || "")));

  if (!events.length) {
    return '<div class="versions-note">No audit events are recorded for this version yet.</div>';
  }

  return `
    <div class="version-audit-timeline">
      ${events.map((event) => `
        <div class="version-audit-event">
          <div class="version-audit-event__header">
            <span class="version-pill version-pill--audit-${escapeAttr(event?.event_type || "created")}">${escapeHtml(labelize(event?.event_type || "created"))}</span>
            <span class="version-audit-event__time">${escapeHtml(formatDate(event?.created_at))}</span>
          </div>
          <div class="version-audit-event__meta">
            <span><strong>Actor:</strong> ${escapeHtml(event?.actor || "system")}</span>
            <span><strong>From Version:</strong> ${escapeHtml(event?.from_version_id || "-")}</span>
          </div>
          ${event?.note ? `<div class="version-audit-event__note">${escapeHtml(event.note)}</div>` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

export function renderVersionDetailsPanel({
  container,
  versionDetail = null,
  versions = [],
  loading = false,
  error = "",
  pendingAction = "",
  onAction = null,
  onCompareTargetChange = null,
} = {}) {
  if (!container) return;

  if (loading) {
    container.innerHTML = '<div class="versions-state">Loading version details...</div>';
    return;
  }

  if (error) {
    container.innerHTML = `
      <div class="versions-state versions-state--error">
        <strong>Version details could not be loaded.</strong>
        <span>${escapeHtml(error)}</span>
      </div>
    `;
    return;
  }

  if (!versionDetail?.version) {
    container.innerHTML = `
      <div class="versions-state versions-state--empty">
        <strong>Select a version.</strong>
        <span>Choose a version from the list to inspect its snapshots, lineage evidence, and lifecycle actions.</span>
      </div>
    `;
    return;
  }

  const version = versionDetail.version;
  const versionId = String(version?.version_id || "");
  const isActive = versionId === versionDetail?.active_version_id;
  const isCandidate = String(version?.status || "") === "candidate";
  const canRollback = !isActive && !["candidate", "draft", "rejected"].includes(String(version?.status || ""));
  const compareOptions = (Array.isArray(versions) ? versions : [])
    .filter((entry) => entry?.version_id && entry.version_id !== versionId)
    .sort((left, right) => {
      const leftActive = left?.version_id === versionDetail?.active_version_id ? 1 : 0;
      const rightActive = right?.version_id === versionDetail?.active_version_id ? 1 : 0;
      if (leftActive !== rightActive) return rightActive - leftActive;
      if (left?.version_id === version?.parent_version_id) return -1;
      if (right?.version_id === version?.parent_version_id) return 1;
      return String(right?.created_at || "").localeCompare(String(left?.created_at || ""));
    })
    .map((entry) => {
      const title = entry?.source_context?.title || entry?.summary || entry?.source_ref || entry?.version_id;
      return {
        value: String(entry?.version_id || ""),
        label: `${entry?.version_id || "-"} | ${labelize(entry?.status || "draft")} | ${title}`,
      };
    });

  const metrics = versionDetail?.metrics || {};
  const profitValue = metrics?.profit_total_pct != null ? formatPct(metrics.profit_total_pct) : formatPct(version?.backtest_profit_pct);
  const drawdownValue = metrics?.max_drawdown_pct != null ? formatPct(-Math.abs(metrics.max_drawdown_pct)) : "-";
  const compareButtonDisabled = !compareOptions.length;
  const busyLabel = pendingAction ? `Action in progress: ${labelize(pendingAction)}` : "";
  const sourceTitle = version?.source_context?.title || version?.summary || version?.source_ref || "No summary recorded.";

  container.innerHTML = `
    <section class="versions-detail">
      <div class="versions-detail__header">
        <div class="versions-detail__copy">
          <div class="versions-detail__eyebrow">Version Detail</div>
          <h2 class="versions-detail__title">${escapeHtml(shortVersionId(versionId))}</h2>
          <p class="versions-detail__subtitle">${escapeHtml(sourceTitle)}</p>
          <div class="versions-detail__chips">
            <span class="version-pill version-pill--status-${escapeAttr(version?.status || "draft")}">${escapeHtml(labelize(version?.status || "draft"))}</span>
            <span class="version-pill version-pill--change">${escapeHtml(labelize(version?.change_type || "-"))}</span>
            ${isActive ? '<span class="version-pill version-pill--active">Current Live Target</span>' : ""}
          </div>
        </div>
        <div class="versions-detail__actions">
          <button type="button" class="btn btn--secondary btn--sm" data-action="compare"${compareButtonDisabled ? " disabled" : ""}>Compare</button>
          <button type="button" class="btn btn--secondary btn--sm" data-action="run"${pendingAction ? " disabled" : ""}>Run Backtest</button>
          <button type="button" class="btn btn--secondary btn--sm" data-action="accept"${!isCandidate || pendingAction ? " disabled" : ""}>Accept</button>
          <button type="button" class="btn btn--ghost btn--sm" data-action="reject"${!isCandidate || pendingAction ? " disabled" : ""}>Reject</button>
          <button type="button" class="btn btn--ghost btn--sm" data-action="rollback"${!canRollback || pendingAction ? " disabled" : ""}>Rollback</button>
        </div>
      </div>

      ${busyLabel ? `<div class="versions-note versions-note--busy">${escapeHtml(busyLabel)}</div>` : ""}

      <div class="versions-detail__summary-grid">
        ${metricCard("Version ID", versionId)}
        ${metricCard("Parent Version", version?.parent_version_id || "-")}
        ${metricCard("Created", formatDate(version?.created_at))}
        ${metricCard("Created By", version?.created_by || "system")}
        ${metricCard("Latest Profit", profitValue, metrics?.profit_total_pct > 0 ? "positive" : metrics?.profit_total_pct < 0 ? "negative" : "")}
        ${metricCard("Trades", String(metrics?.total_trades ?? "-"))}
        ${metricCard("Win Rate", metrics?.win_rate != null ? formatPct(metrics.win_rate) : "-")}
        ${metricCard("Max Drawdown", drawdownValue, metrics?.max_drawdown_pct != null ? "negative" : "")}
        ${metricCard("Latest Run", versionDetail?.latest_run?.run_id || "-")}
        ${metricCard("Linked Runs", String(Array.isArray(versionDetail?.linked_runs) ? versionDetail.linked_runs.length : 0))}
      </div>

      <section class="versions-section">
        <div class="versions-section__header">
          <h3 class="versions-section__title">Diff Viewer</h3>
          ${renderCompareSelector(compareOptions, versionDetail?.compare_version_id || "")}
        </div>
        ${renderRunComparison(versionDetail?.run_comparison)}
        <div class="versions-diff-grid">
          <div class="versions-diff-panel">
            <h4 class="versions-diff-panel__title">Code Diff Summary</h4>
            ${renderCodePreview(versionDetail?.comparison)}
          </div>
          <div class="versions-diff-panel">
            <h4 class="versions-diff-panel__title">Parameter Diff</h4>
            ${renderParamDiffRows(versionDetail?.comparison)}
          </div>
        </div>
      </section>

      <section class="versions-section">
        <h3 class="versions-section__title">Linked Runs</h3>
        ${renderLinkedRuns(versionDetail?.linked_runs)}
      </section>

      <section class="versions-section">
        <h3 class="versions-section__title">Resolved Snapshots</h3>
        <div class="versions-snapshot-grid">
          <details class="version-disclosure" open>
            <summary>Code Snapshot</summary>
            <pre class="version-code-block">${escapeHtml(versionDetail?.resolved_code_snapshot || "No resolved code snapshot is available.")}</pre>
          </details>
          <details class="version-disclosure" open>
            <summary>Parameters Snapshot</summary>
            <pre class="version-code-block">${escapeHtml(formatJson(versionDetail?.resolved_parameters_snapshot || {}))}</pre>
          </details>
        </div>
      </section>

      <section class="versions-section">
        <h3 class="versions-section__title">Audit Trail</h3>
        ${renderAuditTimeline(version)}
      </section>
    </section>
  `;

  if (typeof onAction === "function") {
    container.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => {
        onAction(button.getAttribute("data-action") || "");
      });
    });
  }

  const compareTarget = container.querySelector("#versions-compare-target");
  if (compareTarget && typeof onCompareTargetChange === "function") {
    compareTarget.addEventListener("change", (event) => {
      onCompareTargetChange(event.target.value || "");
    });
  }
}
