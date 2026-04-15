/**
 * results-controller.js - Loads run-scoped diagnosis and fans out the latest ready result payload.
 */

import api from "../../../core/api.js";
import { getState, on as onState } from "../../../core/state.js";
import { on, emit, EVENTS } from "../../../core/events.js";
import { renderSummaryCards } from "../../shared/backtest/result_renderer.js";
import { activateBacktestTab } from "../bootstrap.js";
import { getSelectedCandidateVersionId, getWorkflowCandidateVersions } from "../compare/candidate-selection-state.js";
import { initPersistedRunsStore, subscribePersistedRuns } from "./persisted-runs-store.js";
import { initPersistedVersionsStore, subscribePersistedVersions } from "./persisted-versions-store.js";

const summaryCards = document.getElementById("summary-cards");
const summaryWorkflowGuide = document.getElementById("summary-workflow-guide");
const diagnosisPanel = document.getElementById("summary-diagnosis");

let latestResultsPayload = null;
let lastReadyPayload = null;
let currentStrategy = "";
let selectedRunId = null;
let requestId = 0;
let runsSnapshot = { status: "idle", strategy: "", runs: [], error: null };
let versionsSnapshot = { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };

export function getLatestResultsPayload() {
  return latestResultsPayload;
}

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatConfidence(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  return `${Math.round(number * 100)}%`;
}

function resolveMappedAction(diagnosis, rule) {
  const normalizedRule = String(rule || "").trim();
  if (!normalizedRule) return null;
  const actions = Array.isArray(diagnosis?.proposal_actions) ? diagnosis.proposal_actions : [];
  return actions.find((item) => Array.isArray(item?.matched_rules) && item.matched_rules.includes(normalizedRule)) || null;
}

function describeIssueActionability(diagnosis, rule) {
  const mappedAction = resolveMappedAction(diagnosis, rule);
  if (mappedAction) {
    return {
      label: "Actionable now",
      reason: `Candidate path available via ${mappedAction?.label || labelize(mappedAction?.action_type || "deterministic action")}.`,
    };
  }
  return {
    label: "Diagnostic only",
    reason: "No direct candidate action is mapped for this issue yet.",
  };
}

function resolveStrategyBlock(summary, strategy) {
  if (!isObject(summary)) return null;

  const direct = summary?.[strategy];
  if (isObject(direct)) return direct;

  for (const [key, value] of Object.entries(summary)) {
    if (key === "strategy_comparison") continue;
    if (isObject(value)) return value;
  }

  return null;
}

function makeEmptyPayload(strategy = "") {
  return {
    strategy,
    run_id: null,
    version_id: null,
    summary: null,
    summary_metrics: null,
    diagnosis_status: "pending_summary",
    summary_available: false,
    diagnosis: null,
    ai: null,
    error: null,
    trades: [],
    results_per_pair: [],
  };
}

function buildResultsPayload(response) {
  const strategy = response?.strategy || getState("backtest.strategy") || "";
  const summary = response?.summary ?? null;
  const block = resolveStrategyBlock(summary, strategy);
  return {
    strategy,
    run_id: response?.run_id ?? null,
    version_id: response?.version_id ?? null,
    summary,
    summary_metrics: response?.summary_metrics ?? null,
    diagnosis_status: response?.diagnosis_status ?? "pending_summary",
    summary_available: Boolean(response?.summary_available),
    diagnosis: response?.diagnosis ?? null,
    ai: response?.ai ?? null,
    error: response?.error ?? null,
    trades: Array.isArray(block?.trades) ? block.trades : [],
    results_per_pair: Array.isArray(block?.results_per_pair) ? block.results_per_pair : [],
  };
}

function currentWorkflowSourceRef(payload = latestResultsPayload) {
  const runId = payload?.run_id || "";
  return runId ? `backtest_run:${runId}` : "";
}

function workflowVersionsForPayload(payload = latestResultsPayload) {
  const sourceRef = currentWorkflowSourceRef(payload);
  if (!sourceRef || !Array.isArray(versionsSnapshot.versions)) return [];
  return versionsSnapshot.versions
    .filter((version) => version?.source_ref === sourceRef)
    .slice()
    .sort((left, right) => String(right?.created_at || "").localeCompare(String(left?.created_at || "")));
}

function pendingWorkflowVersions(payload = latestResultsPayload) {
  return getWorkflowCandidateVersions(versionsSnapshot.versions, payload?.run_id || "");
}

