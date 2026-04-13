/**
 * history-panel.js - Hybrid persisted run and version audit history surface.
 */

import { el, formatDate, formatNum, formatPct } from "../../../core/utils.js";
import {
  initPersistedRunsStore,
  subscribePersistedRuns,
} from "../results/persisted-runs-store.js";
import {
  initPersistedVersionsStore,
  subscribePersistedVersions,
} from "../results/persisted-versions-store.js";

const historyList = document.getElementById("history-list");
let runsState = { status: "idle", strategy: "", runs: [], error: null };
let versionsState = { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
let historyFilter = "all";

export function initHistoryPanel() {
  if (!historyList) return;

  initPersistedRunsStore();
  initPersistedVersionsStore();
  historyList.addEventListener("click", handleHistoryClick);
  subscribePersistedRuns((snapshot) => {
    runsState = snapshot || { status: "idle", strategy: "", runs: [], error: null };
    renderHistoryState();
  });
  subscribePersistedVersions((snapshot) => {
    versionsState = snapshot || { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
    renderHistoryState();
  });
}

function handleHistoryClick(event) {
  const button = event.target.closest("[data-history-filter]");
  if (!button) return;
  historyFilter = button.dataset.historyFilter || "all";
  renderHistoryState();
}

function renderHistoryState() {
  if (!historyList) return;

  const runs = Array.isArray(runsState.runs) ? runsState.runs : [];
  const versions = Array.isArray(versionsState.versions) ? versionsState.versions : [];
  const strategy = runsState.strategy || versionsState.strategy || "";
  const loading = (runsState.status === "loading" && !runs.length) && (versionsState.status === "loading" && !versions.length);

  if (loading) {
    historyList.innerHTML = '<div class="info-empty">Loading persisted backtest and version history...</div>';
    return;
  }

  if (!runs.length && !versions.length && runsState.status === "error" && versionsState.status === "error") {
    historyList.innerHTML = `<div class="info-empty">Failed to load persisted history: ${escapeHtml(runsState.error || versionsState.error || "Unknown error")}</div>`;
    return;
  }

  renderHistory(runs, versions, strategy);
}

function renderHistory(runs, versions, strategy) {
  if (!historyList) return;

  historyList.innerHTML = "";

  if (!runs.length && !versions.length) {
    const scope = strategy ? ` for ${escapeHtml(strategy)}` : "";
    historyList.innerHTML = `<div class="info-empty">No persisted run or version history is available${scope}. Run a baseline backtest, then create or decide a version to start the audit trail.</div>`;
    return;
  }

  const stack = el("div", { class: "history-stack history-hybrid" });
  stack.appendChild(buildOverviewCard(runs, versions, strategy));
  stack.appendChild(buildFilterToolbar());

  if (historyFilter !== "runs") {
    stack.appendChild(buildDecisionSection(versions));
  }
  if (historyFilter !== "decisions") {
    stack.appendChild(buildRunsSection(runs, strategy));
  }

  historyList.appendChild(stack);
}

function buildOverviewCard(runs, versions, strategy) {
  const card = el("section", { class: "results-context history-overview-card" });
  const activeVersion = versions.find((version) => version?.version_id === versionsState.activeVersionId) || null;
  const completedRuns = runs.filter((run) => run?.status === "completed").length;
  card.innerHTML = `
    <div class="results-context__title">History Overview</div>
    <div class="results-context__meta history-overview-grid">
      <span><strong>Strategy:</strong> ${escapeHtml(strategy || "-")}</span>
      <span><strong>Persisted Runs:</strong> ${escapeHtml(String(runs.length))}</span>
      <span><strong>Completed Runs:</strong> ${escapeHtml(String(completedRuns))}</span>
      <span><strong>Persisted Versions:</strong> ${escapeHtml(String(versions.length))}</span>
      <span><strong>Active Version:</strong> ${escapeHtml(activeVersion?.version_id || versionsState.activeVersionId || "-")}</span>
    </div>
    <div class="results-context__note">Pinned active version is the current live target. Accept promotes into this target, rollback re-pins an older accepted version, and promote-as-new-strategy creates a separate strategy lineage.</div>
  `;
  return card;
}

function buildFilterToolbar() {
  const toolbar = el("div", { class: "history-filter-bar" });
  toolbar.innerHTML = [
    ["all", "All"],
    ["runs", "Runs"],
    ["decisions", "Decisions"],
  ].map(([value, label]) => `
    <button type="button" class="btn btn--ghost btn--sm history-filter-btn${historyFilter === value ? ' is-active' : ''}" data-history-filter="${escapeHtml(value)}">${escapeHtml(label)}</button>
  `).join("");
  return toolbar;
}

function buildDecisionSection(versions) {
  const wrapper = el("section", { class: "results-context history-section history-section--decisions" });
  wrapper.innerHTML = `
    <div class="results-context__title">Version Decisions</div>
    <div class="results-context__note">Active version stays pinned first. Each card shows version metadata, the latest note snippet, linked run evidence, and the persisted audit timeline.</div>
  `;

  if (versionsState.status === "error") {
    wrapper.appendChild(el("div", { class: "results-context__note" }, `Failed to load versions: ${versionsState.error}`));
    return wrapper;
  }

  if (versionsState.status === "loading" && !versions.length) {
    wrapper.appendChild(el("div", { class: "results-context__note" }, "Loading persisted versions..."));
    return wrapper;
  }

  if (!versions.length) {
    wrapper.appendChild(el("div", { class: "results-context__note" }, "No persisted strategy versions are available yet. Create and decide a version first to populate audit history."));
    return wrapper;
  }

  const stack = el("div", { class: "history-decision-stack" });
  sortDecisionVersions(versions).forEach((version) => {
    const card = el("article", {
      class: `history-decision-card${version?.version_id === versionsState.activeVersionId ? " is-active" : ""}`,
    });
    card.innerHTML = buildDecisionCardHtml(version);
    stack.appendChild(card);
  });
  wrapper.appendChild(stack);
  return wrapper;
}

function sortDecisionVersions(versions) {
  return versions.slice().sort((left, right) => {
    const leftActive = left?.version_id === versionsState.activeVersionId ? 1 : 0;
    const rightActive = right?.version_id === versionsState.activeVersionId ? 1 : 0;
    if (leftActive !== rightActive) return rightActive - leftActive;
    const leftDate = String(left?.promoted_at || left?.created_at || "");
    const rightDate = String(right?.promoted_at || right?.created_at || "");
    return rightDate.localeCompare(leftDate);
  });
}

function buildDecisionCardHtml(version) {
  const sourceTitle = version?.source_context?.title || version?.summary || version?.source_ref || "Version";
  const latestAudit = latestAuditEvent(version);
  const latestNote = latestAuditNote(version);
  const auditEvents = getAuditEvents(version);
  const backtestProfit = version?.backtest_profit_pct == null ? "-" : formatPct(version.backtest_profit_pct);
  const isActiveVersion = version?.version_id === versionsState.activeVersionId;
  const activeChip = isActiveVersion
    ? '<span class="history-decision-chip history-decision-chip--active">Current Live Target</span>'
    : "";
  const statusChip = isActiveVersion && String(version?.status || '').toLowerCase() === 'active'
    ? ''
    : `<span class="history-decision-chip history-decision-chip--status-${escapeAttr(version?.status || 'draft')}">${escapeHtml(labelize(version?.status || 'draft'))}</span>`;

  const timeline = auditEvents.length
    ? auditEvents.map((event) => `
        <div class="history-audit-row">
          <div class="history-audit-row__header">
            <span class="history-audit-row__badge history-audit-row__badge--${escapeAttr(event?.event_type || 'created')}">${escapeHtml(formatAuditEventLabel(event?.event_type || 'created'))}</span>
            <span class="history-audit-row__time">${escapeHtml(formatDate(event?.created_at))}</span>
          </div>
          <div class="history-audit-row__meta">
            <span><strong>Actor:</strong> ${escapeHtml(event?.actor || 'system')}</span>
            <span><strong>From Version:</strong> ${escapeHtml(event?.from_version_id || '-')}</span>
          </div>
          ${event?.note ? `<div class="history-audit-row__note">${escapeHtml(event.note)}</div>` : ''}
        </div>
      `).join("")
    : '<div class="results-context__note">No persisted audit events are recorded for this version yet.</div>';

  return `
    <div class="history-decision-card__header">
      <div>
        <h3 class="history-card__title">${escapeHtml(sourceTitle)}</h3>
        <p class="history-card__subtitle">Version ${escapeHtml(version?.version_id || '-')} | Created ${escapeHtml(formatDate(version?.created_at))}</p>
      </div>
      <div class="history-decision-card__chips">
        ${activeChip}
        ${statusChip}
        <span class="history-decision-chip history-decision-chip--change">${escapeHtml(labelize(version?.change_type || '-'))}</span>
      </div>
    </div>
    <div class="history-decision-card__grid">
      <div><span class="history-card__label">Source Kind</span><strong>${escapeHtml(labelize(version?.source_kind || '-'))}</strong></div>
      <div><span class="history-card__label">Parent Version</span><strong>${escapeHtml(version?.parent_version_id || '-')}</strong></div>
      <div><span class="history-card__label">Linked Backtest</span><strong>${escapeHtml(version?.backtest_run_id || '-')}</strong></div>
      <div><span class="history-card__label">Backtest Profit</span><strong>${escapeHtml(backtestProfit)}</strong></div>
      <div><span class="history-card__label">Promoted</span><strong>${escapeHtml(formatDate(version?.promoted_at || ''))}</strong></div>
      <div><span class="history-card__label">Latest Audit</span><strong>${escapeHtml(latestAudit ? formatAuditEventLabel(latestAudit.event_type) : '-')}</strong></div>
    </div>
    <div class="history-decision-card__note">${escapeHtml(latestNote ? `Latest decision note: ${truncateText(latestNote.note)}` : 'No decision note saved for this version.')}</div>
    <div class="history-audit-timeline">
      ${timeline}
    </div>
  `;
}

function getAuditEvents(version) {
  return (Array.isArray(version?.audit_events) ? version.audit_events : [])
    .slice()
    .sort((left, right) => String(right?.created_at || "").localeCompare(String(left?.created_at || "")));
}

function latestAuditEvent(version) {
  return getAuditEvents(version)[0] || null;
}

function latestAuditNote(version) {
  return getAuditEvents(version).find((event) => String(event?.note || "").trim()) || null;
}

function formatAuditEventLabel(value) {
  if (String(value || "") === "promoted_as_new_strategy") {
    return "Promoted As New Strategy";
  }
  return labelize(value);
}

function truncateText(value, maxLength = 160) {
  const textValue = String(value || "").trim();
  if (!textValue || textValue.length <= maxLength) return textValue;
  return `${textValue.slice(0, Math.max(0, maxLength - 1)).trimEnd()}...`;
}

function buildRunsSection(runs, strategy) {
  const wrapper = el("section", { class: "results-context history-section history-section--runs" });
  wrapper.innerHTML = `
    <div class="results-context__title">Persisted Runs</div>
    <div class="results-context__note">${escapeHtml(strategy ? `Use this section to verify baseline runs, candidate reruns, and execution evidence for ${strategy}. Showing ${runs.length} persisted freqtrade run(s).` : `Use this section to verify baseline runs, candidate reruns, and execution evidence. Showing ${runs.length} persisted freqtrade run(s).`)}</div>
  `;

  if (runsState.status === "error") {
    wrapper.appendChild(el("div", { class: "results-context__note" }, `Failed to load persisted runs: ${runsState.error}`));
    return wrapper;
  }

  if (runsState.status === "loading" && !runs.length) {
    wrapper.appendChild(el("div", { class: "results-context__note" }, "Loading persisted backtest runs..."));
    return wrapper;
  }

  if (!runs.length) {
    wrapper.appendChild(el("div", { class: "results-context__note" }, "No persisted backtest runs are available yet. Run a baseline backtest or candidate rerun first."));
    return wrapper;
  }

  const runStack = el("div", { class: "history-run-stack" });
  runs.forEach((run) => runStack.appendChild(buildHistoryCard(run)));
  wrapper.appendChild(runStack);
  return wrapper;
}

function buildHistoryCard(run) {
  const metrics = run?.summary_metrics || {};
  const profitLabel = metrics.profit_total_pct == null ? "No summary" : formatPct(metrics.profit_total_pct);
  const pairCount = metrics.pair_count == null ? "-" : `${metrics.pair_count}`;
  const tradeCount = metrics.total_trades == null ? "-" : `${metrics.total_trades}`;
  const tradeRange = formatTradeRange(metrics);
  const createdAt = formatDate(run?.created_at);
  const completedAt = run?.completed_at ? formatDate(run.completed_at) : "Not completed";
  const strategy = metrics.strategy || run?.strategy || "Unknown strategy";
  const footerText = buildFooterText(run, metrics);

  const card = el("article", { class: "history-card" });
  card.innerHTML = `
    <div class="history-card__header">
      <div>
        <h3 class="history-card__title">${escapeHtml(strategy)}</h3>
        <p class="history-card__subtitle">Created ${createdAt}</p>
      </div>
      <span class="history-card__badge history-card__badge--${escapeAttr(run?.status || "unknown")}">${escapeHtml(labelize(run?.status || "unknown"))}</span>
    </div>
    <div class="history-card__grid">
      <div><span class="history-card__label">Run ID</span><strong>${escapeHtml(run?.run_id || "-")}</strong></div>
      <div><span class="history-card__label">Version</span><strong>${escapeHtml(run?.version_id || "Base")}</strong></div>
      <div><span class="history-card__label">Total Profit</span><strong>${profitLabel}</strong></div>
      <div><span class="history-card__label">Trades</span><strong>${tradeCount}</strong></div>
      <div><span class="history-card__label">Pairs</span><strong>${pairCount}</strong></div>
      <div><span class="history-card__label">Trade Range</span><strong>${escapeHtml(tradeRange)}</strong></div>
      <div><span class="history-card__label">Completed</span><strong>${completedAt}</strong></div>
      <div><span class="history-card__label">Exit Code</span><strong>${formatExitCode(run?.exit_code)}</strong></div>
    </div>
    <div class="history-card__footer">${escapeHtml(footerText)}</div>
  `;

  return card;
}

function buildFooterText(run, metrics) {
  if (run?.error) {
    return `Trigger ${labelize(run?.trigger_source || "manual")} | ${run.error}`;
  }
  if (!run?.summary_available) {
    return `Trigger ${labelize(run?.trigger_source || "manual")} | Persisted run metadata exists, but no ingested summary artifact is linked to this run.`;
  }

  const parts = [`Trigger ${labelize(run?.trigger_source || "manual")}`];
  if (metrics?.timeframe) parts.push(`Timeframe ${metrics.timeframe}`);
  if (metrics?.max_drawdown_pct != null) parts.push(`Max drawdown ${formatPct(-Math.abs(metrics.max_drawdown_pct))}`);
  if (metrics?.profit_total_abs != null) {
    const currency = metrics?.stake_currency ? ` ${metrics.stake_currency}` : "";
    parts.push(`Abs profit ${formatSignedNumber(metrics.profit_total_abs)}${currency}`);
  }
  return parts.join(" | ");
}

function formatTradeRange(metrics) {
  if (metrics?.trade_start || metrics?.trade_end) {
    return `${formatDate(metrics.trade_start)} -> ${formatDate(metrics.trade_end)}`;
  }
  if (metrics?.timerange) {
    return formatTimerange(metrics.timerange);
  }
  return "No persisted trade range";
}

function formatTimerange(timerange) {
  const value = String(timerange || "");
  const parts = value.split("-");
  if (parts.length === 2 && parts[0].length === 8 && parts[1].length === 8) {
    return `${parts[0].slice(0, 4)}-${parts[0].slice(4, 6)}-${parts[0].slice(6, 8)} -> ${parts[1].slice(0, 4)}-${parts[1].slice(4, 6)}-${parts[1].slice(6, 8)}`;
  }
  return value || "No persisted trade range";
}

function formatExitCode(value) {
  return value == null ? "-" : String(value);
}

function formatSignedNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value || "-");
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${formatNum(number, 2)}`;
}

function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

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
