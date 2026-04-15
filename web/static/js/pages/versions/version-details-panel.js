import { closeModal, openModal } from "../../components/modal.js";
import { renderVersionLineageView } from "./version-lineage-view.js";

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

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
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
  return raw.length > 28 ? `${raw.slice(0, 28)}...` : raw;
}

function metricCard(label, value, tone = "", detail = "") {
  const toneClass = tone ? ` version-metric-card__value--${escapeAttr(tone)}` : "";
  return `
    <div class="version-metric-card">
      <span class="version-metric-card__label">${escapeHtml(label)}</span>
      <strong class="version-metric-card__value${toneClass}">${escapeHtml(value)}</strong>
      ${detail ? `<span class="version-metric-card__detail">${escapeHtml(detail)}</span>` : ""}
    </div>
  `;
}

function renderCompareSelector(compareOptions, selectedCompareVersionId) {
  if (!compareOptions.length) {
    return `
      <div class="versions-compare-toolbar__empty">
        No baseline version is available for comparison yet. Diff panels will activate once this branch has another saved version to compare against.
      </div>
    `;
  }

  return `
    <label class="versions-compare-toolbar__field">
      <span class="versions-compare-toolbar__label">Compare Against</span>
      <select class="form-select" id="versions-compare-target">
        ${compareOptions.map((option) => `
          <option value="${escapeHtml(option.value)}"${option.value === selectedCompareVersionId ? " selected" : ""}>
            ${escapeHtml(option.label)}
          </option>
        `).join("")}
      </select>
    </label>
  `;
}