function currentWorkflowVersion(payload = latestResultsPayload) {
  const pendingVersions = pendingWorkflowVersions(payload);
  const selectedCandidateId = getSelectedCandidateVersionId(payload?.run_id || "");
  const selectedPending = pendingVersions.find((version) => version?.version_id === selectedCandidateId);
  if (selectedPending) return selectedPending;
  if (pendingVersions[0]) return pendingVersions[0];
  return workflowVersionsForPayload(payload)[0] || null;
}

function workflowRunsForVersion(versionId) {
  if (!versionId) return [];
  return (Array.isArray(runsSnapshot.runs) ? runsSnapshot.runs : [])
    .filter((run) => run?.version_id === versionId)
    .slice()
    .sort((left, right) => String(right?.completed_at || right?.created_at || "").localeCompare(String(left?.completed_at || left?.created_at || "")));
}

function comparableWorkflowRun(payload = latestResultsPayload) {
  const currentVersion = currentWorkflowVersion(payload);
  const comparableForCurrent = workflowRunsForVersion(currentVersion?.version_id).find((run) => run?.status === "completed" && run?.summary_available);
  if (comparableForCurrent) return comparableForCurrent;

  for (const version of workflowVersionsForPayload(payload)) {
    const comparable = workflowRunsForVersion(version?.version_id).find((run) => run?.status === "completed" && run?.summary_available);
    if (comparable) return comparable;
  }
  return null;
}

function latestWorkflowDecision(payload = latestResultsPayload) {
  const supported = new Set(["accepted", "rejected", "promoted_as_new_strategy"]);
  const decisions = workflowVersionsForPayload(payload).flatMap((version) => {
    const events = Array.isArray(version?.audit_events) ? version.audit_events : [];
    return events
      .filter((event) => supported.has(String(event?.event_type || "")))
      .map((event) => ({ version, event }));
  });

  decisions.sort((left, right) => String(right?.event?.created_at || "").localeCompare(String(left?.event?.created_at || "")));
  return decisions[0] || null;
}

function formatWorkflowDecision(decision) {
  if (!decision?.event) return "";
  return `${labelize(decision.event.event_type)} on ${decision?.version?.version_id || "the selected version"}`;
}

function buildWorkflowSteps(payload = latestResultsPayload) {
  const strategy = getState("backtest.strategy") || payload?.strategy || currentStrategy || "";
  const hasStrategy = Boolean(strategy);
  const hasReadyRun = Boolean(payload?.run_id && payload?.summary_available);
  const diagnosisReady = Boolean(payload?.diagnosis_status === "ready" && payload?.summary_available);
  const exactBaselineVersion = Boolean(payload?.version_id);
  const workflowVersions = workflowVersionsForPayload(payload);
  const currentVersion = currentWorkflowVersion(payload);
  const compareReadyRun = comparableWorkflowRun(payload);
  const latestDecision = latestWorkflowDecision(payload);
  const currentVersionLabel = currentVersion?.version_id || "No candidate yet";
  const compareRunLabel = compareReadyRun?.run_id || "No rerun yet";

  return [
    {
      title: "Configure Strategy",
      status: hasStrategy ? "done" : "current",
      note: hasStrategy
        ? `Current strategy is ${strategy}. Review configuration here before changing the workflow baseline.`
        : "Choose the strategy, timeframe, timerange, and pairs you want to validate.",
      action: "open-setup",
      actionLabel: hasStrategy ? "Review Configuration" : "Open Configuration",
    },
    {
      title: "Run Backtest",
      status: !hasStrategy ? "locked" : hasReadyRun ? "done" : "current",
      note: !hasStrategy
        ? "Select a strategy first. The baseline run powers diagnosis, candidate creation, and compare."
        : hasReadyRun
          ? `Baseline run ${payload?.run_id || "-"} is loaded and ready for diagnosis.`
          : "Run a backtest to create the baseline run that drives diagnosis, candidates, and compare.",
      action: "focus-run",
      actionLabel: hasReadyRun ? "Review Run Controls" : "Run Backtest",
    },
    {
      title: "Review Diagnosis",
      status: !hasReadyRun ? "locked" : diagnosisReady ? "done" : "current",
      note: !hasReadyRun
        ? "Diagnosis unlocks after a completed run with a persisted summary artifact is available."
        : diagnosisReady
          ? "Start with Primary Issues and use Actionable now items as the first candidate path."
          : "Wait for persisted summary and diagnosis to finish loading, then review Primary Issues before changing anything.",
      action: "review-diagnosis",
      actionLabel: "Review Diagnosis",
    },
    {
      title: "Create Candidate",
      status: !diagnosisReady ? "locked" : workflowVersions.length ? "done" : "current",
      note: !diagnosisReady
        ? "Candidate staging stays locked until diagnosis is ready."
        : workflowVersions.length
          ? `Workflow version ${currentVersionLabel} is already staged from this baseline.`
          : "Open Proposal Workflow and start with Actionable now items. Diagnostic-only items explain the run but do not stage a candidate path.",
      action: "open-proposals",
      actionLabel: workflowVersions.length ? "Review Proposal Workflow" : "Open Proposal Workflow",
    },
    {
      title: "Re-run & Compare",
      status: !workflowVersions.length ? "locked" : compareReadyRun ? "done" : "current",
      note: !workflowVersions.length
        ? "Stage a candidate first. Re-run and compare stay locked until a workflow version exists."
        : compareReadyRun
          ? `Persisted rerun ${compareRunLabel} is ready for baseline-vs-candidate compare.`
          : "Re-run the selected candidate to create a persisted summary-backed run, then compare baseline vs selected candidate.",
      action: compareReadyRun ? "open-compare" : "focus-rerun",
      actionLabel: compareReadyRun ? "Open Compare" : "Re-run Candidate",
    },
    {
      title: "Decide Version",
      status: !compareReadyRun ? "locked" : latestDecision ? "done" : "current",
      note: !compareReadyRun
        ? "Decision actions unlock after compare evidence is grounded in a persisted candidate rerun."
        : latestDecision
          ? `Latest decision: ${formatWorkflowDecision(latestDecision)}. Confirm the note snippet and timeline in History.`
          : exactBaselineVersion
            ? `Use Accept as current strategy or Promote as new strategy variant. Default to Promote as new strategy when you want to preserve the original ${strategy || "strategy"}.`
            : "Compare is ready, but accept and rollback remain disabled until the baseline run is linked to an exact version.",
      action: latestDecision ? "open-history" : "review-decision",
      actionLabel: latestDecision ? "Open History" : "Review Decision Actions",
    },
  ];
}

