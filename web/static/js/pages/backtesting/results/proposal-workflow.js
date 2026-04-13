/**
 * proposal-workflow.js - Run-scoped proposal, candidate, rerun, compare, and decision workflow.
 */

import api from "../../../core/api.js";
import { getState, on as onState } from "../../../core/state.js";
import { on, EVENTS } from "../../../core/events.js";
import { formatDate, formatNum, formatPct } from "../../../core/utils.js";
import { closeModal, openModal } from "../../../components/modal.js";
import showToast from "../../../components/toast.js";
import { startBacktestRun } from "../run/run-controller.js";
import { loadOptions } from "../setup/options-loader.js";
import { switchBacktestStrategy } from "../setup/strategy-panel.js";
import { renderDecisionReadyCompare } from "../compare/decision-ready-renderer.js";
import {
  ensureSelectedCandidateVersion,
  getSelectedCandidateVersionId,
  getWorkflowCandidateVersions,
  setSelectedCandidateVersionId,
} from "../compare/candidate-selection-state.js";
import { initPersistedRunsStore, subscribePersistedRuns } from "./persisted-runs-store.js";
import {
  initPersistedVersionsStore,
  refreshPersistedVersions,
  subscribePersistedVersions,
} from "./persisted-versions-store.js";

const root = document.getElementById("summary-proposals");


let latestPayload = null;
let runsSnapshot = { status: "idle", strategy: "", runs: [], error: null };
let versionsState = { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
let compareState = { status: "idle", key: "", data: null, error: null };
let compareRequestId = 0;
let busyAction = "";

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

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function resolveStrategy() {
  return getState("backtest.strategy") || latestPayload?.strategy || runsSnapshot.strategy || versionsState.strategy || "";
}

function currentBaselineRunId() {
  return latestPayload?.run_id || null;
}

function currentBaselineVersionId() {
  return latestPayload?.version_id || null;
}

function canShowWorkflow() {
  return Boolean(root && latestPayload?.diagnosis_status === "ready" && latestPayload?.summary_available && currentBaselineRunId());
}

function requiresExactBaselineVersion() {
  return Boolean(currentBaselineVersionId());
}

function getWorkflowVersions() {
  return getWorkflowCandidateVersions(versionsState.versions, currentBaselineRunId());
}

function syncWorkflowCandidateSelection() {
  return ensureSelectedCandidateVersion(versionsState.versions, currentBaselineRunId());
}

function currentCandidateVersion() {
  const selectedVersionId = getSelectedCandidateVersionId();
  return getWorkflowVersions().find((version) => version?.version_id === selectedVersionId) || getWorkflowVersions()[0] || null;
}

function getCandidateRuns(candidateVersionId) {
  if (!candidateVersionId) return [];
  return (runsSnapshot.runs || [])
    .filter((run) => run?.version_id === candidateVersionId)
    .slice()
    .sort((left, right) => String(right?.completed_at || right?.created_at || "").localeCompare(String(left?.completed_at || left?.created_at || "")));
}

function currentCandidateRun() {
  const candidate = currentCandidateVersion();
  return getCandidateRuns(candidate?.version_id)[0] || null;
}

function currentComparableCandidateRun() {
  return getCandidateRuns(currentCandidateVersion()?.version_id).find((run) => run?.status === "completed" && run?.summary_available) || null;
}

function formatCandidateOption(version) {
  const sourceTitle = version?.source_context?.title || version?.summary || version?.source_ref || "Candidate";
  return `${version?.version_id || "-"} | ${labelize(version?.change_type)} | ${sourceTitle} | ${formatDate(version?.created_at)}`;
}

function getVersionAuditEvents(version) {
  return (Array.isArray(version?.audit_events) ? version.audit_events : [])
    .slice()
    .sort((left, right) => String(left?.created_at || "").localeCompare(String(right?.created_at || "")));
}

function latestVersionAuditEvent(version) {
  const events = getVersionAuditEvents(version);
  return events[events.length - 1] || null;
}

function latestVersionAuditNote(version) {
  const notedEvents = getVersionAuditEvents(version).filter((event) => String(event?.note || "").trim());
  return notedEvents[notedEvents.length - 1] || null;
}

function truncateText(value, maxLength = 160) {
  const textValue = String(value || "").trim();
  if (!textValue || textValue.length <= maxLength) return textValue;
  return `${textValue.slice(0, Math.max(0, maxLength - 1)).trimEnd()}...`;
}

function buildDecisionContextHtml({ title = "", fields = [], note = "" }) {
  const rows = Array.isArray(fields)
    ? fields.filter(([label, value]) => String(label || "").trim() && String(value || "").trim())
    : [];

  return `
    <div class="proposal-note-dialog__context">
      ${title ? `<div class="proposal-note-dialog__context-title">${escapeHtml(title)}</div>` : ""}
      ${rows.length ? `<div class="proposal-note-dialog__context-grid">${rows.map(([label, value]) => `<span><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</span>`).join("")}</div>` : ""}
      ${note ? `<div class="proposal-note-dialog__context-copy">${escapeHtml(note)}</div>` : ""}
    </div>
  `;
}


function openDecisionNoteDialog({ title, label, confirmLabel, placeholder, contextHtml = "" }) {
  return new Promise((resolve) => {
    let settled = false;
    const dialogBody = `
      <form id="proposal-note-form" class="proposal-note-dialog">
        ${contextHtml || ""}
        <label class="setup-field proposal-note-dialog__field">
          <span class="form-label">${escapeHtml(label)}</span>
          <textarea id="proposal-note-input" class="form-input proposal-note-dialog__textarea" rows="5" placeholder="${escapeHtml(placeholder || "")}"></textarea>
        </label>
      </form>
    `;
    const dialogFooter = `
      <button type="button" class="btn btn--ghost btn--sm" id="proposal-note-cancel">Cancel</button>
      <button type="button" class="btn btn--secondary btn--sm" id="proposal-note-confirm">${escapeHtml(confirmLabel)}</button>
    `;

    const settle = (value) => {
      if (settled) return;
      settled = true;
      closeModal();
      resolve(value);
    };

    openModal({
      title,
      body: dialogBody,
      footer: dialogFooter,
      onClose: () => {
        if (!settled) {
          settled = true;
          resolve(null);
        }
      },
    });

    const input = document.getElementById("proposal-note-input");
    document.getElementById("proposal-note-cancel")?.addEventListener("click", () => settle(null));
    document.getElementById("proposal-note-confirm")?.addEventListener("click", () => settle(String(input?.value || "").trim()));
    document.getElementById("proposal-note-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      settle(String(input?.value || "").trim());
    });
    input?.focus();
  });
}


