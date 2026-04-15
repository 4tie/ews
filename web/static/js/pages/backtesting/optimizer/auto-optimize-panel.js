/**
 * auto-optimize-panel.js - Auto Optimize v1 UI (parameter-only beam search).
 */

import api from "../../../core/api.js";
import { on, EVENTS } from "../../../core/events.js";
import { formatPct } from "../../../core/utils.js";
import showToast from "../../../components/toast.js";
import { refreshPersistedRuns } from "../results/persisted-runs-store.js";
import { refreshPersistedVersions } from "../results/persisted-versions-store.js";
import { setSelectedCandidateVersionId } from "../compare/candidate-selection-state.js";

const root = document.getElementById("summary-auto-optimize");

let baselineRunId = "";
let baselineVersionId = "";
let optimizerRunId = "";
let pollTimer = null;
let busy = false;
let lastRecord = null;

const defaults = {
  attempts: 3,
  beamWidth: 2,
  branchFactor: 3,
  includeAI: false,
  minProfitTotalPct: 0.5,
  minTotalTrades: 30,
  maxAllowedDrawdownPct: 35,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function coerceInt(value, fallback) {
  const n = parseInt(String(value ?? ""), 10);
  return Number.isFinite(n) ? n : fallback;
}

function coerceFloat(value, fallback) {
  const n = parseFloat(String(value ?? ""));
  return Number.isFinite(n) ? n : fallback;
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function pollOnce() {
  if (!optimizerRunId) return;
  try {
    const record = await api.optimizer.getRun(optimizerRunId);
    lastRecord = record;

    const status = String(record?.status || "").toLowerCase();
    render();

    if (status === "completed" || status === "failed") {
      stopPolling();
      await Promise.allSettled([refreshPersistedRuns(), refreshPersistedVersions(null, { silent: true })]);
    }
  } catch (error) {
    stopPolling();
    busy = false;
    showToast(`Auto Optimize poll failed: ${escapeHtml(error?.message || String(error))}`, "error", 7000);
    render();
  }
}

function startPolling() {
  stopPolling();
  pollOnce();
  pollTimer = setInterval(pollOnce, 1200);
}

function summarizeCounts(record) {
  const nodes = Array.isArray(record?.nodes) ? record.nodes : [];
  const counts = { total: nodes.length, completed: 0, failed: 0, deduped: 0 };
  for (const node of nodes) {
    const status = String(node?.status || "").toLowerCase();
    if (status === "completed") counts.completed += 1;
    if (status === "failed") counts.failed += 1;
    if (status === "deduped") counts.deduped += 1;
  }
  return counts;
}

function renderFinalists(record) {
  const finalists = Array.isArray(record?.finalists) ? record.finalists : [];
  if (!finalists.length) {
    return '<div class="info-empty">No finalists yet.</div>';
  }

  const rows = finalists
    .map((item) => {
      const metrics = item?.summary_metrics || {};
      const profit = metrics?.profit_total_pct;
      const dd = metrics?.max_drawdown_pct;
      const trades = metrics?.total_trades;
      return `
        <tr>
          <td><code>${escapeHtml(item?.version_id || "-")}</code></td>
          <td><code>${escapeHtml(item?.run_id || "-")}</code></td>
          <td>${escapeHtml(formatPct(profit))}</td>
          <td>${escapeHtml(formatPct(dd))}</td>
          <td>${escapeHtml(trades ?? "-")}</td>
          <td><button class="btn btn--secondary btn--xs" data-action="select-finalist" data-version-id="${escapeHtml(item?.version_id || "")}">Select</button></td>
        </tr>
      `;
    })
    .join("");

  return `
    <div class="results-context__table">
      <table class="data-table">
        <thead>
          <tr>
            <th>Version</th>
            <th>Run</th>
            <th>Profit</th>
            <th>Drawdown</th>
            <th>Trades</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderNearMisses(record) {
  const misses = Array.isArray(record?.near_misses) ? record.near_misses : [];
  if (!misses.length) return "";

  const items = misses
    .map((item) => {
      const failed = Array.isArray(item?.failed_constraints) ? item.failed_constraints : [];
      const why = failed.length ? `Failed: ${failed.join(", ")}` : "";
      const descriptor = item?.candidate_descriptor ? ` | ${item.candidate_descriptor}` : "";
      return `<li><code>${escapeHtml(item?.version_id || "-")}</code>${descriptor} ${escapeHtml(why)}</li>`;
    })
    .join("");

  return `
    <div class="results-context__note" style="margin-top: var(--space-2);">
      <div style="font-weight: 600; margin-bottom: var(--space-1);">Near Misses</div>
      <ul class="diagnosis-list">${items}</ul>
    </div>
  `;
}

function render() {
  if (!root) return;

  const hasBaseline = Boolean(baselineRunId);
  const record = lastRecord;
  const status = String(record?.status || (optimizerRunId ? "queued" : "idle")).toLowerCase();
  const terminal = status === "completed" || status === "failed";
  const counts = record ? summarizeCounts(record) : { total: 0, completed: 0, failed: 0, deduped: 0 };

  const errorBlock = record?.error
    ? `<div class="results-context__note" style="color: var(--color-danger);">${escapeHtml(record?.error?.message || "Optimizer error")}</div>`
    : "";

  const disabled = busy || !hasBaseline || (!terminal && Boolean(optimizerRunId));

  root.innerHTML = `
    <section class="results-context results-context--workflow-guide">
      <div class="results-context__title">Auto Optimize</div>
      <div class="results-context__note">Parameter-only beam search anchored to the currently loaded baseline run.</div>
      <div class="results-context__meta">
        <span><strong>Baseline run</strong><br/><code>${escapeHtml(baselineRunId || "-")}</code></span>
        <span><strong>Baseline version</strong><br/><code>${escapeHtml(baselineVersionId || "-")}</code></span>
        <span><strong>Status</strong><br/>${escapeHtml(status)}</span>
        <span><strong>Nodes</strong><br/>${escapeHtml(`${counts.total} total | ${counts.completed} completed | ${counts.failed} failed | ${counts.deduped} deduped`)}</span>
      </div>

      <div class="results-context__note" style="margin-top: var(--space-2);">
        <div class="sidebar-subgrid" style="gap: var(--space-3);">
          <div class="setup-field">
            <label class="form-label form-label--sub" for="auto-opt-attempts">Attempts</label>
            <input class="form-input" type="number" id="auto-opt-attempts" min="1" value="${escapeHtml(defaults.attempts)}" ${disabled ? "disabled" : ""} />
          </div>
          <div class="setup-field">
            <label class="form-label form-label--sub" for="auto-opt-beam">Beam width</label>
            <input class="form-input" type="number" id="auto-opt-beam" min="1" value="${escapeHtml(defaults.beamWidth)}" ${disabled ? "disabled" : ""} />
          </div>
          <div class="setup-field">
            <label class="form-label form-label--sub" for="auto-opt-branch">Branch factor</label>
            <input class="form-input" type="number" id="auto-opt-branch" min="1" value="${escapeHtml(defaults.branchFactor)}" ${disabled ? "disabled" : ""} />
          </div>
          <div class="setup-field" style="align-self: end;">
            <label class="form-label form-label--sub" for="auto-opt-ai">Include AI</label>
            <input type="checkbox" id="auto-opt-ai" ${defaults.includeAI ? "checked" : ""} ${disabled ? "disabled" : ""} />
          </div>
        </div>

        <div class="sidebar-subgrid" style="gap: var(--space-3); margin-top: var(--space-3);">
          <div class="setup-field">
            <label class="form-label form-label--sub" for="auto-opt-min-profit">Min profit %</label>
            <input class="form-input" type="number" id="auto-opt-min-profit" step="0.1" value="${escapeHtml(defaults.minProfitTotalPct)}" ${disabled ? "disabled" : ""} />
          </div>
          <div class="setup-field">
            <label class="form-label form-label--sub" for="auto-opt-min-trades">Min trades</label>
            <input class="form-input" type="number" id="auto-opt-min-trades" min="0" value="${escapeHtml(defaults.minTotalTrades)}" ${disabled ? "disabled" : ""} />
          </div>
          <div class="setup-field">
            <label class="form-label form-label--sub" for="auto-opt-max-dd">Max drawdown %</label>
            <input class="form-input" type="number" id="auto-opt-max-dd" step="0.1" value="${escapeHtml(defaults.maxAllowedDrawdownPct)}" ${disabled ? "disabled" : ""} />
          </div>
        </div>

        <div class="action-group" style="margin-top: var(--space-3);">
          <button class="btn btn--primary btn--sm" id="auto-opt-start" ${disabled ? "disabled" : ""}>Start Auto Optimize</button>
          ${optimizerRunId ? `<span class="field-hint" style="margin-left: var(--space-2);">Run: <code>${escapeHtml(optimizerRunId)}</code></span>` : ""}
        </div>
      </div>

      ${errorBlock}

      <div class="results-context__note" style="margin-top: var(--space-3);">
        <div style="font-weight: 600; margin-bottom: var(--space-2);">Finalists</div>
        ${renderFinalists(record)}
        ${renderNearMisses(record)}
      </div>
    </section>
  `;

  root.querySelectorAll("[data-action='select-finalist']").forEach((btn) => {
    btn.addEventListener("click", () => {
      const versionId = btn.getAttribute("data-version-id") || "";
      if (!versionId) return;
      setSelectedCandidateVersionId(versionId, baselineRunId);
      showToast(`Selected candidate ${escapeHtml(versionId)} for compare/workflow.`, "success");
    });
  });

  const startButton = root.querySelector("#auto-opt-start");
  startButton?.addEventListener("click", async () => {
    if (!baselineRunId) {
      showToast("Run a baseline backtest first.", "warning");
      return;
    }

    busy = true;
    render();

    try {
      const attempts = coerceInt(root.querySelector("#auto-opt-attempts")?.value, defaults.attempts);
      const beamWidth = coerceInt(root.querySelector("#auto-opt-beam")?.value, defaults.beamWidth);
      const branchFactor = coerceInt(root.querySelector("#auto-opt-branch")?.value, defaults.branchFactor);
      const includeAI = Boolean(root.querySelector("#auto-opt-ai")?.checked);

      const minProfitTotalPct = coerceFloat(root.querySelector("#auto-opt-min-profit")?.value, defaults.minProfitTotalPct);
      const minTotalTrades = coerceInt(root.querySelector("#auto-opt-min-trades")?.value, defaults.minTotalTrades);
      const maxAllowedDrawdownPct = coerceFloat(root.querySelector("#auto-opt-max-dd")?.value, defaults.maxAllowedDrawdownPct);

      const response = await api.optimizer.startRun({
        baseline_run_id: baselineRunId,
        attempts,
        beam_width: beamWidth,
        branch_factor: branchFactor,
        include_ai_suggestions: includeAI,
        thresholds: {
          min_profit_total_pct: minProfitTotalPct,
          min_total_trades: minTotalTrades,
          max_allowed_drawdown_pct: maxAllowedDrawdownPct,
        },
      });

      optimizerRunId = response?.optimizer_run_id || "";
      lastRecord = null;
      busy = false;
      showToast(`Auto Optimize started (${escapeHtml(optimizerRunId)})`, "info");
      render();
      startPolling();
    } catch (error) {
      optimizerRunId = "";
      lastRecord = null;
      busy = false;
      showToast(`Auto Optimize failed to start: ${escapeHtml(error?.message || String(error))}`, "error", 8000);
      render();
    }
  });
}

export function initAutoOptimizePanel() {
  if (!root) return;

  on(EVENTS.RESULTS_LOADED, (payload) => {
    const nextRunId = String(payload?.run_id || "");
    const nextVersionId = String(payload?.version_id || "");

    const changed = nextRunId !== baselineRunId;
    baselineRunId = nextRunId;
    baselineVersionId = nextVersionId;

    if (changed) {
      optimizerRunId = "";
      lastRecord = null;
      busy = false;
      stopPolling();
    }
    render();
  });

  render();
}