function renderWorkflowStep(step, index) {
  const statusLabel = step.status === "done" ? "Done" : step.status === "current" ? "Current" : "Locked";
  const buttonClass = step.status === "current" ? "btn btn--secondary btn--sm" : "btn btn--ghost btn--sm";
  return `
    <article class="workflow-step workflow-step--${escapeHtml(step.status)}">
      <div class="workflow-step__header">
        <span class="workflow-step__index">${index + 1}</span>
        <div class="workflow-step__copy">
          <div class="workflow-step__title-row">
            <h3 class="workflow-step__title">${escapeHtml(step.title)}</h3>
            <span class="workflow-step__badge workflow-step__badge--${escapeHtml(step.status)}">${escapeHtml(statusLabel)}</span>
          </div>
          <p class="workflow-step__note">${escapeHtml(step.note)}</p>
        </div>
      </div>
      <div class="workflow-step__actions">
        <button type="button" class="${buttonClass}" data-workflow-action="${escapeHtml(step.action)}">${escapeHtml(step.actionLabel)}</button>
      </div>
    </article>
  `;
}

function renderWorkflowGuide(payload = latestResultsPayload) {
  if (!summaryWorkflowGuide) return;

  const strategy = getState("backtest.strategy") || payload?.strategy || currentStrategy || "";
  const intro = strategy
    ? `Follow the same version-safe loop every time for ${strategy}: review diagnosis, stage a candidate, re-run it, compare baseline vs selected candidate, then decide. Promote as new strategy variant is the safest default when you want to preserve the original.`
    : "Select a strategy first. The guided workflow below becomes state-aware as soon as the backtesting page has enough context.";

  const steps = buildWorkflowSteps(payload);
  summaryWorkflowGuide.innerHTML = `
    <section class="results-context results-context--workflow-guide">
      <div class="results-context__title">Workflow Guide</div>
      <div class="results-context__note">${escapeHtml(intro)}</div>
      <div class="workflow-stepper">
        ${steps.map((step, index) => renderWorkflowStep(step, index)).join("")}
      </div>
    </section>
  `;
}

function renderSummary(payload) {
  const summarySource = payload?.summary ?? lastReadyPayload?.summary ?? null;
  renderSummaryCards(summaryCards, summarySource, { expanded: true });
  renderWorkflowGuide(payload || latestResultsPayload || makeEmptyPayload(currentStrategy || getState("backtest.strategy") || ""));
}

function renderSeverityBadge(severity) {
  const sev = String(severity || "").toLowerCase();
  const klass = sev === "critical" ? "diagnosis-severity-badge diagnosis-severity-badge--critical" 
    : sev === "warning" ? "diagnosis-severity-badge diagnosis-severity-badge--warning" 
    : "diagnosis-severity-badge diagnosis-severity-badge--info";
  return `<span class="${klass}">${escapeHtml(sev)}</span>`;
}