function openAcceptDecisionDialog() {
  return new Promise((resolve) => {
    let settled = false;
    const strategyName = resolveStrategy() || "Strategy";
    const candidate = currentCandidateVersion();
    const baselineVersionId = currentBaselineVersionId() || "Unavailable";
    const candidateVersionId = candidate?.version_id || "Unavailable";
    const candidateSourceTitle = candidate?.source_context?.title || candidate?.summary || candidate?.source_ref || "Selected candidate";
    const suggestion = `${strategyName || 'Strategy'}_v2`;
    const contextHtml = buildDecisionContextHtml({
      title: "Decision target",
      fields: [
        ["Current strategy", strategyName],
        ["Current live version", baselineVersionId],
        ["Selected candidate", candidateVersionId],
        ["Candidate source", candidateSourceTitle],
      ],
      note: `Current live target is ${strategyName} at version ${baselineVersionId}. Accepting as current writes this candidate into that target. Promote as new strategy variant creates a separate live strategy and leaves ${strategyName} unchanged.`,
    });
    const dialogBody = `
      <form id="proposal-accept-form" class="proposal-note-dialog">
        ${contextHtml}
        <fieldset class="proposal-note-dialog__mode-group">
          <legend class="form-label">Promotion Mode</legend>
          <label class="proposal-note-dialog__choice">
            <input type="radio" name="proposal-accept-mode" value="accept_current" checked />
            <span>Accept as current strategy</span>
          </label>
          <div class="proposal-note-dialog__choice-copy">Writes candidate ${escapeHtml(candidateVersionId)} into the live ${escapeHtml(strategyName)} target.</div>
          <label class="proposal-note-dialog__choice">
            <input type="radio" name="proposal-accept-mode" value="promote_new_strategy" />
            <span>Promote as new strategy variant</span>
          </label>
          <div class="proposal-note-dialog__choice-copy">Creates a separate strategy lineage and keeps ${escapeHtml(strategyName)} unchanged.</div>
        </fieldset>
        <label class="setup-field proposal-note-dialog__field">
          <span class="form-label">Decision note</span>
          <textarea id="proposal-note-input" class="form-input proposal-note-dialog__textarea" rows="5" placeholder="Why this candidate should become the live target or a new variant."></textarea>
        </label>
        <label class="setup-field proposal-note-dialog__field" id="proposal-new-strategy-field" hidden>
          <span class="form-label">New strategy name</span>
          <input id="proposal-new-strategy-input" class="form-input" type="text" value="${escapeHtml(suggestion)}" placeholder="MultiMa_v2" pattern="[A-Za-z_][A-Za-z0-9_]*" spellcheck="false" autocapitalize="off" autocomplete="off" />
          <span class="field-hint">Creates a separate live strategy and leaves ${escapeHtml(strategyName)} unchanged.</span>
          <span class="field-hint">File: <code id="proposal-new-strategy-file">user_data/strategies/${escapeHtml(suggestion)}.py</code></span>
          <span class="field-hint">Class: <code id="proposal-new-strategy-class">${escapeHtml(suggestion)}</code></span>
          <span class="field-hint">Config: <code id="proposal-new-strategy-config">user_data/config/config_${escapeHtml(suggestion)}.json</code></span>
        </label>
      </form>
    `;
    const dialogFooter = `
      <button type="button" class="btn btn--ghost btn--sm" id="proposal-accept-cancel">Cancel</button>
      <button type="button" class="btn btn--secondary btn--sm" id="proposal-accept-confirm">Accept Candidate</button>
    `;

    const settle = (value) => {
      if (settled) return;
      settled = true;
      closeModal();
      resolve(value);
    };

    openModal({
      title: "Accept Candidate",
      body: dialogBody,
      footer: dialogFooter,
      onClose: () => {
        if (!settled) {
          settled = true;
          resolve(null);
        }
      },
    });

    const form = document.getElementById("proposal-accept-form");
    const noteInput = document.getElementById("proposal-note-input");
    const modeInputs = Array.from(document.querySelectorAll('input[name="proposal-accept-mode"]'));
    const strategyField = document.getElementById("proposal-new-strategy-field");
    const strategyInput = document.getElementById("proposal-new-strategy-input");
    const filePreview = document.getElementById("proposal-new-strategy-file");
    const classPreview = document.getElementById("proposal-new-strategy-class");
    const configPreview = document.getElementById("proposal-new-strategy-config");

    const selectedMode = () => modeInputs.find((input) => input.checked)?.value || "accept_current";
    const clearStrategyValidation = () => strategyInput?.setCustomValidity("");
    const syncMode = () => {
      const promoteNew = selectedMode() === "promote_new_strategy";
      if (strategyField) strategyField.hidden = !promoteNew;
      if (strategyInput) {
        strategyInput.disabled = !promoteNew;
        strategyInput.required = promoteNew;
        if (!promoteNew) {
          clearStrategyValidation();
        }
      }
    };
    const syncPreviews = () => {
      const name = String(strategyInput?.value || "").trim() || suggestion;
      if (filePreview) filePreview.textContent = `user_data/strategies/${name}.py`;
      if (classPreview) classPreview.textContent = name;
      if (configPreview) configPreview.textContent = `user_data/config/config_${name}.json`;
    };

    const submit = () => {
      const mode = selectedMode();
      const newStrategyName = mode === "promote_new_strategy" ? String(strategyInput?.value || "").trim() : "";
      if (mode === "promote_new_strategy") {
        if (!newStrategyName) {
          strategyInput?.setCustomValidity("New strategy name is required.");
          strategyInput?.reportValidity();
          strategyInput?.focus();
          return;
        }
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(newStrategyName)) {
          strategyInput?.setCustomValidity("Use a valid Python identifier.");
          strategyInput?.reportValidity();
          strategyInput?.focus();
          return;
        }
        if (newStrategyName === resolveStrategy()) {
          strategyInput?.setCustomValidity("New strategy name must be different from the current strategy.");
          strategyInput?.reportValidity();
          strategyInput?.focus();
          return;
        }
      }
      clearStrategyValidation();
      settle({
        note: String(noteInput?.value || "").trim(),
        promotionMode: mode,
        newStrategyName,
      });
    };

    document.getElementById("proposal-accept-cancel")?.addEventListener("click", () => settle(null));
    document.getElementById("proposal-accept-confirm")?.addEventListener("click", submit);
    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      submit();
    });
    modeInputs.forEach((input) => input.addEventListener("change", syncMode));
    strategyInput?.addEventListener("input", () => {
      clearStrategyValidation();
      syncPreviews();
    });

    syncMode();
    syncPreviews();
    noteInput?.focus();
  });
}