function renderRunComparison(runComparison) {
  if (!runComparison) {
    return `
      <div class="versions-note">
        No comparable completed runs are linked to both versions yet. The diff viewer still shows exact code and parameter deltas.
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
    <div class="version-table-wrapper version-table-wrapper--diff">
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
      ${codeDiff?.preview_truncated ? '<div class="versions-note">Code preview is truncated. Open the full code snapshot in Snapshots to inspect the resolved artifact.</div>' : ""}
    </div>
  `;
}

function renderLinkedRunsTable(linkedRuns) {
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
            <th>
              Drawdown
              <button type="button" class="btn btn--ghost btn--xs version-rollback-config-btn" data-action="rollback-config" title="Rollback strategy config">Rollback Config</button>
            </th>
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

function renderRunsPreview(linkedRuns) {
  if (!Array.isArray(linkedRuns) || !linkedRuns.length) {
    return '<div class="versions-note">No backtest runs are linked to this version yet.</div>';
  }

  return `
    <div class="versions-preview-list">
      ${linkedRuns.slice(0, 3).map((run) => {
        const metrics = run?.summary_metrics || {};
        const profit = metrics?.profit_total_pct != null ? formatPct(metrics.profit_total_pct) : "No profit";
        return `
          <div class="versions-preview-row">
            <div class="versions-preview-row__main">
              <code>${escapeHtml(run?.run_id || "-")}</code>
              <span>${escapeHtml(labelize(run?.status || "unknown"))} | ${escapeHtml(labelize(run?.trigger_source || "manual"))}</span>
            </div>
            <div class="versions-preview-row__side">
              <strong>${escapeHtml(profit)}</strong>
              <span>${escapeHtml(String(metrics?.total_trades ?? "-"))} trades</span>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderAuditPreview(version) {
  const events = (Array.isArray(version?.audit_events) ? version.audit_events : [])
    .slice()
    .sort((left, right) => String(right?.created_at || "").localeCompare(String(left?.created_at || "")))
    .slice(0, 4);

  if (!events.length) {
    return '<div class="versions-note">No audit events are recorded for this version yet.</div>';
  }

  return `
    <div class="versions-preview-list">
      ${events.map((event) => `
        <div class="versions-preview-row versions-preview-row--audit">
          <div class="versions-preview-row__main">
            <span class="version-pill version-pill--audit-${escapeAttr(event?.event_type || "created")}">${escapeHtml(labelize(event?.event_type || "created"))}</span>
            <span>${escapeHtml(event?.actor || "system")}</span>
          </div>
          <div class="versions-preview-row__side">
            <strong>${escapeHtml(formatCompactDate(event?.created_at))}</strong>
            <span>${escapeHtml(event?.from_version_id || "No source version")}</span>
          </div>
          ${event?.note ? `<div class="versions-preview-row__note">${escapeHtml(event.note)}</div>` : ""}
        </div>
      `).join("")}
    </div>
  `;
}
function renderSnapshotPanel({ title, description, target, content }) {
  return `
    <section class="versions-panel-surface versions-snapshot-panel">
      <div class="versions-snapshot-panel__header">
        <div>
          <h3 class="versions-section__title">${escapeHtml(title)}</h3>
          <p class="versions-snapshot-panel__subtitle">${escapeHtml(description)}</p>
        </div>
        <div class="versions-snapshot-panel__actions">
          <button type="button" class="btn btn--ghost btn--sm version-copy-btn" data-copy-target="${escapeHtml(target)}">Copy</button>
          <button type="button" class="btn btn--secondary btn--sm version-expand-btn" data-expand-target="${escapeHtml(target)}">Expand</button>
        </div>
      </div>
      <pre class="version-code-block">${escapeHtml(content)}</pre>
    </section>
  `;
}

function openSnapshotModal(title, text) {
  const body = `
    <div class="versions-modal versions-modal--snapshot">
      <pre class="version-code-block version-code-block--modal">${escapeHtml(text)}</pre>
    </div>
  `;
  const footer = `
    <button type="button" class="btn btn--ghost btn--sm" id="versions-snapshot-close">Close</button>
    <button type="button" class="btn btn--secondary btn--sm" id="versions-snapshot-copy">Copy</button>
  `;

  openModal({ title, body, footer });

  document.getElementById("versions-snapshot-close")?.addEventListener("click", () => closeModal());
  document.getElementById("versions-snapshot-copy")?.addEventListener("click", async (event) => {
    try {
      await navigator.clipboard.writeText(text);
      event.currentTarget.textContent = "Copied";
      window.setTimeout(() => {
        const button = document.getElementById("versions-snapshot-copy");
        if (button) button.textContent = "Copy";
      }, 1500);
    } catch (error) {
      console.warn("Failed to copy snapshot:", error);
    }
  });
}

function buildCompareOptions(versions, version, activeVersionId) {
  return (Array.isArray(versions) ? versions : [])
    .filter((entry) => entry?.version_id && entry.version_id !== version?.version_id)
    .sort((left, right) => {
      const leftActive = left?.version_id === activeVersionId ? 1 : 0;
      const rightActive = right?.version_id === activeVersionId ? 1 : 0;
      if (leftActive !== rightActive) return rightActive - leftActive;
      if (left?.version_id === version?.parent_version_id) return -1;
      if (right?.version_id === version?.parent_version_id) return 1;
      return String(right?.created_at || "").localeCompare(String(left?.created_at || ""));
    })
    .map((entry) => {
      const title = entry?.source_context?.title || entry?.summary || entry?.source_ref || entry?.version_id;
      return {
        value: String(entry?.version_id || ""),
        label: `${shortVersionId(entry?.version_id || "-")} | ${labelize(entry?.status || "draft")} | ${title}`,
      };
    });
}

export function renderVersionDetailsPanel({
  container,
  versionDetail = null,
  versions = [],
  selectedVersionId = "",
  activeVersionId = "",
  activeTab = "overview",
  loading = false,
  error = "",
  pendingAction = "",
  onAction = null,
  onCompareTargetChange = null,
  onTabChange = null,
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
        <span>Choose a version from the list to inspect snapshots, lineage, runs, and lifecycle actions.</span>
      </div>
    `;
    return;
  }

  const version = versionDetail.version;
  const versionId = String(version?.version_id || "");
  const currentActiveVersionId = String(activeVersionId || versionDetail?.active_version_id || "");
  const isActive = versionId === currentActiveVersionId;
  const isCandidate = String(version?.status || "") === "candidate";
  const canRollback = !isActive && !["candidate", "draft", "rejected"].includes(String(version?.status || ""));
  const compareOptions = buildCompareOptions(versions, version, currentActiveVersionId);
  const metrics = versionDetail?.metrics || {};
  const linkedRuns = Array.isArray(versionDetail?.linked_runs) ? versionDetail.linked_runs : [];
  const lineageVersionIds = Array.isArray(versionDetail?.lineage_version_ids) ? versionDetail.lineage_version_ids : [];
  const latestProfit = metrics?.profit_total_pct != null ? formatPct(metrics.profit_total_pct) : formatPct(version?.backtest_profit_pct);
  const drawdownValue = metrics?.max_drawdown_pct != null ? formatPct(-Math.abs(metrics.max_drawdown_pct)) : "-";
  const busyLabel = pendingAction ? `Action in progress: ${labelize(pendingAction)}` : "";
  const sourceTitle = version?.source_context?.title || version?.summary || version?.source_ref || "No summary recorded.";
  const selectedCompareVersionId = String(versionDetail?.compare_version_id || "");
  const baselineVersionId = String(versionDetail?.comparison?.versions?.baseline_version_id || selectedCompareVersionId || "");
  const candidateVersionId = String(versionDetail?.comparison?.versions?.candidate_version_id || versionId);
  const childCount = (Array.isArray(versions) ? versions : []).filter((entry) => String(entry?.parent_version_id || "") === versionId).length;
  const currentTab = ["overview", "diff", "snapshots", "lineage", "runs"].includes(activeTab) ? activeTab : "overview";

  const compactMetrics = [
    {
      label: "Latest Profit",
      value: latestProfit,
      tone: metrics?.profit_total_pct > 0 ? "positive" : metrics?.profit_total_pct < 0 ? "negative" : "",
      detail: linkedRuns.length ? `from ${linkedRuns[0]?.run_id || "latest run"}` : "No linked run yet",
    },
    {
      label: "Trades",
      value: String(metrics?.total_trades ?? "-"),
      detail: linkedRuns.length ? "latest linked run" : "waiting for backtest",
    },
    {
      label: "Win Rate",
      value: metrics?.win_rate != null ? formatPct(metrics.win_rate) : "-",
      detail: metrics?.win_rate != null ? "completed-run evidence" : "no run evidence",
    },
    {
      label: "Drawdown",
      value: drawdownValue,
      tone: metrics?.max_drawdown_pct != null ? "negative" : "",
      detail: metrics?.max_drawdown_pct != null ? "latest linked run" : "no run evidence",
    },
  ];
  const overviewContent = `
    <div class="versions-overview">
      <section class="versions-overview__metrics">
        ${compactMetrics.map((item) => metricCard(item.label, item.value, item.tone, item.detail)).join("")}
      </section>

      <div class="versions-overview__grid">
        <section class="versions-panel-surface versions-overview__summary">
          <h3 class="versions-section__title">Summary</h3>
          <p class="versions-overview__summary-copy">${escapeHtml(sourceTitle)}</p>
          <div class="versions-overview__context">
            <span class="versions-mini-stat">
              <span class="versions-mini-stat__label">Parent</span>
              <strong>${escapeHtml(shortVersionId(version?.parent_version_id || "Root"))}</strong>
            </span>
            <span class="versions-mini-stat">
              <span class="versions-mini-stat__label">Lineage</span>
              <strong>${escapeHtml(String(lineageVersionIds.length || 1))} versions</strong>
            </span>
            <span class="versions-mini-stat">
              <span class="versions-mini-stat__label">Children</span>
              <strong>${escapeHtml(String(childCount))}</strong>
            </span>
          </div>
        </section>

        <section class="versions-panel-surface versions-overview__runs-preview">
          <div class="versions-panel-surface__header">
            <h3 class="versions-section__title">Linked Runs</h3>
            <span class="versions-panel-surface__count">${escapeHtml(String(linkedRuns.length))}</span>
          </div>
          ${renderRunsPreview(linkedRuns)}
        </section>

        <section class="versions-panel-surface versions-overview__audit-preview">
          <div class="versions-panel-surface__header">
            <h3 class="versions-section__title">Audit Trail</h3>
            <span class="versions-panel-surface__count">${escapeHtml(String((Array.isArray(version?.audit_events) ? version.audit_events : []).length))}</span>
          </div>
          ${renderAuditPreview(version)}
        </section>
      </div>
    </div>
  `;

  const diffContent = `
    <div class="versions-diff">
      <section class="versions-panel-surface versions-diff__header">
        <div class="versions-diff__selector">
          ${renderCompareSelector(compareOptions, selectedCompareVersionId)}
        </div>
        <div class="versions-diff__version-pair">
          <div class="versions-diff__version-label">
            <span>Baseline</span>
            <strong>${escapeHtml(shortVersionId(baselineVersionId || "Not selected"))}</strong>
          </div>
          <div class="versions-diff__version-label versions-diff__version-label--selected">
            <span>Selected</span>
            <strong>${escapeHtml(shortVersionId(candidateVersionId || versionId))}</strong>
          </div>
        </div>
      </section>

      <section class="versions-panel-surface versions-diff__comparison">
        <div class="versions-panel-surface__header">
          <h3 class="versions-section__title">Run Evidence</h3>
        </div>
        ${renderRunComparison(versionDetail?.run_comparison)}
      </section>

      <div class="versions-diff-grid">
        <section class="versions-diff-panel">
          <div class="versions-panel-surface__header">
            <h3 class="versions-section__title">Parameter Diff</h3>
          </div>
          ${renderParamDiffRows(versionDetail?.comparison)}
        </section>

        <section class="versions-diff-panel">
          <div class="versions-panel-surface__header">
            <h3 class="versions-section__title">Code Diff Summary</h3>
          </div>
          ${renderCodePreview(versionDetail?.comparison)}
        </section>
      </div>
    </div>
  `;

  const snapshotsContent = `
    <div class="versions-snapshots">
      ${renderSnapshotPanel({
        title: "Code Snapshot",
        description: "Resolved strategy artifact for this exact version.",
        target: "code",
        content: versionDetail?.resolved_code_snapshot || "No resolved code snapshot is available.",
      })}
      ${renderSnapshotPanel({
        title: "Parameters Snapshot",
        description: "Resolved parameters bound to this version.",
        target: "params",
        content: formatJson(versionDetail?.resolved_parameters_snapshot || {}),
      })}
    </div>
  `;

  const lineageContent = `
    <div class="versions-lineage-tab">
      <section class="versions-panel-surface versions-lineage__context">
        <div class="versions-lineage__facts">
          <div class="versions-lineage__fact">
            <span>Parent</span>
            <strong>${escapeHtml(shortVersionId(version?.parent_version_id || "Root"))}</strong>
          </div>
          <div class="versions-lineage__fact">
            <span>Children</span>
            <strong>${escapeHtml(String(childCount))}</strong>
          </div>
          <div class="versions-lineage__fact">
            <span>Visible Lineage</span>
            <strong>${escapeHtml(String(lineageVersionIds.length || versions.length || 1))}</strong>
          </div>
        </div>
        <div class="versions-lineage__legend">
          <span class="version-pill version-pill--active">Live</span>
          <span class="version-pill version-pill--status-candidate">Candidate</span>
          <span class="version-pill version-pill--status-rejected">Rejected</span>
        </div>
      </section>

      <section class="versions-panel-surface versions-lineage__tree-shell">
        <div id="versions-lineage-tree"></div>
      </section>
    </div>
  `;

  const runsContent = `
    <div class="versions-runs">
      <section class="versions-panel-surface">
        <div class="versions-panel-surface__header">
          <h3 class="versions-section__title">Linked Runs</h3>
          <span class="versions-panel-surface__count">${escapeHtml(String(linkedRuns.length))}</span>
        </div>
        ${renderLinkedRunsTable(linkedRuns)}
      </section>
    </div>
  `;

  const tabs = [
    { id: "overview", label: "Overview", count: "" },
    { id: "diff", label: "Diff", count: compareOptions.length ? "1" : "" },
    { id: "snapshots", label: "Snapshots", count: "2" },
    { id: "lineage", label: "Lineage", count: String(lineageVersionIds.length || versions.length || 1) },
    { id: "runs", label: "Runs", count: String(linkedRuns.length) },
  ];
  container.innerHTML = `
    <section class="versions-detail">
      <div class="versions-detail__header">
        <div class="versions-detail__header-main">
          <div class="versions-detail__identity">
            <span class="versions-detail__eyebrow">Selected Version</span>
            <h2 class="versions-detail__title" title="${escapeHtml(versionId)}">${escapeHtml(versionId || "-")}</h2>
            <div class="versions-detail__badges">
              <span class="version-pill version-pill--status-${escapeAttr(version?.status || "draft")}">${escapeHtml(labelize(version?.status || "draft"))}</span>
              <span class="version-pill version-pill--change-${escapeAttr(version?.change_type || "manual")}">${escapeHtml(labelize(version?.change_type || "-"))}</span>
              ${isActive ? '<span class="version-pill version-pill--active">Live</span>' : ""}
            </div>
          </div>

          <dl class="versions-detail__facts">
            <div class="versions-detail__fact">
              <dt>Created</dt>
              <dd>${escapeHtml(formatDate(version?.created_at))}</dd>
            </div>
            <div class="versions-detail__fact">
              <dt>Created By</dt>
              <dd>${escapeHtml(version?.created_by || "system")}</dd>
            </div>
            <div class="versions-detail__fact">
              <dt>Latest Profit</dt>
              <dd class="versions-detail__fact-value${metrics?.profit_total_pct > 0 ? " is-positive" : metrics?.profit_total_pct < 0 ? " is-negative" : ""}">${escapeHtml(latestProfit)}</dd>
            </div>
          </dl>

          <div class="versions-detail__actions">
            <div class="versions-action-cluster">
              <button type="button" class="btn btn--secondary btn--sm" data-action="compare"${!compareOptions.length ? " disabled" : ""}>Compare</button>
              <button type="button" class="btn btn--secondary btn--sm" data-action="run"${pendingAction ? " disabled" : ""}>Run Backtest</button>
            </div>
            <div class="versions-action-cluster versions-action-cluster--decision">
              <button type="button" class="btn btn--primary btn--sm" data-action="accept"${!isCandidate || pendingAction ? " disabled" : ""}>Accept</button>
              <button type="button" class="btn btn--ghost btn--sm versions-btn--danger-outline" data-action="reject"${!isCandidate || pendingAction ? " disabled" : ""}>Reject</button>
              <button type="button" class="btn btn--ghost btn--sm versions-btn--warning-outline" data-action="rollback"${!canRollback || pendingAction ? " disabled" : ""}>Rollback</button>
            </div>
          </div>
        </div>

        ${busyLabel ? `<div class="versions-note versions-note--busy">${escapeHtml(busyLabel)}</div>` : ""}
      </div>

      <div class="versions-tabs">
        <div class="versions-tabs__nav">
          ${tabs.map((tab) => `
            <button type="button" class="versions-tab-btn${tab.id === currentTab ? " is-active" : ""}" data-tab="${escapeHtml(tab.id)}">
              <span>${escapeHtml(tab.label)}</span>
              ${tab.count && tab.count !== "0" ? `<span class="versions-tab-btn__count">${escapeHtml(tab.count)}</span>` : ""}
            </button>
          `).join("")}
        </div>

        <div class="versions-tabs__content">
          <div class="versions-tab-pane${currentTab === "overview" ? " is-active" : ""}" data-tab="overview">${overviewContent}</div>
          <div class="versions-tab-pane${currentTab === "diff" ? " is-active" : ""}" data-tab="diff">${diffContent}</div>
          <div class="versions-tab-pane${currentTab === "snapshots" ? " is-active" : ""}" data-tab="snapshots">${snapshotsContent}</div>
          <div class="versions-tab-pane${currentTab === "lineage" ? " is-active" : ""}" data-tab="lineage">${lineageContent}</div>
          <div class="versions-tab-pane${currentTab === "runs" ? " is-active" : ""}" data-tab="runs">${runsContent}</div>
        </div>
      </div>
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

  container.querySelectorAll(".versions-tab-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const tabName = button.getAttribute("data-tab") || "overview";
      container.querySelectorAll(".versions-tab-btn").forEach((node) => node.classList.remove("is-active"));
      container.querySelectorAll(".versions-tab-pane").forEach((node) => node.classList.remove("is-active"));
      button.classList.add("is-active");
      container.querySelector(`.versions-tab-pane[data-tab="${tabName}"]`)?.classList.add("is-active");
      if (typeof onTabChange === "function") {
        onTabChange(tabName);
      }
    });
  });

  const copySnapshotText = async (button, text) => {
    if (!text) return;
    const originalLabel = button.textContent;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = originalLabel;
      }, 1500);
    } catch (error) {
      console.warn("Failed to copy snapshot:", error);
    }
  };

  container.querySelectorAll(".version-copy-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.getAttribute("data-copy-target");
      const text = target === "code"
        ? versionDetail?.resolved_code_snapshot || ""
        : formatJson(versionDetail?.resolved_parameters_snapshot || {});
      void copySnapshotText(button, text);
    });
  });

  container.querySelectorAll(".version-expand-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.getAttribute("data-expand-target");
      if (target === "code") {
        openSnapshotModal("Code Snapshot", versionDetail?.resolved_code_snapshot || "No resolved code snapshot is available.");
        return;
      }
      openSnapshotModal("Parameters Snapshot", formatJson(versionDetail?.resolved_parameters_snapshot || {}));
    });
  });

  const lineageContainer = container.querySelector("#versions-lineage-tree");
  renderVersionLineageView({
    container: lineageContainer,
    versions,
    selectedVersionId: selectedVersionId || versionId,
    activeVersionId: currentActiveVersionId,
    onSelect: (nextVersionId) => {
      if (typeof onAction === "function") {
        onAction("select-version", nextVersionId);
      }
    },
  });
}