function renderIssueCard(issue, index) {
  const severity = String(issue?.severity || "warning").toLowerCase();
  const klass = severity === "critical" ? "diagnosis-issue-card diagnosis-issue-card--critical" : "diagnosis-issue-card diagnosis-issue-card--warning";
  const rule = issue?.rule || "issue";
  const message = issue?.message || "";
  const actual = issue?.actual;
  const warning_threshold = issue?.warning_threshold;
  const critical_threshold = issue?.critical_threshold;
  const threshold_distance = issue?.threshold_distance;
  const facts = issue?.facts || {};
  
  let metricsHtml = "";
  if (typeof actual === "object" && actual !== null) {
    const parts = [];
    if (actual.avg_loss_duration_hours && actual.avg_win_duration_hours) {
      parts.push(`<span class="diagnosis-issue-card__metric"><span class="diagnosis-issue-card__metric-label">Hold time</span><span class="diagnosis-issue-card__metric-value">${actual.avg_loss_duration_hours.toFixed(1)}h vs ${actual.avg_win_duration_hours.toFixed(1)}h</span></span>`);
    }
    if (actual.avg_mfe_captured_pct) {
      parts.push(`<span class="diagnosis-issue-card__metric"><span class="diagnosis-issue-card__metric-label">MFE captured</span><span class="diagnosis-issue-card__metric-value">${actual.avg_mfe_captured_pct.toFixed(1)}%</span></span>`);
    }
    if (parts.length) metricsHtml = `<div class="diagnosis-issue-card__metrics">${parts.join("")}</div>`;
  } else if (actual != null && warning_threshold != null) {
    const threshold = critical_threshold != null ? critical_threshold : warning_threshold;
    const isNegative = rule === "negative_profit" || rule === "high_drawdown" || rule === "low_sample_size";
    const pct = Math.min(Math.abs(actual) / Math.abs(threshold) * 100, 100);
    const barKlass = severity === "critical" ? "diagnosis-metric-bar__fill--critical" : severity === "warning" ? "diagnosis-metric-bar__fill--warning" : "diagnosis-metric-bar__fill--ok";
    metricsHtml = `
      <div class="diagnosis-issue-card__metrics">
        <div class="diagnosis-issue-card__metric">
          <span class="diagnosis-issue-card__metric-label">Value vs Threshold</span>
          <div class="diagnosis-metric-bar">
            <div class="diagnosis-metric-bar__track">
              <div class="diagnosis-metric-bar__fill ${barKlass}" style="width: ${pct}%"></div>
            </div>
            <div class="diagnosis-metric-bar__labels">
              <span>${typeof actual === "number" ? actual.toFixed(2) : "-"}</span>
              <span>Threshold: ${threshold}</span>
            </div>
          </div>
        </div>
        ${threshold_distance != null ? `<span class="diagnosis-issue-card__metric"><span class="diagnosis-issue-card__metric-label">Distance</span><span class="diagnosis-issue-card__metric-value">${threshold_distance >= 0 ? "+" : ""}${Number(threshold_distance).toFixed(2)}</span></span>` : ""}
      </div>
    `;
  }

  const actionability = describeIssueActionability(diagnosis, rule);
  const actionHtml = actionability.label === "Actionable now" 
    ? `<div style="margin-top: var(--space-2);"><span class="proposal-status-chip proposal-status-chip--actionable">${escapeHtml(actionability.label)}</span></div>`
    : `<div style="margin-top: var(--space-2);"><span class="proposal-status-chip proposal-status-chip--advisory">${escapeHtml(actionability.label)}</span></div>`;

  return `
    <div class="${klass}">
      <div class="diagnosis-issue-card__header">
        <div style="display: flex; align-items: center; gap: var(--space-2);">
          ${renderSeverityBadge(severity)}
          <span class="diagnosis-issue-card__title">${escapeHtml(labelize(rule))}</span>
        </div>
      </div>
      <div class="diagnosis-issue-card__message">${escapeHtml(message)}</div>
      ${metricsHtml}
      ${actionHtml}
    </div>
  `;
}

function renderActionCard(action) {
  const label = action?.label || "Action";
  const summary = action?.summary || "";
  const matched_rules = Array.isArray(action?.matched_rules) ? action.matched_rules : [];
  return `
    <div class="diagnosis-action-card">
      <span class="diagnosis-action-card__title">${escapeHtml(label)}</span>
      <span class="diagnosis-action-card__summary">${escapeHtml(summary)}</span>
      ${matched_rules.length ? `<div class="diagnosis-action-card__rules">${matched_rules.map(r => `<span class="diagnosis-action-card__rule">${escapeHtml(r)}</span>`).join("")}</div>` : ""}
    </div>
  `;
}