function renderCandidateSelector() {
  const versions = getWorkflowVersions();
  if (versions.length < 2) return "";

  const selectedVersionId = getSelectedCandidateVersionId();
  return `
    <label class="setup-field compare-toolbar__field proposal-candidate-selector">
      <span class="form-label">Selected Candidate</span>
      <select class="form-select" data-role="selected-candidate">
        ${versions.map((version) => `
          <option value="${escapeHtml(version?.version_id || "")}"${version?.version_id === selectedVersionId ? " selected" : ""}>${escapeHtml(formatCandidateOption(version))}</option>
        `).join("")}
      </select>
    </label>
  `;
}

function renderEmptyState(message) {
  if (!root) return;
  root.innerHTML = message ? `<section class="results-context results-context--empty"><div class="results-context__title">Proposal Workflow</div><div class="results-context__note">${escapeHtml(message)}</div></section>` : "";
}

function renderWorkflowIntro() {
  return `
    <section class="results-context results-context--table">
      <div class="results-context__title">Proposal Workflow</div>
      <div class="results-context__note">Start here after reviewing diagnosis. Create a versioned candidate from an actionable source, re-run the selected candidate, compare baseline vs selected candidate, then make the version decision.</div>
      <div class="results-context__note">If you want to preserve the original strategy, use <strong>Promote as new strategy variant</strong> when the candidate is ready.</div>
    </section>
  `;
}

function formatMetricValue(valueFormat, value, currency = "", options = {}) {
  if (value == null || value === "") return "-";
  if (valueFormat === "pct") return formatPct(value);
  if (valueFormat === "count") {
    const number = Number(value);
    return Number.isFinite(number) ? `${Math.round(number)}` : String(value);
  }
  if (valueFormat === "money") {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    const prefix = options.signed && number > 0 ? "+" : "";
    return `${prefix}${formatNum(number, 2)}${currency ? ` ${currency}` : ""}`;
  }
  const number = Number(value);
  if (Number.isFinite(number)) {
    const prefix = options.signed && number > 0 ? "+" : "";
    return `${prefix}${formatNum(number, 3)}`;
  }
  return String(value);
}

function resolveDeterministicAction(rule) {
  const normalizedRule = String(rule || "").trim();
  if (!normalizedRule) return null;

  const actions = Array.isArray(latestPayload?.diagnosis?.proposal_actions) ? latestPayload.diagnosis.proposal_actions : [];
  return actions.find((item) => Array.isArray(item?.matched_rules) && item.matched_rules.includes(normalizedRule)) || null;
}

