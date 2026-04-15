
/**
 * auto-optimize-panel.js - Auto Optimize v1 UI (parameter-only beam search).
 */

import api from "../../../core/api.js";
import { on, EVENTS } from "../../../core/events.js";
import { formatPct, formatDate } from "../../../core/utils.js";
import showToast from "../../../components/toast.js";
import { refreshPersistedRuns } from "../results/persisted-runs-store.js";
import { refreshPersistedVersions } from "../results/persisted-versions-store.js";
import { setSelectedCandidateVersionId } from "../compare/candidate-selection-state.js";

const root = document.getElementById("summary-auto-optimize");

let baselineRunId = "";
let baselineVersionId = "";
let optimizerRunId = "";
let pollTimer = null;
let eventSource = null;
let eventReconnectTimer = null;
let busy = false;
let paused = false;
let pausedEventBuffer = [];
let lastRecord = null;
let optimizerEvents = [];
let eventSignatures = new Set();

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
    .replace(/\"/g, "&quot;")
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

function isTerminalStatus(status) {
  const normalized = String(status || "").toLowerCase();
  return normalized === "completed" || normalized === "failed";
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function clearEventReconnectTimer() {
  if (eventReconnectTimer) {
    clearTimeout(eventReconnectTimer);
    eventReconnectTimer = null;
  }
}

function stopEventStream() {
  clearEventReconnectTimer();
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function resetEventLog() {
  optimizerEvents = [];
  eventSignatures = new Set();
  paused = false;
  pausedEventBuffer = [];
}

function flushPausedEvents() {
  if (!paused || pausedEventBuffer.length === 0) return;
  while (pausedEventBuffer.length) {
    optimizerEvents.push(pausedEventBuffer.shift());
  }
}

function eventSignature(event) {
  return JSON.stringify(event || {});
}

function appendOptimizerEvent(event) {
  if (!event || typeof event !== "object") return;
  const signature = eventSignature(event);
  if (eventSignatures.has(signature)) return;
  eventSignatures.add(signature);

  if (paused) {
    pausedEventBuffer.push(event);
    return;
  }

  optimizerEvents.push(event);
  render();
}

function scheduleEventReconnect() {
  clearEventReconnectTimer();
  eventReconnectTimer = setTimeout(() => {
    eventReconnectTimer = null;
    if (!optimizerRunId || isTerminalStatus(lastRecord?.status)) {
      return;
    }
    startEventStream();
  }, 1500);
}

function startEventStream() {
  if (!optimizerRunId || eventSource) return;

  const source = api.optimizer.streamEvents(optimizerRunId);
  eventSource = source;

  source.onmessage = (message) => {
    let payload = null;
    try {
      payload = JSON.parse(message.data);
    } catch {
      payload = { event_type: "optimizer_stream_message", line: String(message.data || "") };
    }

    const type = String(payload?.event_type || "").toLowerCase();
    if (type === "optimizer_stream_started") {
      return;
    }
    if (type === "optimizer_stream_done") {
      stopEventStream();
      return;
    }

    appendOptimizerEvent(payload);
  };

  source.onerror = () => {
    if (eventSource !== source) return;
    source.close();
    eventSource = null;
    if (!isTerminalStatus(lastRecord?.status)) {
      scheduleEventReconnect();
    }
  };
}

async function pollOnce() {
  if (!optimizerRunId) return;
  try {
    const record = await api.optimizer.getRun(optimizerRunId);
    lastRecord = record;

    const status = String(record?.status || "").toLowerCase();
    if (!isTerminalStatus(status) && !eventSource) {
      startEventStream();
    }
    render();

    if (isTerminalStatus(status)) {
      stopPolling();
      await Promise.allSettled([refreshPersistedRuns(), refreshPersistedVersions(null, { silent: true })]);
    }
  } catch (error) {
    stopPolling();
    stopEventStream();
    busy = false;
    showToast(`Auto Optimize poll failed: ${escapeHtml(error?.message || String(error))}`, "error", 7000);
    render();
  }
}

function startPolling() {
  stopPolling();
  startEventStream();
  void pollOnce();
  pollTimer = setInterval(() => {
    void pollOnce();
  }, 1200);
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

function formatNumber(value, digits = 2) {
  if (value == null || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return numeric.toFixed(digits);
}

function formatMetricValue(key, value) {
  if (value == null || value === "") return "-";
  if (key === "profit_total_pct" || key === "max_drawdown_pct" || key === "win_rate") {
    return formatPct(value);
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : formatNumber(value, 2);
  }
  return String(value);
}

function formatConstraintName(value) {
  const key = String(value || "").trim();
  if (!key) return "constraint";
  if (key === "min_profit_total_pct") return "profit threshold";
  if (key === "min_total_trades") return "trade threshold";
  if (key === "max_allowed_drawdown_pct") return "drawdown threshold";
  return key.replace(/_/g, " ");
}

function formatHardStopReason(value) {
  const key = String(value || "").trim();
  return key ? key.replace(/_/g, " ") : "hard stop";
}

function formatDescriptor(value) {
  const descriptor = String(value || "").trim();
  return descriptor || "candidate";
}

function thresholdSummary(thresholds) {
  if (!thresholds || typeof thresholds !== "object") return "default thresholds";
  return [
    `profit >= ${formatPct(thresholds.min_profit_total_pct ?? defaults.minProfitTotalPct)}`,
    `trades >= ${thresholds.min_total_trades ?? defaults.minTotalTrades}`,
    `drawdown <= ${formatPct(thresholds.max_allowed_drawdown_pct ?? defaults.maxAllowedDrawdownPct)}`,
  ].join(" | ");
}

function hardStopSummary(hardStops) {
  if (!hardStops || typeof hardStops !== "object") return "default hard stops";
  return [
    `max nodes ${hardStops.max_total_nodes ?? "auto"}`,
    `max failed runs ${hardStops.max_failed_runs ?? "auto"}`,
    `max no-improve attempts ${hardStops.max_consecutive_no_improvement_attempts ?? 3}`,
  ].join(" | ");
}

function eventTone(event) {
  const type = String(event?.event_type || "").toLowerCase();
  if (type === "optimizer_failed" || type === "candidate_run_failed") return "error";
  if (
    type === "candidate_deduped"
    || type === "optimizer_hard_stop_triggered"
    || type === "optimizer_stop_requested"
    || type === "optimizer_no_frontier_remaining"
    || type === "optimizer_parent_no_candidate_seeds"
    || type === "optimizer_completed_no_finalists"
  ) {
    return "warn";
  }
  if (type === "candidate_run_completed" || type === "optimizer_completed" || type === "optimizer_baseline_loaded") {
    return "ok";
  }
  return "info";
}

function eventPhase(event) {
  const type = String(event?.event_type || "").toLowerCase();
  if (type.startsWith("optimizer_run_") || type === "optimizer_started") return "Setup";
  if (type === "optimizer_baseline_loaded") return "Baseline";
  if (type === "optimizer_attempt_started" || type === "optimizer_attempt_completed" || type === "optimizer_no_frontier_remaining") return "Attempt";
  if (type === "optimizer_parent_diagnosis_loaded") return "Diagnosis";
  if (type === "candidate_seeds_prepared" || type === "optimizer_parent_no_candidate_seeds" || type === "candidate_deduped" || type === "candidate_version_created") return "Candidate";
  if (type === "backtest_run_launched") return "Rerun";
  if (type === "candidate_run_completed" || type === "candidate_run_failed") return "Evaluation";
  return "Finish";
}

function eventTitle(event) {
  const type = String(event?.event_type || "").toLowerCase();
  switch (type) {
    case "optimizer_run_created":
      return `Configured Auto Optimize from baseline ${event?.baseline_run_id || "-"}.`;
    case "optimizer_started":
      return "Started parameter-only beam search.";
    case "optimizer_baseline_loaded":
      return `Loaded baseline node-root from run ${event?.run_id || "-"}.`;
    case "optimizer_attempt_started":
      return `Attempt ${event?.attempt_index || "-"} selected ${event?.frontier_node_ids?.length || 0} frontier node(s).`;
    case "optimizer_parent_diagnosis_loaded":
      return `Loaded diagnosis for parent ${event?.parent_node_id || "-"}.`;
    case "candidate_seeds_prepared":
      return `Prepared ${event?.seed_count || 0} parameter-only seed(s) for ${event?.parent_node_id || "-"}.`;
    case "optimizer_parent_no_candidate_seeds":
      return `No parameter-only seeds were produced for ${event?.parent_node_id || "-"}.`;
    case "candidate_deduped":
      return `Skipped duplicate candidate ${formatDescriptor(event?.candidate_descriptor)}.`;
    case "candidate_version_created":
      return `Staged candidate version ${event?.version_id || "-"}.`;
    case "backtest_run_launched":
      return `Launched isolated rerun ${event?.run_id || "-"}.`;
    case "candidate_run_completed":
      return `Candidate run ${event?.run_id || "-"} completed.`;
    case "candidate_run_failed":
      return `Candidate run ${event?.run_id || event?.error?.run_id || "-"} failed.`;
    case "optimizer_attempt_completed":
      return `Attempt ${event?.attempt_index || "-"} finished.`;
    case "optimizer_no_frontier_remaining":
      return "No frontier nodes remain to expand.";
    case "optimizer_hard_stop_triggered":
      return `Optimization stopped by hard stop: ${formatHardStopReason(event?.hard_stop_reason)}.`;
    case "optimizer_stop_requested":
      return "Stop requested for the current optimizer run.";
    case "optimizer_completed":
      return `Optimization completed with ${event?.finalists?.length || 0} finalist(s).`;
    case "optimizer_completed_no_finalists":
      return "Optimization completed without profitable finalists.";
    case "optimizer_failed":
      return "Optimization failed before finalists were produced.";
    default:
      return String(event?.event_type || "optimizer event").replace(/_/g, " ");
  }
}

function eventDetail(event) {
  const type = String(event?.event_type || "").toLowerCase();
  switch (type) {
    case "optimizer_run_created":
      return `Attempts ${event?.attempts || "-"}, beam width ${event?.beam_width || "-"}, branch factor ${event?.branch_factor || "-"}, AI ${event?.include_ai_suggestions ? "enabled" : "disabled"}. Thresholds: ${thresholdSummary(event?.thresholds)}. Hard stops: ${hardStopSummary(event?.hard_stops)}.`;
    case "optimizer_started":
      return "The optimizer now loads the baseline summary, scores node-root, and expands the strongest completed nodes first.";
    case "optimizer_baseline_loaded":
      return `Baseline version ${event?.version_id || "-"} is the search anchor. It is scored before any candidate mutations are staged.`;
    case "optimizer_attempt_started": {
      const frontier = Array.isArray(event?.frontier_nodes) ? event.frontier_nodes : [];
      const chosen = frontier.length
        ? frontier.map((node) => `${node.node_id}${node.score != null ? ` (score ${formatNumber(node.score)})` : ""}`).join(", ")
        : "no frontier nodes";
      return `Beam search expands the best completed nodes first. This attempt is exploring: ${chosen}.`;
    }
    case "optimizer_parent_diagnosis_loaded":
      return `Deterministic diagnosis found ${event?.proposal_action_count || 0} action(s). AI status is ${event?.ai_status || "unavailable"} with ${event?.ai_suggestion_count || 0} suggestion(s).`;
    case "candidate_seeds_prepared":
      return "Each seed is a parameter-only mutation. A seed must be staged as a candidate version and rerun from that exact version before it can compete.";
    case "optimizer_parent_no_candidate_seeds":
      return "Diagnosis actions and fallback nudges did not yield a parameter mutation for this parent, so the search moved on.";
    case "candidate_deduped":
      return "This normalized parameter snapshot was already staged earlier, so no duplicate version or rerun was created.";
    case "candidate_version_created":
      return `Candidate ${event?.version_id || "-"} was staged from ${formatDescriptor(event?.candidate_descriptor)}. Live strategy files were not touched.`;
    case "backtest_run_launched":
      return `Run ${event?.run_id || "-"} is an isolated rerun pinned to candidate version ${event?.version_id || "-"}.`;
    case "candidate_run_completed":
      return event?.constraint_passed
        ? "The rerun cleared every optimizer threshold and remains eligible for the finalist set."
        : "The rerun finished, but one or more thresholds failed so it can only be treated as a near miss.";
    case "candidate_run_failed":
      return String(event?.error?.message || "The candidate backtest could not produce a ready summary.");
    case "optimizer_attempt_completed":
      return event?.improved
        ? `This attempt improved the best score from ${formatNumber(event?.best_score_before)} to ${formatNumber(event?.best_score_after)}.`
        : `No better score was found in this attempt. Consecutive no-improve attempts: ${event?.consecutive_no_improve || 0}.`;
    case "optimizer_no_frontier_remaining":
      return "All eligible completed nodes were already expanded or none had a usable score, so the beam search exhausted its frontier early.";
    case "optimizer_hard_stop_triggered":
      return `The optimizer stopped because ${formatHardStopReason(event?.hard_stop_reason)} was reached.`;
    case "optimizer_stop_requested":
      return `The service signaled ${Array.isArray(event?.stopped_child_run_ids) ? event.stopped_child_run_ids.length : 0} running child backtest(s) to stop.`;
    case "optimizer_completed":
      return "Finalists are the strongest completed candidates that also passed the configured thresholds.";
    case "optimizer_completed_no_finalists":
      return "The search finished, but no rerun cleared the configured thresholds strongly enough to be promoted as a finalist.";
    case "optimizer_failed":
      return String(event?.error?.message || "Optimizer loop failed.");
    default:
      return "";
  }
}
function renderInfoChips(items, extraClass = "") {
  const filtered = items.filter((item) => item && item.value != null && item.value !== "");
  if (!filtered.length) return "";
  return `
    <div class="auto-opt-event__chips ${extraClass}">
      ${filtered.map((item) => `<span class="auto-opt-chip${item.tone ? ` auto-opt-chip--${escapeHtml(item.tone)}` : ""}"><strong>${escapeHtml(item.label)}:</strong> ${escapeHtml(item.value)}</span>`).join("")}
    </div>
  `;
}

function renderMetricChips(metrics, score, failedConstraints = []) {
  const data = metrics && typeof metrics === "object" ? metrics : {};
  return renderInfoChips([
    { label: "Profit", value: formatMetricValue("profit_total_pct", data.profit_total_pct), tone: "ok" },
    { label: "Drawdown", value: formatMetricValue("max_drawdown_pct", data.max_drawdown_pct), tone: failedConstraints.length ? "warn" : "info" },
    { label: "Win rate", value: formatMetricValue("win_rate", data.win_rate), tone: "info" },
    { label: "Trades", value: formatMetricValue("total_trades", data.total_trades), tone: "info" },
    { label: "Score", value: score == null ? "-" : formatNumber(score), tone: "info" },
  ], "auto-opt-event__chips--metrics");
}

function renderConstraintChips(failedConstraints) {
  const failed = Array.isArray(failedConstraints) ? failedConstraints : [];
  if (!failed.length) {
    return renderInfoChips([{ label: "Thresholds", value: "all passed", tone: "ok" }]);
  }
  return renderInfoChips(failed.map((item) => ({ label: "Threshold", value: formatConstraintName(item), tone: "warn" })));
}

function renderParameterChanges(changes, totalCount, truncated) {
  const rows = Array.isArray(changes) ? changes : [];
  if (!rows.length) return "";
  const extra = Math.max((Number(totalCount) || rows.length) - rows.length, 0);
  return `
    <div class="auto-opt-event__changes">
      ${rows.map((change) => `<span class="auto-opt-chip auto-opt-chip--info"><strong>${escapeHtml(change.path || "parameter")}:</strong> ${escapeHtml(change.before ?? "-")} -> ${escapeHtml(change.after ?? "-")}</span>`).join("")}
      ${truncated || extra > 0 ? `<span class="auto-opt-chip"><strong>More:</strong> +${escapeHtml(extra || "more")}</span>` : ""}
    </div>
  `;
}

function renderSeedSummaries(event) {
  const seeds = Array.isArray(event?.seeds) ? event.seeds : [];
  if (!seeds.length) return "";
  return `
    <div class="auto-opt-event__seed-list">
      ${seeds.map((seed) => `
        <div class="auto-opt-event__seed">
          <div class="auto-opt-event__seed-title">${escapeHtml(formatDescriptor(seed?.candidate_descriptor))}</div>
          ${renderParameterChanges(seed?.parameter_changes, seed?.parameter_change_count, seed?.parameter_changes_truncated)}
        </div>
      `).join("")}
    </div>
  `;
}

function renderEventSupplement(event) {
  const type = String(event?.event_type || "").toLowerCase();

  if (type === "optimizer_baseline_loaded" || type === "candidate_run_completed") {
    return `${renderMetricChips(event?.summary_metrics, event?.score, event?.failed_constraints)}${renderConstraintChips(event?.failed_constraints)}`;
  }

  if (type === "candidate_version_created") {
    return renderParameterChanges(event?.parameter_changes, event?.parameter_change_count, event?.parameter_changes_truncated);
  }

  if (type === "candidate_seeds_prepared") {
    return renderSeedSummaries(event);
  }

  if (type === "optimizer_attempt_completed") {
    return renderInfoChips([
      { label: "Attempt nodes", value: event?.attempt_node_count ?? 0 },
      { label: "Completed", value: event?.attempt_completed_nodes ?? 0, tone: "ok" },
      { label: "Failed", value: event?.attempt_failed_nodes ?? 0, tone: event?.attempt_failed_nodes ? "warn" : "info" },
      { label: "Deduped", value: event?.attempt_deduped_nodes ?? 0 },
      { label: "Best before", value: event?.best_score_before == null ? "-" : formatNumber(event.best_score_before) },
      { label: "Best after", value: event?.best_score_after == null ? "-" : formatNumber(event.best_score_after), tone: event?.improved ? "ok" : "info" },
    ]);
  }

  if (type === "optimizer_attempt_started") {
    const frontier = Array.isArray(event?.frontier_nodes) ? event.frontier_nodes : [];
    return renderInfoChips(frontier.map((node) => ({
      label: node?.node_id || "node",
      value: node?.score == null ? (node?.run_id || "selected") : `score ${formatNumber(node.score)}`,
      tone: node?.constraint_passed ? "ok" : "info",
    })));
  }

  if (type === "optimizer_completed" || type === "optimizer_completed_no_finalists" || type === "optimizer_hard_stop_triggered") {
    const finalists = Array.isArray(event?.finalists) ? event.finalists : [];
    return renderInfoChips([
      { label: "Finalists", value: finalists.length, tone: finalists.length ? "ok" : "warn" },
      { label: "Near misses", value: Array.isArray(event?.near_misses) ? event.near_misses.length : 0 },
      { label: "Total nodes", value: event?.total_nodes ?? 0 },
      { label: "Best score", value: event?.best_score == null ? "-" : formatNumber(event.best_score), tone: finalists.length ? "ok" : "info" },
    ]);
  }

  if (type === "candidate_run_failed" || type === "optimizer_failed") {
    const err = event?.error || {};
    return renderInfoChips([
      { label: "Stage", value: err?.error_stage || "-", tone: "warn" },
      { label: "Code", value: err?.error_code || "-", tone: "warn" },
      { label: "Version", value: err?.details?.version_id || event?.version_id || "-" },
      { label: "Descriptor", value: err?.details?.candidate_descriptor || event?.candidate_descriptor || "-" },
    ]);
  }

  if (type === "optimizer_run_created") {
    return renderInfoChips([
      { label: "Attempts", value: event?.attempts ?? defaults.attempts },
      { label: "Beam width", value: event?.beam_width ?? defaults.beamWidth },
      { label: "Branch factor", value: event?.branch_factor ?? defaults.branchFactor },
      { label: "AI", value: event?.include_ai_suggestions ? "enabled" : "disabled" },
    ]);
  }

  return "";
}

function renderTimeline() {
  if (!optimizerEvents.length) {
    return `
      <div class="auto-opt-empty">
        ${optimizerRunId
          ? "Waiting for optimizer events. The timeline will fill as the beam search stages candidates, reruns them, and scores the results."
          : "Start Auto Optimize to log each baseline load, beam selection, candidate seed, rerun, score update, and final outcome here."}
      </div>
    `;
  }

  const items = optimizerEvents
    .map((event, index) => {
      const tone = eventTone(event);
      const phase = eventPhase(event);
      const title = eventTitle(event);
      const detail = eventDetail(event);
      const timestamp = event?.created_at ? formatDate(event.created_at) : "";
      return `
        <article class="auto-opt-event auto-opt-event--${escapeHtml(tone)}">
          <div class="auto-opt-event__meta">
            <span class="auto-opt-event__phase">${escapeHtml(phase)}</span>
            <span class="auto-opt-event__time">${escapeHtml(timestamp || `Event ${index + 1}`)}</span>
          </div>
          <h4 class="auto-opt-event__title">${escapeHtml(title)}</h4>
          ${detail ? `<div class="auto-opt-event__detail">${escapeHtml(detail)}</div>` : ""}
          ${renderEventSupplement(event)}
        </article>
      `;
    })
    .join("");

  return `<div class="auto-opt-timeline__list">${items}</div>`;
}

function renderExplainer() {
  const steps = [
    ["1. Load baseline", "Anchor the search to the currently loaded completed baseline run and score node-root against the optimizer thresholds."],
    ["2. Pick frontier nodes", "Use beam width to expand the strongest completed nodes first instead of branching from every prior candidate."],
    ["3. Prepare parameter seeds", "Generate parameter-only candidate seeds from deterministic diagnosis actions plus optional AI suggestions and nudges."],
    ["4. Dedup and stage", "Skip normalized duplicate snapshots, then stage each surviving mutation as a new candidate version without touching live files."],
    ["5. Re-run exact versions", "Launch isolated backtests from the staged candidate versions so every result stays tied to the exact version_id used."],
    ["6. Score and stop", "Score completed runs, keep finalists and near misses, and stop when hard-stop limits or search exhaustion say the loop is done."],
  ];

  return `
    <div class="auto-opt-explainer">
      ${steps.map(([title, detail]) => `
        <div class="auto-opt-explainer__step">
          <div class="auto-opt-explainer__title">${escapeHtml(title)}</div>
          <div class="auto-opt-explainer__detail">${escapeHtml(detail)}</div>
        </div>
      `).join("")}
    </div>
  `;
}
function renderFinalists(record) {
  const finalists = Array.isArray(record?.finalists) ? record.finalists : [];
  if (!finalists.length) {
    return '<div class="info-empty">No finalists yet.</div>';
  }

  const rows = finalists
    .map((item) => {
      const metrics = item?.summary_metrics || {};
      return `
        <tr>
          <td><code>${escapeHtml(item?.version_id || "-")}</code></td>
          <td><code>${escapeHtml(item?.run_id || "-")}</code></td>
          <td>${escapeHtml(formatPct(metrics?.profit_total_pct))}</td>
          <td>${escapeHtml(formatPct(metrics?.max_drawdown_pct))}</td>
          <td>${escapeHtml(metrics?.total_trades ?? "-")}</td>
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
      const why = failed.length ? `Failed: ${failed.map((value) => formatConstraintName(value)).join(", ")}` : "";
      const descriptor = item?.candidate_descriptor ? ` | ${item.candidate_descriptor}` : "";
      return `<li><code>${escapeHtml(item?.version_id || "-")}</code>${escapeHtml(descriptor)} ${escapeHtml(why)}</li>`;
    })
    .join("");

  return `
    <div class="results-context__note auto-opt-note-block">
      <div class="auto-opt-section-title">Near Misses</div>
      <ul class="diagnosis-list">${items}</ul>
    </div>
  `;
}

function render() {
  if (!root) return;

  const hasBaseline = Boolean(baselineRunId);
  const record = lastRecord;
  const status = String(record?.status || (optimizerRunId ? "queued" : "idle")).toLowerCase();
  const terminal = isTerminalStatus(status);
  const counts = record ? summarizeCounts(record) : { total: 0, completed: 0, failed: 0, deduped: 0 };
  const errorBlock = record?.error
    ? `<div class="results-context__note auto-opt-error">${escapeHtml(record?.error?.message || "Optimizer error")}</div>`
    : "";
  const disabled = busy || !hasBaseline || (!terminal && Boolean(optimizerRunId));

  root.innerHTML = `
    <section class="results-context results-context--workflow-guide auto-opt-shell">
      <div class="results-context__title">Auto Optimize</div>
      <div class="results-context__note">Parameter-only beam search anchored to the currently loaded baseline run.</div>
      <div class="results-context__meta">
        <span><strong>Baseline run</strong><br/><code>${escapeHtml(baselineRunId || "-")}</code></span>
        <span><strong>Baseline version</strong><br/><code>${escapeHtml(baselineVersionId || "-")}</code></span>
        <span><strong>Status</strong><br/>${escapeHtml(status)}</span>
        <span><strong>Nodes</strong><br/>${escapeHtml(`${counts.total} total | ${counts.completed} completed | ${counts.failed} failed | ${counts.deduped} deduped`)}</span>
      </div>

      <div class="auto-opt-controls">
        <div class="sidebar-subgrid auto-opt-grid">
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
          <div class="setup-field auto-opt-checkbox">
            <label class="form-label form-label--sub" for="auto-opt-ai">Include AI</label>
            <input type="checkbox" id="auto-opt-ai" ${defaults.includeAI ? "checked" : ""} ${disabled ? "disabled" : ""} />
          </div>
        </div>

        <div class="sidebar-subgrid auto-opt-grid auto-opt-grid--secondary">
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

        <div class="action-group auto-opt-actions">
          <button class="btn btn--primary btn--sm" id="auto-opt-start" ${disabled ? "disabled" : ""}>Start Auto Optimize</button>
          <button class="btn btn--secondary btn--sm" id="auto-opt-pause" ${!optimizerRunId ? "disabled" : ""}>
            ${paused ? "Resume" : "Pause"}
          </button>
          ${optimizerRunId ? `<span class="field-hint">Run: <code>${escapeHtml(optimizerRunId)}</code></span>` : ""}
        </div>
      </div>

      ${errorBlock}
      ${paused ? `<div class="results-context__note auto-opt-note-block">Optimizer event display is paused. New events are buffered and will appear when you resume.</div>` : ""}

      <div class="auto-opt-section">
        <div class="auto-opt-section-title">How Auto Optimize works</div>
        <div class="results-context__note">The log below uses the persisted optimizer events so you can see what the beam search did, why it staged each candidate, and how every rerun finished.</div>
        ${renderExplainer()}
      </div>

      <div class="auto-opt-section">
        <div class="auto-opt-section-header">
          <div>
            <div class="auto-opt-section-title">Auto Optimize Timeline</div>
            <div class="results-context__note">Every persisted optimizer event is listed in order so you can see how the search moved from baseline to finalists.</div>
          </div>
          <span class="auto-opt-event-count">${escapeHtml(optimizerEvents.length)} event${optimizerEvents.length === 1 ? "" : "s"}</span>
        </div>
        ${renderTimeline()}
      </div>

      <div class="auto-opt-section">
        <div class="auto-opt-section-title">Finalists</div>
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

  root.querySelector("#auto-opt-start")?.addEventListener("click", async () => {
    if (!baselineRunId) {
      showToast("Run a baseline backtest first.", "warning");
      return;
    }

    busy = true;
    render();

    try {
      const response = await api.optimizer.startRun({
        baseline_run_id: baselineRunId,
        attempts: coerceInt(root.querySelector("#auto-opt-attempts")?.value, defaults.attempts),
        beam_width: coerceInt(root.querySelector("#auto-opt-beam")?.value, defaults.beamWidth),
        branch_factor: coerceInt(root.querySelector("#auto-opt-branch")?.value, defaults.branchFactor),
        include_ai_suggestions: Boolean(root.querySelector("#auto-opt-ai")?.checked),
        thresholds: {
          min_profit_total_pct: coerceFloat(root.querySelector("#auto-opt-min-profit")?.value, defaults.minProfitTotalPct),
          min_total_trades: coerceInt(root.querySelector("#auto-opt-min-trades")?.value, defaults.minTotalTrades),
          max_allowed_drawdown_pct: coerceFloat(root.querySelector("#auto-opt-max-dd")?.value, defaults.maxAllowedDrawdownPct),
        },
      });

      optimizerRunId = response?.optimizer_run_id || "";
      lastRecord = null;
      busy = false;
      resetEventLog();
      showToast(`Auto Optimize started (${escapeHtml(optimizerRunId)})`, "info");
      render();
      startPolling();
    } catch (error) {
      optimizerRunId = "";
      lastRecord = null;
      busy = false;
      resetEventLog();
      stopPolling();
      stopEventStream();
      showToast(`Auto Optimize failed to start: ${escapeHtml(error?.message || String(error))}`, "error", 8000);
      render();
    }
  });

  root.querySelector("#auto-opt-pause")?.addEventListener("click", () => {
    if (!optimizerRunId) return;
    paused = !paused;
    if (!paused) {
      flushPausedEvents();
    }
    render();
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
      stopEventStream();
      resetEventLog();
    }
    render();
  });

  render();
}