function renderMetricBar(fact, threshold, label) {
  const value = fact?.[label.toLowerCase().replace(/ /g, "_")];
  if (value == null) return "";
  const thresholdVal = threshold || value * 1.2;
  const pct = Math.min((Math.abs(value) / Math.abs(thresholdVal)) * 100, 100);
  const barKlass = pct > 80 ? "diagnosis-metric-bar__fill--critical" : pct > 50 ? "diagnosis-metric-bar__fill--warning" : "diagnosis-metric-bar__fill--ok";
  return `
    <div class="diagnosis-issue-card__metric">
      <span class="diagnosis-issue-card__metric-label">${escapeHtml(label)}</span>
      <div class="diagnosis-metric-bar">
        <div class="diagnosis-metric-bar__track">
          <div class="diagnosis-metric-bar__fill ${barKlass}" style="width: ${pct}%"></div>
        </div>
        <div class="diagnosis-metric-bar__labels">
          <span>${typeof value === "number" ? value.toFixed(2) : value}</span>
          <span>Threshold: ${thresholdVal}</span>
        </div>
      </div>
    </div>
  `;
}

function renderDiagnosis(response) {
  if (!diagnosisPanel) return;

  const strategy = response?.strategy || currentStrategy || getState("backtest.strategy") || "";
  const runId = response?.run_id || selectedRunId || "?";
  const versionId = response?.version_id || lastReadyPayload?.version_id || "?";
  const diagnosisStatus = response?.diagnosis_status || "pending_summary";
  const summaryAvailable = Boolean(response?.summary_available);
  const diagnosis = response?.diagnosis || null;
  const ai = response?.ai || null;
  const error = response?.error || null;

  const toneClass = diagnosisStatus === "ingestion_failed"
    ? " results-context--negative"
    : diagnosisStatus === "ready"
      ? " results-context--positive"
      : " results-context--empty";

  const facts = isObject(diagnosis?.facts) ? diagnosis.facts : {};
  const rankedIssues = Array.isArray(diagnosis?.ranked_issues) ? diagnosis.ranked_issues : [];
  const primaryFlags = Array.isArray(diagnosis?.primary_flags) ? diagnosis.primary_flags : [];
  const proposalActions = Array.isArray(diagnosis?.proposal_actions) ? diagnosis.proposal_actions : [];
  const insufficient = diagnosis?.insufficient_evidence && isObject(diagnosis.insufficient_evidence)
    ? Object.entries(diagnosis.insufficient_evidence)
    : [];
  const aiStatus = ai?.ai_status || "disabled";

  const summaryMetricsHtml = (() => {
    const items = [];
    if (facts.profit_total_pct != null) {
      const isNegative = facts.profit_total_pct < 0;
      items.push(`<div class="diagnosis-summary-item ${isNegative ? "diagnosis-summary-item--negative" : "diagnosis-summary-item--positive"}"><span class="diagnosis-summary-item__label">Profit</span><span class="diagnosis-summary-item__value">${facts.profit_total_pct.toFixed(2)}%</span></div>`);
    }
    if (facts.drawdown_pct != null) {
      const isHigh = facts.drawdown_pct > 15;
      items.push(`<div class="diagnosis-summary-item ${isHigh ? "diagnosis-summary-item--negative" : ""}"><span class="diagnosis-summary-item__label">Drawdown</span><span class="diagnosis-summary-item__value">${facts.drawdown_pct.toFixed(2)}%</span></div>`);
    }
    if (facts.win_rate_pct != null) {
      const isLow = facts.win_rate_pct < 35;
      items.push(`<div class="diagnosis-summary-item ${isLow ? "diagnosis-summary-item--negative" : ""}"><span class="diagnosis-summary-item__label">Win Rate</span><span class="diagnosis-summary-item__value">${facts.win_rate_pct.toFixed(2)}%</span></div>`);
    }
    if (facts.total_trades != null) {
      const isLow = facts.total_trades < 30;
      items.push(`<div class="diagnosis-summary-item ${isLow ? "diagnosis-summary-item--negative" : ""}"><span class="diagnosis-summary-item__label">Trades</span><span class="diagnosis-summary-item__value">${facts.total_trades}</span></div>`);
    }
    if (facts.avg_duration_hours != null) {
      const isLong = facts.avg_duration_hours > 12;
      items.push(`<div class="diagnosis-summary-item ${isLong ? "diagnosis-summary-item--negative" : ""}"><span class="diagnosis-summary-item__label">Avg Hold</span><span class="diagnosis-summary-item__value">${facts.avg_duration_hours.toFixed(1)}h</span></div>`);
    }
    if (facts.avg_mfe_captured_pct != null) {
      const isLow = facts.avg_mfe_captured_pct < 60;
      items.push(`<div class="diagnosis-summary-item ${isLow ? "diagnosis-summary-item--negative" : ""}"><span class="diagnosis-summary-item__label">MFE Captured</span><span class="diagnosis-summary-item__value">${facts.avg_mfe_captured_pct.toFixed(1)}%</span></div>`);
    }
    if (facts.worst_pair) {
      items.push(`<div class="diagnosis-summary-item diagnosis-summary-item--negative"><span class="diagnosis-summary-item__label">Worst Pair</span><span class="diagnosis-summary-item__value">${escapeHtml(facts.worst_pair)}</span></div>`);
    }
    return items.length ? `<div class="diagnosis-summary-grid">${items.join("")}</div>` : "";
  })();

  const issuesHtml = rankedIssues.length
    ? `<div class="diagnosis-section">${rankedIssues.map((issue, index) => renderIssueCard(issue, index)).join("")}</div>`
    : '<div class="results-context__note">No deterministic issues are currently flagged for this run. You can still use AI suggestions or compare evidence if you need more context.</div>';

  const actionsHtml = proposalActions.length
    ? `<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-3);">${proposalActions.map(action => renderActionCard(action)).join("")}</div>`
    : '<div class="results-context__note">No actionable deterministic actions for this run.</div>';

  const insufficientHtml = insufficient.length
    ? `<ul class="diagnosis-list">${insufficient.map(([rule, detail]) => `<li class="diagnosis-item"><strong>${escapeHtml(rule)}</strong>: ${escapeHtml(detail?.reason || "Insufficient evidence")}</li>`).join("")}</ul>`
    : '<div class="results-context__note">All deterministic rules had the evidence they needed.</div>';

  let aiHtml = '<div class="results-context__note">AI overlay disabled for this view.</div>';
  if (aiStatus === "ready") {
    const priorities = Array.isArray(ai?.priorities) ? ai.priorities : [];
    const rationale = Array.isArray(ai?.rationale) ? ai.rationale : [];
    const overlayDiagnosis = isObject(ai?.diagnosis) ? ai.diagnosis : {};
    const weaknesses = Array.isArray(overlayDiagnosis?.weaknesses) ? overlayDiagnosis.weaknesses : [];
    const parameterSuggestions = Array.isArray(ai?.parameter_suggestions) ? ai.parameter_suggestions : [];
    const confidenceLabel = formatConfidence(ai?.confidence);
    aiHtml = `
      ${ai?.summary ? `<div class="results-context__note">${escapeHtml(ai.summary)}</div>` : ""}
      <div class="results-context__meta">
        ${ai?.recommended_next_step ? `<span><strong>Recommended next step:</strong> ${escapeHtml(labelize(ai.recommended_next_step))}</span>` : ""}
        ${confidenceLabel ? `<span><strong>Confidence:</strong> ${escapeHtml(confidenceLabel)}</span>` : ""}
        ${ai?.provider ? `<span><strong>Model:</strong> ${escapeHtml(ai.provider)}${ai?.model ? ` / ${escapeHtml(ai.model)}` : ""}</span>` : ""}
      </div>
      ${overlayDiagnosis?.problem ? `<div class="results-context__note"><strong>Problem:</strong> ${escapeHtml(overlayDiagnosis.problem)}</div>` : ""}
      ${overlayDiagnosis?.cause ? `<div class="results-context__note"><strong>Cause:</strong> ${escapeHtml(overlayDiagnosis.cause)}</div>` : ""}
      ${weaknesses.length ? `<ul class="diagnosis-list">${weaknesses.map((item) => `<li class="diagnosis-item">${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
      ${ai?.code_change_summary ? `<div class="results-context__note"><strong>Code change summary:</strong> ${escapeHtml(ai.code_change_summary)}</div>` : ""}
      ${priorities.length ? `<ul class="diagnosis-list">${priorities.map((item) => `<li class="diagnosis-item">${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
      ${parameterSuggestions.length ? `<ul class="diagnosis-list">${parameterSuggestions.map((item) => `<li class="diagnosis-item"><strong>${escapeHtml(item?.name || "suggestion")}</strong>${item?.value != null ? ` = ${escapeHtml(item.value)}` : ""}${item?.reason ? `: ${escapeHtml(item.reason)}` : ""}</li>`).join("")}</ul>` : ""}
      ${rationale.length ? `<div class="results-context__note">${escapeHtml(rationale.join(" "))}</div>` : ""}
      <div class="results-context__note">Advisory only. Deterministic diagnosis remains the source of truth for version decisions.</div>
    `;
  } else if (aiStatus === "unavailable") {
    aiHtml = '<div class="results-context__note">AI overlay unavailable. Deterministic diagnosis remains available.</div>';
  }

  diagnosisPanel.innerHTML = `
    <section class="results-context${toneClass}">
      <div class="results-context__title">Run Diagnosis</div>
      <div class="results-context__meta">
        <span><strong>Strategy:</strong> ${escapeHtml(strategy || "?")}</span>
        <span><strong>Run:</strong> ${escapeHtml(runId)}</span>
        <span><strong>Version:</strong> ${escapeHtml(versionId)}</span>
        <span><strong>Status:</strong> ${escapeHtml(diagnosisStatus)}</span>
      </div>
      <div class="results-context__note">
        ${summaryAvailable ? "Start with Primary Issues below. Once you understand the baseline, move into Proposal Workflow to stage a candidate version." : escapeHtml(error || "Run a backtest first. Diagnosis and candidate actions stay locked until a persisted summary is available.")}
      </div>
    </section>
    ${summaryMetricsHtml ? `<section class="results-context"><div class="results-context__title">Summary Metrics</div>${summaryMetricsHtml}</section>` : ""}
    <section class="results-context">
      <div class="results-context__title">Primary Issues ${rankedIssues.length ? `<span style="font-weight: 400; color: var(--color-text-muted); font-size: var(--text-sm);">(${rankedIssues.length} ranked)</span>` : ""}</div>
      <div class="results-context__note">Start with items marked Actionable now. Diagnostic-only items explain the run but do not create a candidate path yet.</div>
      ${issuesHtml}
    </section>
    <section class="results-context">
      <div class="results-context__title">Deterministic Actions</div>
      <div class="results-context__note">Use these buttons to create a candidate version in the Proposal Workflow.</div>
      ${actionsHtml}
    </section>
    <section class="results-context">
      <div class="results-context__title">Evidence Gaps ${insufficient.length ? `<span style="font-weight: 400; color: var(--color-text-muted); font-size: var(--text-sm);">(${insufficient.length} rules)</span>` : ""}</div>
      <div class="results-context__note">Use this section to understand which rules are waiting on stronger evidence before they can become decision-ready.</div>
      ${insufficientHtml}
    </section>
    <section class="results-context">
      <div class="results-context__title">AI Overlay</div>
      <div class="results-context__note">Use this overlay as additional interpretation and suggestion. It does not replace deterministic diagnosis for final version decisions.</div>
      ${aiHtml}
    </section>
  `;
}

function publishReadyPayload(payload, response) {
  latestResultsPayload = payload;
  lastReadyPayload = payload;
  selectedRunId = payload.run_id;
  renderSummary(payload);
  renderDiagnosis(response);
  emit(EVENTS.RESULTS_LOADED, payload);
}

function publishEmptyPayload(strategy = "") {
  const empty = makeEmptyPayload(strategy);
  latestResultsPayload = empty;
  lastReadyPayload = null;
  selectedRunId = null;
  renderSummary(empty);
  renderDiagnosis(empty);
  emit(EVENTS.RESULTS_LOADED, empty);
}

async function loadDiagnosis(runId) {
  if (!runId) return;
  const localRequestId = ++requestId;

  try {
    const response = await api.backtest.getRunDiagnosis(runId, { include_ai: true });
    if (localRequestId !== requestId) return;
    if ((response?.strategy || "") !== (getState("backtest.strategy") || "")) return;

    const payload = buildResultsPayload(response);
    selectedRunId = response?.run_id || runId;

    if (response?.diagnosis_status === "ready" && response?.summary_available) {
      publishReadyPayload(payload, response);
      return;
    }

    if (!lastReadyPayload || lastReadyPayload.strategy !== payload.strategy) {
      latestResultsPayload = makeEmptyPayload(payload.strategy);
      emit(EVENTS.RESULTS_LOADED, latestResultsPayload);
    }

    renderSummary(lastReadyPayload || latestResultsPayload);
    renderDiagnosis(response);
  } catch (error) {
    if (localRequestId !== requestId) return;
    console.warn("[backtesting] Failed to load run diagnosis:", error);
    renderSummary(lastReadyPayload || latestResultsPayload || makeEmptyPayload(getState("backtest.strategy") || ""));
    renderDiagnosis({
      strategy: getState("backtest.strategy") || "",
      run_id: runId,
      diagnosis_status: "ingestion_failed",
      summary_available: false,
      error: error?.message || String(error),
      ai: { ai_status: "unavailable" },
      diagnosis: null,
    });
  }
}

function selectPreferredRun(snapshot) {
  const runs = Array.isArray(snapshot?.runs) ? snapshot.runs : [];
  return runs.find((run) => run?.status === "completed" && run?.summary_available) || runs[0] || null;
}

function refreshWorkflowGuide() {
  renderWorkflowGuide(latestResultsPayload || makeEmptyPayload(getState("backtest.strategy") || currentStrategy || ""));
}

function handleVersionsSnapshot(snapshot) {
  versionsSnapshot = snapshot || { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
  refreshWorkflowGuide();
}

function handleRunsSnapshot(snapshot) {
  runsSnapshot = snapshot || { status: "idle", strategy: "", runs: [], error: null };
  const strategy = runsSnapshot?.strategy || getState("backtest.strategy") || "";
  const strategyChanged = strategy !== currentStrategy;

  if (strategyChanged) {
    currentStrategy = strategy;
    selectedRunId = null;
    publishEmptyPayload(strategy);
  }

  if (!strategy) {
    publishEmptyPayload("");
    return;
  }

  refreshWorkflowGuide();

  if (runsSnapshot?.status !== "ready") {
    return;
  }

  const preferredRun = selectPreferredRun(runsSnapshot);
  if (!preferredRun) {
    publishEmptyPayload(strategy);
    return;
  }

  const runIds = new Set((runsSnapshot.runs || []).map((run) => run?.run_id));
  if (!selectedRunId || !runIds.has(selectedRunId) || strategyChanged) {
    loadDiagnosis(preferredRun.run_id);
  }
}

function shouldPreserveWorkflowBaseline(event) {
  const triggerSource = String(event?.trigger_source || "").toLowerCase();
  return Boolean(
    triggerSource === "ai_apply"
      && lastReadyPayload?.diagnosis_status === "ready"
      && lastReadyPayload?.summary_available
      && lastReadyPayload?.run_id
  );
}

function focusTarget(selector) {
  if (!selector) return;
  const node = document.querySelector(selector);
  if (node?.focus) {
    node.focus({ preventScroll: true });
    node.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function scrollToSection(sectionId, focusSelector = "") {
  const section = document.getElementById(sectionId);
  section?.scrollIntoView({ behavior: "smooth", block: "start" });
  if (focusSelector) {
    window.requestAnimationFrame(() => focusTarget(focusSelector));
  }
}

function openSummarySection(sectionId, focusSelector = "") {
  activateBacktestTab("summary");
  window.requestAnimationFrame(() => scrollToSection(sectionId, focusSelector));
}

function openResultsTab(tabId, sectionId) {
  activateBacktestTab(tabId);
  window.requestAnimationFrame(() => scrollToSection(sectionId));
}

function handleWorkflowGuideClick(event) {
  const button = event.target.closest("[data-workflow-action]");
  if (!button) return;

  const action = button.dataset.workflowAction || "";
  if (action === "open-setup") {
    scrollToSection("setup-panel", "#select-strategy");
    return;
  }
  if (action === "focus-run") {
    scrollToSection("run-panel", "#btn-run-backtest");
    return;
  }
  if (action === "review-diagnosis") {
    openSummarySection("summary-diagnosis");
    return;
  }
  if (action === "open-proposals") {
    openSummarySection("summary-proposals");
    return;
  }
  if (action === "focus-rerun") {
    openSummarySection("summary-proposals", '[data-action="rerun-candidate"]');
    return;
  }
  if (action === "open-compare") {
    openResultsTab("compare", "compare-area");
    return;
  }
  if (action === "review-decision") {
    openSummarySection("summary-proposals", '[data-action="accept-candidate"], [data-action="reject-candidate"], [data-action="rerun-candidate"]');
    return;
  }
  if (action === "open-history") {
    openResultsTab("history", "history-list");
  }
}

export function initResultsController() {
  currentStrategy = getState("backtest.strategy") || "";
  initPersistedRunsStore();
  initPersistedVersionsStore();
  summaryWorkflowGuide?.addEventListener("click", handleWorkflowGuideClick);
  subscribePersistedRuns(handleRunsSnapshot);
  subscribePersistedVersions(handleVersionsSnapshot);
  onState("backtest.selectedCandidateVersionId", refreshWorkflowGuide);

  on(EVENTS.BACKTEST_COMPLETE, (event) => {
    if (!event?.run_id) {
      return;
    }
    if (shouldPreserveWorkflowBaseline(event)) {
      return;
    }
    loadDiagnosis(event.run_id);
  });

  renderWorkflowGuide(makeEmptyPayload(currentStrategy));
}