function describeProposalActionability(sourceKind, item) {
  if (sourceKind === "deterministic_action") {
    return {
      actionable: true,
      label: "Actionable now",
      reason: item?.summary || item?.message || "This deterministic action can stage a candidate immediately.",
      mappedAction: item || null,
    };
  }

  if (sourceKind === "ai_parameter_suggestion") {
    return {
      actionable: true,
      label: "Actionable now",
      reason: "AI can draft a versioned candidate from this diagnosed run context.",
      mappedAction: null,
    };
  }

  const mappedAction = resolveDeterministicAction(item?.rule);
  if (mappedAction) {
    const actionLabel = mappedAction?.label || labelize(mappedAction?.action_type || "deterministic action");
    return {
      actionable: true,
      label: "Actionable now",
      reason: `Candidate path available via ${actionLabel}.`,
      mappedAction,
    };
  }

  return {
    actionable: false,
    label: "Diagnostic only",
    reason: "No direct candidate action is mapped for this diagnosis item yet.",
    mappedAction: null,
  };
}

function renderProposalStatusChip(details) {
  const tone = details?.actionable ? "actionable" : "advisory";
  const label = details?.label || (details?.actionable ? "Actionable now" : "Diagnostic only");
  return `<span class="proposal-status-chip proposal-status-chip--${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
}

function renderPrimaryIssues() {
  const items = Array.isArray(latestPayload?.diagnosis?.primary_flags) ? latestPayload.diagnosis.primary_flags : [];
  const body = items.length
    ? `<div class="proposal-flags">${items.map((flag) => {
        const severity = String(flag?.severity || "warning");
        const actionability = describeProposalActionability("ranked_issue", flag);
        return `
          <article class="proposal-flag proposal-flag--${escapeHtml(severity)}">
            <div class="proposal-flag__header">
              <span class="proposal-flag__rule">${escapeHtml(flag?.rule || "issue")}</span>
              <div class="proposal-flag__chips">
                <span class="proposal-flag__severity">${escapeHtml(labelize(severity))}</span>
                ${renderProposalStatusChip(actionability)}
              </div>
            </div>
            <div class="proposal-flag__message">${escapeHtml(flag?.message || "No summary available.")}</div>
            <div class="proposal-status-note">${escapeHtml(actionability.reason)}</div>
          </article>
        `;
      }).join("")}</div>`
    : '<div class="results-context__note">No pinned primary issues are currently available for this run.</div>';

  return `
    <section class="results-context">
      <div class="results-context__title">Primary Issues</div>
      <div class="results-context__note">Start with items marked Actionable now. Diagnostic-only items explain the run but do not stage a candidate path by themselves.</div>
      ${body}
    </section>
  `;
}

function renderRankedIssue(item) {
  const severity = labelize(item?.severity || "warning");
  const message = item?.message || item?.rule || "Ranked issue";
  const distance = item?.threshold_distance == null ? "-" : formatNum(item.threshold_distance, 2);
  return `
    <div class="proposal-item__body">${escapeHtml(message)}</div>
    <div class="proposal-item__meta">
      <span><strong>Rule:</strong> ${escapeHtml(item?.rule || "-")}</span>
      <span><strong>Severity:</strong> ${escapeHtml(severity)}</span>
      <span><strong>Distance:</strong> ${escapeHtml(distance)}</span>
    </div>
  `;
}

function renderParameterHint(item) {
  const parameters = Array.isArray(item?.parameters) ? item.parameters.join(", ") : "-";
  return `
    <div class="proposal-item__body">${escapeHtml(item?.rationale || item?.rule || "Parameter hint")}</div>
    <div class="proposal-item__meta">
      <span><strong>Rule:</strong> ${escapeHtml(item?.rule || "-")}</span>
      <span><strong>Parameters:</strong> ${escapeHtml(parameters)}</span>
    </div>
  `;
}

function renderAiSuggestion(item) {
  const name = item?.name || item?.parameter || item?.key || "AI suggestion";
  const value = item?.value == null ? "-" : String(item.value);
  const reason = item?.reason || item?.rationale || item?.summary || "AI suggestion grounded in the latest diagnosis.";
  return `
    <div class="proposal-item__body">${escapeHtml(reason)}</div>
    <div class="proposal-item__meta">
      <span><strong>Name:</strong> ${escapeHtml(name)}</span>
      <span><strong>Value:</strong> ${escapeHtml(value)}</span>
    </div>
  `;
}

function renderDeterministicAction(item) {
  const parameters = Array.isArray(item?.parameters) ? item.parameters.join(", ") : "-";
  const matchedRules = Array.isArray(item?.matched_rules) ? item.matched_rules.join(", ") : "-";
  return `
    <div class="proposal-item__body">${escapeHtml(item?.summary || item?.message || "Diagnosis-backed deterministic action")}</div>
    <div class="proposal-item__meta">
      <span><strong>Action:</strong> ${escapeHtml(item?.label || item?.action_type || "-")}</span>
      <span><strong>Rules:</strong> ${escapeHtml(matchedRules)}</span>
      <span><strong>Parameters:</strong> ${escapeHtml(parameters)}</span>
    </div>
  `;
}

function renderActionSection({ title, sourceKind, items, note, renderer }) {
  const body = items.length
    ? items.map((item, index) => {
        const actionKey = `create:${sourceKind}:${index}`;
        const actionability = describeProposalActionability(sourceKind, item);
        const advisoryOnly = !actionability.actionable;
        const busyLocked = Boolean(busyAction && busyAction !== actionKey);
        const loading = busyAction === actionKey;
        const effectiveActionType = item?.action_type || actionability?.mappedAction?.action_type || "";
        const actionTypeAttr = effectiveActionType ? ` data-action-type="${escapeHtml(effectiveActionType)}"` : "";
        const disabled = advisoryOnly || busyLocked ? " disabled" : "";
        const buttonTitle = advisoryOnly ? ` title="${escapeHtml(actionability.reason)}"` : "";
        const buttonLabel = advisoryOnly ? "Advisory Only" : loading ? "Creating..." : "Create Candidate";
        return `
          <article class="proposal-item">
            <div class="proposal-item__header">
              <div>
                <div class="proposal-item__title">${escapeHtml(item?.label || item?.rule || item?.name || item?.parameter || item?.key || `${title} ${index + 1}`)}</div>
                <div class="proposal-item__subtitle">${escapeHtml(sourceKind.replace(/_/g, " "))}</div>
              </div>
              <div class="proposal-item__controls">
                ${renderProposalStatusChip(actionability)}
                <button type="button" class="btn btn--secondary btn--sm" data-action="create-candidate" data-source-kind="${escapeHtml(sourceKind)}" data-source-index="${index}"${actionTypeAttr}${buttonTitle}${disabled}>${buttonLabel}</button>
              </div>
            </div>
            ${renderer(item)}
            <div class="proposal-status-note">${escapeHtml(actionability.reason)}</div>
          </article>
        `;
      }).join("")
    : `<div class="results-context__note">${escapeHtml(note)}</div>`;

  return `
    <section class="results-context">
      <div class="results-context__title">${escapeHtml(title)}</div>
      <div class="proposal-items">${body}</div>
    </section>
  `;
}

function renderWorkflowState() {
  const candidate = currentCandidateVersion();
  if (!candidate) {
    return `
      <section class="results-context results-context--empty results-context--table">
        <div class="results-context__title">Candidate State</div>
        <div class="results-context__note">Create a candidate from one of the diagnosis-backed proposal sources to start the run-scoped workflow.</div>
      </section>
    `;
  }

  const baselineRunId = currentBaselineRunId();
  const baselineVersionId = currentBaselineVersionId() || "Unavailable on baseline run";
  const exactBaseline = requiresExactBaselineVersion();
  const candidateRun = currentCandidateRun();
  const rerunBusy = busyAction === "rerun-candidate";
  const acceptBusy = busyAction === "accept-candidate";
  const rejectBusy = busyAction === "reject-candidate";
  const rollbackBusy = busyAction === "rollback-baseline";
  const anyBusy = Boolean(busyAction);
  const latestAudit = latestVersionAuditEvent(candidate);
  const latestAuditNote = latestVersionAuditNote(candidate);

  const candidateRunLabel = candidateRun
    ? `${labelize(candidateRun.status)} | ${formatDate(candidateRun.completed_at || candidateRun.created_at)}`
    : "Not rerun yet";
  const strategyName = resolveStrategy() || "strategy";
  const exactBaselineNote = exactBaseline
    ? `Current live target is ${strategyName} at version ${baselineVersionId}. Accept promotes the selected candidate into this target. Use "Promote as new strategy variant" in the dialog to keep ${strategyName} unchanged and create a separate strategy lineage.`
    : `Current live target is ambiguous because baseline run ${baselineRunId || "-"} has no exact version_id. Candidate creation and rerun stay available, but accept and rollback remain disabled until the workflow is grounded in an exact version.`;
  const sourceTitle = candidate?.source_context?.title || candidate?.summary || candidate?.source_ref || "-";
  const candidateMode = candidate?.source_context?.candidate_mode || "-";
  const latestAuditLabel = latestAudit
    ? `${labelize(latestAudit.event_type)} | ${formatDate(latestAudit.created_at)}`
    : "No audit events yet";
  const latestAuditNoteText = latestAuditNote?.note
    ? `Latest audit note: ${truncateText(latestAuditNote.note)}`
    : "No audit note saved yet for this candidate.";

  return `
    <section class="results-context results-context--table">
      <div class="results-context__title">Candidate State</div>
      ${renderCandidateSelector()}
      <div class="results-context__meta proposal-state-grid">
        <span><strong>Baseline Run:</strong> ${escapeHtml(baselineRunId || "-")}</span>
        <span><strong>Baseline Version:</strong> ${escapeHtml(baselineVersionId)}</span>
        <span><strong>Selected Candidate:</strong> ${escapeHtml(candidate.version_id || "-")}</span>
        <span><strong>Candidate Parent:</strong> ${escapeHtml(candidate.parent_version_id || "-")}</span>
        <span><strong>Candidate Status:</strong> ${escapeHtml(labelize(candidate.status))}</span>
        <span><strong>Change Type:</strong> ${escapeHtml(labelize(candidate.change_type))}</span>
        <span><strong>Source Kind:</strong> ${escapeHtml(labelize(candidate.source_kind || "-"))}</span>
        <span><strong>Source Title:</strong> ${escapeHtml(sourceTitle)}</span>
        <span><strong>Candidate Mode:</strong> ${escapeHtml(labelize(candidateMode))}</span>
        <span><strong>Candidate Run:</strong> ${escapeHtml(candidateRunLabel)}</span>
        <span><strong>Created:</strong> ${escapeHtml(formatDate(candidate.created_at))}</span>
        <span><strong>Latest Audit:</strong> ${escapeHtml(latestAuditLabel)}</span>
      </div>
      <div class="results-context__note">${escapeHtml(exactBaselineNote)}</div>
      <div class="results-context__note proposal-audit-note">${escapeHtml(latestAuditNoteText)}</div>
      <div class="proposal-actions">
        <button type="button" class="btn btn--secondary btn--sm" data-action="rerun-candidate"${anyBusy && !rerunBusy ? " disabled" : ""}>${rerunBusy ? "Starting..." : "Re-run Candidate"}</button>
        <button type="button" class="btn btn--secondary btn--sm" data-action="accept-candidate"${!exactBaseline || (anyBusy && !acceptBusy) ? " disabled" : ""}>${acceptBusy ? "Accepting..." : "Accept"}</button>
        <button type="button" class="btn btn--ghost btn--sm" data-action="reject-candidate"${anyBusy && !rejectBusy ? " disabled" : ""}>${rejectBusy ? "Rejecting..." : "Reject"}</button>
        <button type="button" class="btn btn--ghost btn--sm" data-action="rollback-baseline"${!exactBaseline || (anyBusy && !rollbackBusy) ? " disabled" : ""}>${rollbackBusy ? "Rolling Back..." : "Rollback"}</button>
      </div>
    </section>
  `;
}

function renderCompareSection() {
  const candidate = currentCandidateVersion();
  const candidateRun = currentComparableCandidateRun();
  if (!candidate) {
    return "";
  }
  const candidateSourceTitle = candidate?.source_context?.title || candidate?.summary || candidate?.source_ref || "selected candidate";
  if (!candidateRun) {
    return `
      <section class="results-context results-context--table results-context--empty">
        <div class="results-context__title">Candidate Compare</div>
        <div class="results-context__note">Re-run the selected candidate to create a persisted completed run before comparing it against the baseline run inline. Current selection: ${escapeHtml(candidate.version_id || "-")} | ${escapeHtml(candidateSourceTitle)}.</div>
      </section>
    `;
  }
  if (compareState.status === "loading") {
    return `
      <section class="results-context results-context--table results-context--empty">
        <div class="results-context__title">Candidate Compare</div>
        <div class="results-context__note">Loading persisted compare evidence for baseline ${escapeHtml(currentBaselineRunId())} vs selected candidate run ${escapeHtml(candidateRun.run_id)}.</div>
      </section>
    `;
  }
  if (compareState.status === "error") {
    return `
      <section class="results-context results-context--table results-context--empty">
        <div class="results-context__title">Candidate Compare</div>
        <div class="results-context__note">${escapeHtml(compareState.error ? `Persisted compare evidence is unavailable: ${compareState.error}` : "Persisted compare evidence is unavailable.")}</div>
      </section>
    `;
  }
  if (!compareState.data) {
    return "";
  }

  return `
    <section class="results-context">
      <div class="results-context__title">Candidate Compare</div>
      <div class="results-context__note">Baseline run ${escapeHtml(currentBaselineRunId())} (version ${escapeHtml(currentBaselineVersionId() || "-")}) vs selected candidate ${escapeHtml(candidate.version_id || "-")} on persisted rerun ${escapeHtml(candidateRun.run_id)}.</div>
    </section>
    ${renderDecisionReadyCompare(compareState.data, { baselineLabel: "Baseline", candidateLabel: "Selected Candidate" })}
    <section class="results-context">
      <div class="results-context__note">Decision evidence is grounded in persisted run summaries, request snapshots, and version artifacts only. Use this evidence before choosing Accept as current strategy or Promote as new strategy variant.</div>
    </section>
  `;
}

function classifyDelta(key, delta) {
  const number = Number(delta);
  if (!Number.isFinite(number) || number === 0) return "";
  if (key === "max_drawdown_pct") {
    return number < 0 ? "positive" : "negative";
  }
  return number > 0 ? "positive" : "negative";
}

function render() {
  if (!root) return;

  if (!resolveStrategy()) {
    renderEmptyState("Select a strategy, then run a backtest to unlock the candidate workflow.");
    return;
  }
  if (!latestPayload) {
    renderEmptyState("Run or load a completed backtest. Proposal Workflow appears here once diagnosis is ready.");
    return;
  }
  if (latestPayload?.diagnosis_status !== "ready" || !latestPayload?.summary_available) {
    renderEmptyState("Backtest results are loaded, but diagnosis is not ready yet. Wait for Primary Issues and candidate actions to finish loading.");
    return;
  }

  const rankedIssues = Array.isArray(latestPayload?.diagnosis?.ranked_issues) ? latestPayload.diagnosis.ranked_issues : [];
  const parameterHints = Array.isArray(latestPayload?.diagnosis?.parameter_hints) ? latestPayload.diagnosis.parameter_hints : [];
  const deterministic_actions = Array.isArray(latestPayload?.diagnosis?.proposal_actions) ? latestPayload.diagnosis.proposal_actions : [];
  const aiSuggestions = latestPayload?.ai?.ai_status === "ready" && Array.isArray(latestPayload?.ai?.parameter_suggestions)
    ? latestPayload.ai.parameter_suggestions
    : [];
  const aiNote = latestPayload?.ai?.ai_status === "unavailable"
    ? "AI suggestions are unavailable for this run right now. Deterministic proposal sources remain usable."
    : "No AI parameter suggestions were returned for this run.";

  root.innerHTML = `
    ${renderWorkflowIntro()}
    ${renderPrimaryIssues()}
    ${renderActionSection({
      title: "Deterministic Actions",
      sourceKind: "deterministic_action",
      items: deterministic_actions,
      note: "No deterministic actions are recommended for this run based on the diagnosis flags.",
      renderer: renderDeterministicAction,
    })}
    ${renderActionSection({
      title: "Ranked Issues",
      sourceKind: "ranked_issue",
      items: rankedIssues,
      note: "No ranked issues are available for this run.",
      renderer: renderRankedIssue,
    })}
    ${renderActionSection({
      title: "Parameter Hints",
      sourceKind: "parameter_hint",
      items: parameterHints,
      note: "No deterministic parameter hints are available for this run.",
      renderer: renderParameterHint,
    })}
    ${renderActionSection({
      title: "AI Parameter Suggestions",
      sourceKind: "ai_parameter_suggestion",
      items: aiSuggestions,
      note: aiNote,
      renderer: renderAiSuggestion,
    })}
    ${renderWorkflowState()}
    ${renderCompareSection()}
  `;
}

async function loadVersions(strategy, options = {}) {
  if (!strategy) {
    setSelectedCandidateVersionId(null);
    await refreshPersistedVersions("", options);
    render();
    return;
  }

  await refreshPersistedVersions(strategy, { silent: Boolean(options?.silent) });
}

function handleVersionsSnapshot(snapshot) {
  versionsState = snapshot || { status: "idle", strategy: "", versions: [], activeVersionId: null, error: null };
  if (canShowWorkflow()) {
    syncWorkflowCandidateSelection();
  }
  render();
  void ensureCompareLoaded();
}

async function ensureCompareLoaded() {
  if (!canShowWorkflow()) {
    compareState = { status: "idle", key: "", data: null, error: null };
    render();
    return;
  }

  const candidateRun = currentComparableCandidateRun();
  if (!candidateRun) {
    compareState = { status: "idle", key: "", data: null, error: null };
    render();
    return;
  }

  const key = `${currentBaselineRunId()}:${candidateRun.run_id}`;
  if (compareState.key === key && (compareState.status === "ready" || compareState.status === "loading")) {
    return;
  }

  const requestId = ++compareRequestId;
  compareState = { status: "loading", key, data: null, error: null };
  render();

  try {
    const comparison = await api.backtest.compareRuns(currentBaselineRunId(), candidateRun.run_id);
    if (requestId !== compareRequestId) return;
    compareState = { status: "ready", key, data: comparison, error: null };
    render();
  } catch (error) {
    if (requestId !== compareRequestId) return;
    compareState = { status: "error", key, data: null, error: error?.message || String(error) };
    render();
  }
}

async function handleCreateCandidate(sourceKind, sourceIndex, actionType) {
  const baselineRunId = currentBaselineRunId();
  if (!baselineRunId) {
    showToast("No baseline run is loaded for proposal creation.", "warning");
    return;
  }

  busyAction = `create:${sourceKind}:${sourceIndex}`;
  render();

  try {
    const payload = {
      source_kind: sourceKind,
      source_index: Number(sourceIndex),
      candidate_mode: "auto",
    };
    if (actionType) {
      payload.action_type = actionType;
    }
    const response = await api.backtest.createProposalCandidate(baselineRunId, payload);
    if (response?.candidate_version_id) {
      setSelectedCandidateVersionId(response.candidate_version_id);
    }
    showToast(response?.candidate_version_id ? `Candidate ${response.candidate_version_id} created.` : "Candidate created.", "success");
    await refreshPersistedVersions(resolveStrategy(), { silent: true });
    await ensureCompareLoaded();
  } catch (error) {
    showToast(`Failed to create candidate: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

async function handleRerunCandidate() {
  const candidate = currentCandidateVersion();
  const baselineRunId = currentBaselineRunId();
  if (!candidate?.version_id || !baselineRunId) {
    showToast("Candidate rerun context is incomplete.", "warning");
    return;
  }

  busyAction = "rerun-candidate";
  render();

  try {
    const response = await api.backtest.getRun(baselineRunId);
    const baselineRun = response?.run;
    const snapshot = isObject(baselineRun?.request_snapshot) ? baselineRun.request_snapshot : null;
    if (!snapshot?.strategy || !snapshot?.timeframe) {
      throw new Error("Baseline run request snapshot is missing required strategy launch fields.");
    }

    await startBacktestRun({
      strategy: snapshot.strategy,
      timeframe: snapshot.timeframe,
      timerange: snapshot.timerange || undefined,
      pairs: Array.isArray(snapshot.pairs) ? snapshot.pairs : [],
      exchange: snapshot.exchange || "binance",
      max_open_trades: snapshot.max_open_trades ?? undefined,
      dry_run_wallet: snapshot.dry_run_wallet ?? undefined,
      config_path: snapshot.config_path || undefined,
      extra_flags: Array.isArray(snapshot.extra_flags) ? snapshot.extra_flags : [],
      version_id: candidate.version_id,
      trigger_source: "ai_apply",
    });
  } catch (error) {
    showToast(`Failed to start candidate rerun: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

async function handleAcceptCandidate() {
  const strategy = resolveStrategy();
  const candidate = currentCandidateVersion();
  if (!strategy || !candidate?.version_id) {
    showToast("No candidate is available to accept.", "warning");
    return;
  }
  if (!requiresExactBaselineVersion()) {
    showToast("Baseline run is missing an exact version link, so accept stays disabled for this workflow.", "warning");
    return;
  }

  const decision = await openAcceptDecisionDialog();
  if (decision === null) return;

  busyAction = "accept-candidate";
  render();

  try {
    const response = await api.versions.accept(strategy, {
      version_id: candidate.version_id,
      notes: decision.note || undefined,
      promotion_mode: decision.promotionMode || "accept_current",
      new_strategy_name: decision.newStrategyName || undefined,
    });
    if (response?.promotion_mode === "promote_new_strategy" && response?.new_strategy_name) {
      await loadOptions();
      if (switchBacktestStrategy(response.new_strategy_name)) {
        showToast(response?.message || `Promoted ${candidate.version_id} as new strategy ${response.new_strategy_name}. Switched to the new strategy.`, "success");
      } else {
        showToast(`Promoted ${candidate.version_id} as ${response.new_strategy_name}, but the strategy selector could not switch automatically.`, "warning");
        await refreshPersistedVersions(strategy, { silent: true });
      }
    } else {
      showToast(response?.message || `Accepted ${candidate.version_id}.`, "success");
      await refreshPersistedVersions(strategy, { silent: true });
    }
  } catch (error) {
    showToast(`Failed to accept candidate: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

async function handleRejectCandidate() {
  const strategy = resolveStrategy();
  const candidate = currentCandidateVersion();
  if (!strategy || !candidate?.version_id) {
    showToast("No candidate is available to reject.", "warning");
    return;
  }

  const reason = await openDecisionNoteDialog({
    title: "Reject Candidate",
    label: "Decision note",
    confirmLabel: "Reject Candidate",
    placeholder: "Why this candidate should stay out of the live strategy.",
    contextHtml: buildDecisionContextHtml({
      title: "Decision target",
      fields: [
        ["Strategy", strategy],
        ["Selected candidate", candidate.version_id],
        ["Candidate source", candidate?.source_context?.title || candidate?.summary || candidate?.source_ref || "Selected candidate"],
      ],
      note: `Reject marks candidate ${candidate.version_id} as rejected and leaves the live ${strategy} strategy untouched.`,
    }),
  });
  if (reason === null) return;

  busyAction = "reject-candidate";
  render();

  try {
    const response = await api.versions.reject(strategy, {
      version_id: candidate.version_id,
      reason: reason || undefined,
    });
    showToast(response?.message || `Rejected ${candidate.version_id}.`, "success");
    await refreshPersistedVersions(strategy, { silent: true });
  } catch (error) {
    showToast(`Failed to reject candidate: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

async function handleRollbackBaseline() {
  const strategy = resolveStrategy();
  const baselineVersionId = currentBaselineVersionId();
  if (!strategy || !baselineVersionId) {
    showToast("Baseline version is unavailable for rollback.", "warning");
    return;
  }

  const reason = await openDecisionNoteDialog({
    title: "Rollback Baseline",
    label: "Decision note",
    confirmLabel: "Rollback to Baseline",
    placeholder: "Why the workflow should return to the baseline version.",
    contextHtml: buildDecisionContextHtml({
      title: "Rollback target",
      fields: [
        ["Strategy", strategy],
        ["Rollback version", baselineVersionId],
        ["Current live version", versionsState.activeVersionId || baselineVersionId],
      ],
      note: `Rollback restores version ${baselineVersionId} as the live ${strategy} target and archives the currently active version.`,
    }),
  });
  if (reason === null) return;

  busyAction = "rollback-baseline";
  render();

  try {
    const response = await api.versions.rollback(strategy, {
      target_version_id: baselineVersionId,
      reason: reason || undefined,
    });
    showToast(response?.message || `Rolled back to ${baselineVersionId}.`, "success");
    await refreshPersistedVersions(strategy, { silent: true });
  } catch (error) {
    showToast(`Failed to rollback baseline: ${error?.message || String(error)}`, "error");
  } finally {
    busyAction = "";
    render();
  }
}

function handleRootChange(event) {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement)) return;
  if (target.dataset.role !== "selected-candidate") return;
  setSelectedCandidateVersionId(target.value || null);
}

function handleRootClick(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action || "";

  if (action === "create-candidate") {
    const sourceKind = button.dataset.sourceKind || "";
    const sourceIndex = button.dataset.sourceIndex || "0";
    const actionType = button.dataset.actionType || null;
    void handleCreateCandidate(sourceKind, sourceIndex, actionType);
    return;
  }
  if (action === "rerun-candidate") {
    void handleRerunCandidate();
    return;
  }
  if (action === "accept-candidate") {
    void handleAcceptCandidate();
    return;
  }
  if (action === "reject-candidate") {
    void handleRejectCandidate();
    return;
  }
  if (action === "rollback-baseline") {
    void handleRollbackBaseline();
  }
}

export function initProposalWorkflow() {
  if (!root) return;

  initPersistedRunsStore();
  initPersistedVersionsStore();
  root.addEventListener("click", handleRootClick);
  root.addEventListener("change", handleRootChange);
  subscribePersistedRuns((snapshot) => {
    runsSnapshot = snapshot || { status: "idle", strategy: "", runs: [], error: null };
    render();
    void ensureCompareLoaded();
  });

  subscribePersistedVersions(handleVersionsSnapshot);

  on(EVENTS.RESULTS_LOADED, (payload) => {
    latestPayload = payload || null;
    if (!canShowWorkflow()) {
      setSelectedCandidateVersionId(null);
    }
    render();
    void loadVersions(resolveStrategy(), { silent: false });
  });

  onState("backtest.selectedCandidateVersionId", () => {
    render();
    void ensureCompareLoaded();
  });

  render();
}
