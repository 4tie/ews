/**
 * results-controller.js - Loads run-scoped diagnosis and fans out the latest ready result payload.
 */

import api from "../../../core/api.js";
import { getState } from "../../../core/state.js";
import { on, emit, EVENTS } from "../../../core/events.js";
import { renderSummaryCards } from "../../shared/backtest/result_renderer.js";
import { initPersistedRunsStore, subscribePersistedRuns } from "./persisted-runs-store.js";

const summaryCards = document.getElementById("summary-cards");
const diagnosisPanel = document.getElementById("summary-diagnosis");

let latestResultsPayload = null;
let lastReadyPayload = null;
let currentStrategy = "";
let selectedRunId = null;
let currentDiagnosisResponse = null;
let requestId = 0;

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
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function labelize(value) {
  return String(value || "-")
    .replace(/_/g, " ")
    .replace(/\w/g, (letter) => letter.toUpperCase());
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

function renderSummary(payload) {
  const summarySource = payload?.summary ?? lastReadyPayload?.summary ?? null;
  renderSummaryCards(summaryCards, summarySource, { expanded: true });
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

  const primaryFlags = Array.isArray(diagnosis?.primary_flags) ? diagnosis.primary_flags : [];
  const insufficient = diagnosis?.insufficient_evidence && isObject(diagnosis.insufficient_evidence)
    ? Object.entries(diagnosis.insufficient_evidence)
    : [];
  const aiStatus = ai?.ai_status || "disabled";

  const issuesHtml = primaryFlags.length
    ? `<ul class="diagnosis-list">${primaryFlags.map((flag) => {
        const severity = String(flag?.severity || "warning");
        const klass = severity === "critical" ? "diagnosis-item diagnosis-item--critical" : "diagnosis-item diagnosis-item--warning";
        const actionability = describeIssueActionability(diagnosis, flag?.rule);
        return `
          <li class="${klass}">
            <strong>${escapeHtml(flag?.rule || "issue")}</strong>: ${escapeHtml(flag?.message || "")}
            <div class="results-context__note"><strong>${escapeHtml(actionability.label)}:</strong> ${escapeHtml(actionability.reason)}</div>
          </li>
        `;
      }).join("")}</ul>`
    : '<div class="results-context__note">No deterministic issues are currently flagged for this run.</div>';

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
        ${summaryAvailable ? "Diagnosis is reading the persisted run-linked summary artifact." : escapeHtml(error || "Summary is not ready for diagnosis yet.")}
      </div>
    </section>
    <section class="results-context">
      <div class="results-context__title">Primary Issues</div>
      ${issuesHtml}
    </section>
    <section class="results-context">
      <div class="results-context__title">Evidence Gaps</div>
      ${insufficientHtml}
    </section>
    <section class="results-context">
      <div class="results-context__title">AI Overlay</div>
      ${aiHtml}
    </section>
  `;
}

function publishReadyPayload(payload, response) {
  latestResultsPayload = payload;
  lastReadyPayload = payload;
  currentDiagnosisResponse = response;
  selectedRunId = payload.run_id;
  renderSummary(payload);
  renderDiagnosis(response);
  emit(EVENTS.RESULTS_LOADED, payload);
}

function publishEmptyPayload(strategy = "") {
  const empty = makeEmptyPayload(strategy);
  latestResultsPayload = empty;
  lastReadyPayload = null;
  currentDiagnosisResponse = null;
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
    currentDiagnosisResponse = response;
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

function handleRunsSnapshot(snapshot) {
  const strategy = snapshot?.strategy || getState("backtest.strategy") || "";
  const strategyChanged = strategy !== currentStrategy;

  if (strategyChanged) {
    currentStrategy = strategy;
    selectedRunId = null;
    currentDiagnosisResponse = null;
    publishEmptyPayload(strategy);
  }

  if (!strategy) {
    publishEmptyPayload("");
    return;
  }

  if (snapshot?.status !== "ready") {
    return;
  }

  const preferredRun = selectPreferredRun(snapshot);
  if (!preferredRun) {
    publishEmptyPayload(strategy);
    return;
  }

  const runIds = new Set((snapshot.runs || []).map((run) => run?.run_id));
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

export function initResultsController() {
  currentStrategy = getState("backtest.strategy") || "";
  initPersistedRunsStore();
  subscribePersistedRuns(handleRunsSnapshot);

  on(EVENTS.BACKTEST_COMPLETE, (event) => {
    if (!event?.run_id) {
      return;
    }
    if (shouldPreserveWorkflowBaseline(event)) {
      return;
    }
    loadDiagnosis(event.run_id);
  });
}
