import api from "../core/api.js";
import { getState, on as onState } from "../core/state.js";
import { emit, on as onEvent, EVENTS } from "../core/events.js";
import persistence, { KEYS } from "../core/persistence.js";
import showToast from "./toast.js";
import { setButtonLoading } from "./loading-state.js";
import { copyToClipboard } from "../core/utils.js";
import { setSelectedCandidateVersionId } from "../pages/backtesting/compare/candidate-selection-state.js";

const panel = document.getElementById("ai-chat-panel");
const backdrop = document.getElementById("ai-chat-backdrop");
const openBtn = document.getElementById("btn-open-ai-chat");
const closeBtn = document.getElementById("close-chat");
const messagesEl = document.getElementById("chat-messages");
const inputEl = document.getElementById("chat-input");
const sendBtn = document.getElementById("btn-send-chat");

const POLL_INTERVAL_MS = 1200;
const MAX_LIVE_EVENTS = 24;

const COPY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>';
const APPLY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"/></svg>';
const REDO_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.73 10h-2.08A6.01 6.01 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>';

const state = {
  isInitialized: false,
  isOpen: false,
  isBacktestingPage: false,
  latestContext: loadContext(),
  overlays: loadOverlays(),
  currentVersion: null,
  currentVersionSource: "none",
  thread: { strategy_name: "", messages: [], latest_context: {}, active_job: null },
  latestResultsPayload: null,
  activeJobId: null,
  pollTimer: null,
  streamSource: null,
  requestInFlight: false,
  threadLoadToken: 0,
  versionLookupToken: 0,
  liveTimeline: [],
  liveDraft: "",
  deliveredEventSeq: 0,
  liveProvider: "",
  liveModel: "",
  liveStatusText: "",
  lastRedoTrace: null,
};

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function hasKeys(value) {
  return isObject(value) && Object.keys(value).length > 0;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function compactText(value, max = 220) {
  const text = String(value || "").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max)}...`;
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
  return String(value || "unknown").replace(/_/g, " ");
}

function defaultContext(strategy = "") {
  return {
    strategy,
    run_id: null,
    version_id: null,
    diagnosis_status: null,
    summary_available: false,
    version_source: "none",
  };
}

function normalizeContext(context) {
  const raw = isObject(context) ? context : {};
  return {
    strategy: String(raw.strategy || raw.strategy_name || "").trim(),
    run_id: raw.run_id || null,
    version_id: raw.version_id || null,
    diagnosis_status: raw.diagnosis_status || null,
    summary_available: Boolean(raw.summary_available),
    version_source: raw.version_source || "none",
  };
}

function loadContext() {
  return normalizeContext(persistence.load(KEYS.AI_CHAT_CONTEXT, {}));
}

function saveContext(nextContext) {
  const normalized = normalizeContext(nextContext);
  state.latestContext = normalized;
  persistence.save(KEYS.AI_CHAT_CONTEXT, normalized);
  return normalized;
}

function loadOverlays() {
  const raw = persistence.load(KEYS.AI_CHAT_MESSAGE_OVERLAYS, {});
  return isObject(raw) ? raw : {};
}

function saveOverlays() {
  persistence.save(KEYS.AI_CHAT_MESSAGE_OVERLAYS, state.overlays);
}

function persistUiState() {
  persistence.save(KEYS.AI_CHAT_UI_STATE, {
    open: state.isOpen,
    draft: String(inputEl?.value || ""),
  });
}

function loadUiState() {
  const raw = persistence.load(KEYS.AI_CHAT_UI_STATE, {});
  return isObject(raw) ? raw : {};
}

function currentSavedBacktestStrategy() {
  const savedConfig = persistence.load(KEYS.BACKTEST_CONFIG, {});
  return String(savedConfig?.strategy || "").trim();
}

function resolveStrategy() {
  const liveStrategy = String(getState("backtest.strategy") || "").trim();
  if (liveStrategy) return liveStrategy;

  if (state.isBacktestingPage) {
    const savedStrategy = currentSavedBacktestStrategy();
    if (savedStrategy) return savedStrategy;
  }

  const contextStrategy = String(state.latestContext?.strategy || "").trim();
  if (contextStrategy) return contextStrategy;

  return "";
}

function canUseAssistant(strategy = resolveStrategy()) {
  if (!strategy) return false;
  if (state.isBacktestingPage) return true;
  return Boolean(state.latestContext.strategy === strategy && state.latestContext.run_id);
}

function currentContext(strategy = resolveStrategy()) {
  if (!strategy) return defaultContext("");
  if (state.latestContext.strategy === strategy) {
    return normalizeContext(state.latestContext);
  }
  return defaultContext(strategy);
}

function currentRunReady() {
  const context = currentContext();
  return Boolean(context.run_id && context.diagnosis_status === "ready" && context.summary_available);
}

function describeCandidateCreationState(context = currentContext()) {
  const normalized = normalizeContext(context);
  if (!normalized.run_id) {
    return {
      ready: false,
      headline: "Candidate creation requires a completed diagnosed run.",
      reason: "No run/diagnosis context yet. Load a completed run before staging a candidate.",
    };
  }
  if (!normalized.summary_available) {
    return {
      ready: false,
      headline: "Candidate creation requires a completed diagnosed run.",
      reason: "The loaded run does not have a persisted summary artifact yet.",
    };
  }
  if (normalized.diagnosis_status !== "ready") {
    return {
      ready: false,
      headline: "Candidate creation requires a completed diagnosed run.",
      reason: `Candidate staging unavailable for this message until a completed run diagnosis is loaded. Current diagnosis status: ${labelize(normalized.diagnosis_status || "pending")}.`,
    };
  }
  return {
    ready: true,
    headline: "Candidate creation is enabled for this diagnosed run.",
    reason: "Versioned candidate staging can use the current run and version context.",
  };
}


function normalizeCandidateOverlay(entry) {
  const raw = isObject(entry) ? entry : {};
  const normalized = {};

  const assign = (key, value) => {
    if (value === null || value === undefined || value === "") return;
    normalized[key] = value;
  };

  assign("baseline_run_id", raw.baseline_run_id);
  assign("baseline_version_id", raw.baseline_version_id);
  assign("baseline_run_version_id", raw.baseline_run_version_id);
  assign("baseline_version_source", raw.baseline_version_source);
  assign("candidate_version_id", raw.candidate_version_id || raw.version_id);
  assign("candidate_change_type", raw.candidate_change_type);
  assign("candidate_status", raw.candidate_status);
  assign("source_kind", raw.source_kind);
  if (raw.source_index !== undefined && raw.source_index !== null && raw.source_index !== "") {
    const parsedIndex = Number(raw.source_index);
    assign("source_index", Number.isFinite(parsedIndex) ? parsedIndex : raw.source_index);
  }
  assign("source_title", raw.source_title);
  assign("candidate_ai_mode", raw.candidate_ai_mode);
  assign("message", raw.message || raw.note);

  return normalized;
}

function mergedMessages() {
  const strategy = resolveStrategy();
  const overlays = isObject(state.overlays?.[strategy]) ? state.overlays[strategy] : {};
  return safeArray(state.thread?.messages).map((message) => {
    const candidateMeta = {
      ...normalizeCandidateOverlay(message),
      ...normalizeCandidateOverlay(overlays?.[message?.id]),
    };
    return {
      ...message,
      ...candidateMeta,
      candidate_note: candidateMeta.message || "",
    };
  });
}

function rememberCandidateOverlay(strategy, messageId, payload) {
  if (!strategy || !messageId) return;
  if (!isObject(state.overlays[strategy])) {
    state.overlays[strategy] = {};
  }
  state.overlays[strategy][messageId] = normalizeCandidateOverlay(payload);
  saveOverlays();
}

function resetLiveState() {
  state.liveTimeline = [];
  state.liveDraft = "";
  state.deliveredEventSeq = 0;
  state.liveProvider = "";
  state.liveModel = "";
  state.liveStatusText = "";
}

function closeLiveStream() {
  if (state.streamSource) {
    state.streamSource.close();
    state.streamSource = null;
  }
}

function stopPollingTimer() {
  if (state.pollTimer) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function stopJobTracking({ clearLiveState = true } = {}) {
  closeLiveStream();
  stopPollingTimer();
  state.activeJobId = null;
  state.requestInFlight = false;
  if (clearLiveState) {
    resetLiveState();
  }
  updateComposerState();
}

function appendLiveEvent(event) {
  if (!isObject(event)) return;
  if (event.type === "stream_delta") return;
  state.liveTimeline.push(event);
  if (state.liveTimeline.length > MAX_LIVE_EVENTS) {
    state.liveTimeline = state.liveTimeline.slice(-MAX_LIVE_EVENTS);
  }
}

function applyLiveEvent(event) {
  const seq = Number(event?.seq || 0);
  if (seq && seq <= state.deliveredEventSeq) {
    return false;
  }
  if (seq) {
    state.deliveredEventSeq = seq;
  }
  if (event?.provider) state.liveProvider = String(event.provider || "");
  if (event?.model) state.liveModel = String(event.model || "");
  if (event?.message && event.type !== "stream_delta") {
    state.liveStatusText = String(event.message || "");
  }
  if (event?.type === "stream_delta" && event?.delta) {
    state.liveDraft += String(event.delta || "");
  }
  appendLiveEvent(event);
  render();
  return true;
}

function renderTimelineEvent(event) {
  const label = labelize(event?.type || "status");
  const detail = compactText(
    event?.message
      || event?.detail
      || event?.recommended_pipeline
      || (event?.task_types ? safeArray(event.task_types).join(", ") : "")
      || (event?.provider ? `${event.provider}${event.model ? ` / ${event.model}` : ""}` : ""),
    160,
  );
  return `
    <li class="ai-live-event ai-live-event--${escapeHtml(event?.type || "status")}">
      <span class="ai-live-event__label">${escapeHtml(label)}</span>
      ${detail ? `<span class="ai-live-event__detail">${escapeHtml(detail)}</span>` : ""}
    </li>
  `;
}

async function refreshVersionContext() {
  const strategy = resolveStrategy();
  const lookupToken = ++state.versionLookupToken;

  state.currentVersion = null;
  state.currentVersionSource = strategy ? "loading" : "none";
  render();

  if (!strategy) {
    state.currentVersionSource = "none";
    render();
    return;
  }

  let version = null;
  let source = "none";
  const context = currentContext(strategy);
  const contextVersionId = context.strategy === strategy ? context.version_id : null;

  if (contextVersionId) {
    try {
      version = await api.versions.getVersion(strategy, contextVersionId);
      source = context.version_source && context.version_source !== "none" ? context.version_source : "run";
    } catch (error) {
      console.debug("[ai-chat] Unable to load run-linked version context:", error);
    }
  }

  if (!version) {
    try {
      version = await api.versions.getActive(strategy);
      source = "active";
    } catch (error) {
      console.debug("[ai-chat] Unable to load active version context:", error);
    }
  }

  if (lookupToken !== state.versionLookupToken) return;

  state.currentVersion = version || null;
  state.currentVersionSource = version ? source : "none";

  if (version) {
    saveContext({
      ...currentContext(strategy),
      strategy,
      version_id: version.version_id || contextVersionId,
      version_source: state.currentVersionSource,
    });
  }

  render();
}

function handleStreamDisconnect(jobId) {
  if (state.activeJobId !== jobId) return;
  closeLiveStream();
  state.liveStatusText = "Live stream disconnected. Falling back to polling.";
  render();
  startPolling(jobId);
}

function startStream(jobId) {
  closeLiveStream();
  try {
    const source = api.aiChat.streamJob(jobId);
    state.streamSource = source;
    source.onmessage = (event) => {
      let payload = null;
      try {
        payload = JSON.parse(event.data);
      } catch {
        payload = null;
      }
      if (!payload || state.activeJobId !== jobId) return;
      if (!applyLiveEvent(payload)) return;
      if (payload.type === "completed") {
        void finalizeJob(jobId, "completed", payload);
      } else if (payload.type === "failed") {
        void finalizeJob(jobId, payload.interrupted ? "interrupted" : "failed", payload);
      }
    };
    source.onerror = () => {
      handleStreamDisconnect(jobId);
    };
  } catch (error) {
    console.warn("[ai-chat] Failed to open live stream:", error);
    startPolling(jobId);
  }
}

function startJobTracking(jobId) {
  if (!jobId) return;
  if (state.activeJobId === jobId && (state.streamSource || state.pollTimer)) {
    state.requestInFlight = true;
    updateComposerState();
    render();
    return;
  }

  stopJobTracking();
  state.activeJobId = jobId;
  state.requestInFlight = true;
  resetLiveState();
  updateComposerState();
  render();
  startStream(jobId);
}

function startPolling(jobId) {
  if (!jobId) return;
  stopPollingTimer();
  state.activeJobId = jobId;
  state.requestInFlight = true;
  updateComposerState();
  render();
  void pollJob(jobId);
}

async function finalizeJob(jobId, status, payload = null) {
  if (state.activeJobId !== jobId) return;
  closeLiveStream();
  stopPollingTimer();
  const strategy = resolveStrategy();
  state.requestInFlight = false;
  updateComposerState();

  await loadThread(strategy);

  if (status === "completed") {
    showToast("AI response ready.", "success", 2500);
  } else if (status === "interrupted") {
    showToast("The previous AI request was interrupted.", "warning", 3500);
  } else if (status === "failed") {
    showToast(`AI request failed: ${payload?.message || payload?.error || "unknown error"}`, "error");
  }
}

async function pollJob(jobId) {
  try {
    const response = await api.aiChat.getJob(jobId);
    if (state.activeJobId !== jobId) return;

    const job = response?.job;
    if (!job) {
      throw new Error("AI job payload missing");
    }

    if (job.status === "queued" || job.status === "running") {
      state.requestInFlight = true;
      updateComposerState();
      render();
      state.pollTimer = window.setTimeout(() => {
        void pollJob(jobId);
      }, POLL_INTERVAL_MS);
      return;
    }

    await finalizeJob(jobId, job.status, job);
  } catch (error) {
    if (state.activeJobId !== jobId) return;
    console.warn("[ai-chat] Polling failed, retrying:", error);
    state.pollTimer = window.setTimeout(() => {
      void pollJob(jobId);
    }, POLL_INTERVAL_MS + 300);
  }
}

async function loadThread(strategy = resolveStrategy()) {
  const token = ++state.threadLoadToken;

  if (!strategy) {
    state.thread = { strategy_name: "", messages: [], latest_context: {}, active_job: null };
    stopJobTracking();
    render();
    return;
  }

  try {
    const response = await api.aiChat.getThread(strategy);
    if (token !== state.threadLoadToken || resolveStrategy() !== strategy) return;

    state.thread = isObject(response) ? response : { strategy_name: strategy, messages: [], latest_context: {}, active_job: null };
    const serverContext = normalizeContext({ ...(response?.latest_context || {}), strategy });
    if (serverContext.strategy && (serverContext.run_id || serverContext.version_id || state.latestContext.strategy !== strategy)) {
      saveContext({ ...currentContext(strategy), ...serverContext, strategy });
    }

    const activeJob = response?.active_job;
    if (activeJob?.job_id) {
      startJobTracking(activeJob.job_id);
    } else {
      stopJobTracking();
    }

    render();
  } catch (error) {
    if (token !== state.threadLoadToken) return;
    console.warn("[ai-chat] Failed to load strategy thread:", error);
    state.thread = { strategy_name: strategy, messages: [], latest_context: {}, active_job: null };
    stopJobTracking();
    render();
  }
}

async function refreshConversation() {
  await refreshVersionContext();
  await loadThread();
}

function renderRecommendations(message) {
  const items = safeArray(message?.recommendations).filter(Boolean);
  if (!items.length) return "";
  return `<ul class="ai-chat-message__list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function payloadText(message, payloadKind) {
  if (payloadKind === "parameters" && Array.isArray(message?.suggestions) && message.suggestions.length) {
    return JSON.stringify({ suggestions: message.suggestions }, null, 2);
  }
  if (payloadKind === "parameters" && hasKeys(message?.parameters)) {
    return JSON.stringify(message.parameters, null, 2);
  }
  if (payloadKind === "code" && typeof message?.code === "string" && message.code.trim()) {
    return message.code.trim();
  }
  return "";
}

function messageContentForCopy(message) {
  const parts = [];
  const title = message?.title || (message?.role === "user" ? "You" : message?.role === "assistant" ? "AI" : "Panel");
  if (title) parts.push(String(title).trim());
  if (message?.meta) parts.push(String(message.meta).trim());
  if (message?.text) parts.push(String(message.text).trim());
  const recommendations = safeArray(message?.recommendations).filter(Boolean);
  if (recommendations.length) {
    parts.push(recommendations.map((item) => `- ${item}`).join("\n"));
  }
  const parameters = payloadText(message, "parameters");
  if (parameters) parts.push(parameters);
  const code = payloadText(message, "code");
  if (code) parts.push(code);
  const note = message?.candidate_note || message?.note || "";
  if (note) parts.push(String(note).trim());
  if (message?.candidate_version_id) {
    const status = message?.candidate_status ? ` (${message.candidate_status})` : "";
    parts.push(`Candidate version ${message.candidate_version_id}${status}`);
  }
  return parts.filter(Boolean).join("\n\n");
}

function renderIconButton({ action, messageId, payloadKind = "", label, icon, disabled = false }) {
  const payloadAttr = payloadKind ? ` data-payload-kind="${escapeHtml(payloadKind)}"` : "";
  return `<button type="button" class="ai-chat-icon-btn" data-action="${escapeHtml(action)}" data-message-id="${escapeHtml(messageId)}"${payloadAttr} aria-label="${escapeHtml(label)}" title="${escapeHtml(label)}"${disabled ? " disabled" : ""}>${icon}</button>`;
}

function renderPayloadActions(message, payloadKind) {
  const actions = [
    renderIconButton({
      action: "copy-payload",
      messageId: message.id,
      payloadKind,
      label: payloadKind === "code" ? "Copy code" : "Copy parameters",
      icon: COPY_ICON,
    }),
  ];

  if (!message?.candidate_version_id) {
    const currentPayload = payloadText(message, payloadKind);
    const canStage = Boolean(currentPayload && currentRunReady() && !state.requestInFlight);
    actions.push(renderIconButton({
      action: payloadKind === "code" ? "apply-code" : "apply-parameters",
      messageId: message.id,
      payloadKind,
      label: payloadKind === "code" ? "Create code candidate" : "Create parameter candidate",
      icon: APPLY_ICON,
      disabled: !canStage,
    }));
  }

  return `<div class="ai-chat-message__payload-actions">${actions.join("")}</div>`;
}

function renderPayloadBlock(message, payloadKind, cssClass = "") {
  const text = payloadText(message, payloadKind);
  if (!text) return "";
  return `
    <div class="ai-chat-message__payload-shell">
      ${renderPayloadActions(message, payloadKind)}
      <pre class="ai-chat-message__payload${cssClass}">${escapeHtml(text)}</pre>
    </div>
  `;
}

function renderRunNotReadyNote(message) {
  if (message?.candidate_version_id) return "";
  const hasCandidatePayload = Boolean(payloadText(message, "parameters") || payloadText(message, "code"));
  if (!hasCandidatePayload || currentRunReady()) return "";

  const candidateState = describeCandidateCreationState(currentContext());
  return `
    <div class="ai-chat-message__note ai-chat-message__note--context-state">
      <strong>${escapeHtml(candidateState.headline)}</strong>
      <span>${escapeHtml(candidateState.reason)}</span>
    </div>
  `;
}


function renderMessageCopyButton(message) {
  if (!message?.id) return "";
  return renderIconButton({
    action: "copy-message",
    messageId: message.id,
    label: "Copy message",
    icon: COPY_ICON,
  }).replace('class="ai-chat-icon-btn"', 'class="ai-chat-icon-btn ai-chat-copy-message-btn"');
}

function renderRedoActionRow(message) {
  if (message?.role !== "assistant" || !message?.id) return "";
  return `
    <div class="ai-chat-redo-row">
      <button type="button" class="ai-chat-redo-btn" data-action="redo-message" data-message-id="${escapeHtml(message.id)}" aria-label="Regenerate response" title="Regenerate response"${state.requestInFlight ? " disabled" : ""}>${REDO_ICON}<span>Regenerate</span></button>
    </div>
  `;
}

function renderStatusMessage() {
  const strategy = resolveStrategy();
  if (!strategy) {
    return `
      <article class="ai-chat-message ai-chat-message--system ai-chat-message--status ai-chat-message--label">
        <div class="ai-chat-message__header">
          <span class="ai-chat-message__role">AI Panel</span>
        </div>
        <div class="ai-chat-message__body">Select a strategy in Backtesting to enable the assistant.</div>
      </article>
    `;
  }

  if (!canUseAssistant(strategy)) {
    return `
      <article class="ai-chat-message ai-chat-message--system ai-chat-message--status ai-chat-message--label">
        <div class="ai-chat-message__header">
          <span class="ai-chat-message__role">Grounding Required</span>
        </div>
        <div class="ai-chat-message__body">Load a persisted run from Backtesting first. The shared drawer stays grounded in saved backtest context and does not become a generic app chat.</div>
      </article>
    `;
  }

  const context = currentContext(strategy);
  const versionId = context.version_id || state.currentVersion?.version_id || "Unavailable";
  const resultState = context.summary_available
    ? "Latest persisted run summary loaded"
    : state.isBacktestingPage
      ? "No latest persisted run summary loaded"
      : "Using the last saved backtesting snapshot";

  const effectiveVersionSource = state.currentVersionSource !== "none" ? state.currentVersionSource : context.version_source;
  let versionSourceLabel = "Version context unavailable";
  if (effectiveVersionSource === "run") versionSourceLabel = "Run-linked version snapshot";
  if (effectiveVersionSource === "active") versionSourceLabel = "Active version fallback";
  if (effectiveVersionSource === "loading") versionSourceLabel = "Loading version context";
  const candidateCreationState = describeCandidateCreationState(context);

  return `
    <article class="ai-chat-message ai-chat-message--system ai-chat-message--status">
      <div class="ai-chat-message__header">
        <span class="ai-chat-message__role">Grounded Context</span>
        <span class="ai-chat-message__meta">${escapeHtml(state.isBacktestingPage ? "live page context" : "saved backtesting snapshot")}</span>
      </div>
      <div class="ai-chat-message__context">
        <span><strong>Strategy:</strong> ${escapeHtml(strategy)}</span>
        <span><strong>Run:</strong> ${escapeHtml(context.run_id || "No latest run loaded")}</span>
        <span><strong>Version:</strong> ${escapeHtml(versionId)}</span>
        <span><strong>Version Source:</strong> ${escapeHtml(versionSourceLabel)}</span>
        <span><strong>Result Context:</strong> ${escapeHtml(resultState)}</span>
        <span><strong>Code Context:</strong> ${escapeHtml(state.currentVersion?.code_snapshot ? "Code snapshot ready" : "Code snapshot unavailable")}</span>
      </div>
      <div class="ai-chat-message__note ai-chat-message__note--context-state${candidateCreationState.ready ? " is-ready" : ""}">
        <strong>${escapeHtml(candidateCreationState.headline)}</strong>
        <span>${escapeHtml(candidateCreationState.reason)}</span>
      </div>
      <div class="ai-chat-message__note">Use this drawer to explain diagnosed runs, regenerate replies, copy returned parameters or code, and create a versioned candidate from those payloads once run context is ready.</div>
    </article>
  `;
}

function renderActiveJobMessage() {
  if (!state.activeJobId) return "";
  const telemetry = state.liveProvider
    ? `${state.liveProvider}${state.liveModel ? ` / ${state.liveModel}` : ""}`
    : `server job ${state.activeJobId}`;
  const draft = state.liveDraft
    ? `<pre class="ai-chat-message__payload ai-chat-message__payload--code ai-chat-live-draft">${escapeHtml(state.liveDraft)}</pre>`
    : '<div class="ai-chat-message__note">Waiting for the model to start producing output?</div>';
  const timeline = state.liveTimeline.length
    ? `<ol class="ai-live-timeline">${state.liveTimeline.map(renderTimelineEvent).join("")}</ol>`
    : '<div class="ai-chat-message__note">Queued on the server. Live timeline events will appear here as the job advances.</div>';

  return `
    <article class="ai-chat-message ai-chat-message--system ai-chat-message--live">
      <div class="ai-chat-message__header">
        <span class="ai-chat-message__role">AI Live Timeline</span>
        <span class="ai-chat-message__meta">${escapeHtml(telemetry)}</span>
      </div>
      ${state.liveStatusText ? `<div class="ai-chat-message__body">${escapeHtml(state.liveStatusText)}</div>` : ""}
      ${timeline}
      <div class="ai-chat-live-draft-wrap">
        <div class="ai-chat-message__role">Assistant Draft</div>
        ${draft}
      </div>
    </article>
  `;
}

function renderMessage(message) {
  const body = message?.text ? `<div class="ai-chat-message__body">${escapeHtml(message.text)}</div>` : "";
  const recommendations = renderRecommendations(message);
  const parameters = renderPayloadBlock(message, "parameters");
  const code = renderPayloadBlock(message, "code", " ai-chat-message__payload--code");
  const noteText = message?.candidate_note || message?.note || "";
  const note = noteText ? `<div class="ai-chat-message__note">${escapeHtml(noteText)}</div>` : "";
  const versionNote = message?.candidate_version_id
    ? `<div class="ai-chat-message__note">Candidate version ${escapeHtml(message.candidate_version_id)}${message?.candidate_change_type ? ` (${escapeHtml(labelize(message.candidate_change_type))})` : ""} created${message?.candidate_status ? ` with ${escapeHtml(labelize(message.candidate_status))} status` : ""}. It remains pending until you explicitly accept it.</div>`
    : "";

  return `
    <article class="ai-chat-message ai-chat-message--${escapeHtml(message.role || "system")}" tabindex="-1">
      ${renderMessageCopyButton(message)}
      <div class="ai-chat-message__header">
        <span class="ai-chat-message__role">${escapeHtml(message.title || (message.role === "user" ? "You" : message.role === "assistant" ? "AI" : "Panel"))}</span>
        ${message?.meta ? `<span class="ai-chat-message__meta">${escapeHtml(message.meta)}</span>` : ""}
      </div>
      ${body}
      ${recommendations}
      ${parameters}
      ${code}
      ${renderRunNotReadyNote(message)}
      ${note}
      ${versionNote}
      ${renderRedoActionRow(message)}
    </article>
  `;
}

function renderTranscript() {
  if (!messagesEl) return;
  const strategy = resolveStrategy();
  const messages = mergedMessages();

  if (!strategy && !messages.length) {
    messagesEl.innerHTML = '<div class="chat-panel__empty">Select a strategy in Backtesting to enable the assistant.</div>';
    return;
  }

  if (!canUseAssistant(strategy) && !messages.length) {
    messagesEl.innerHTML = `${renderStatusMessage()}<div class="chat-panel__empty">No grounded conversation is available yet.</div>`;
    return;
  }

  const parts = [renderStatusMessage(), renderActiveJobMessage()];
  if (messages.length) {
    parts.push(messages.map(renderMessage).join(""));
  } else {
    parts.push('<div class="chat-panel__empty">No conversation yet. Ask the assistant to explain the grounded run, regenerate a reply, copy payloads, or generate a candidate.</div>');
  }

  messagesEl.innerHTML = parts.filter(Boolean).join("");
  if (state.isOpen) {
    requestAnimationFrame(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    });
  }
}

function updateComposerState() {
  const strategy = resolveStrategy();
  const usable = canUseAssistant(strategy);
  const disabled = !strategy || !usable || state.requestInFlight;

  if (inputEl) {
    inputEl.disabled = disabled;
  }
  if (sendBtn) {
    sendBtn.disabled = disabled;
    if (state.requestInFlight) {
      setButtonLoading(sendBtn, true, "Thinking...");
    } else {
      setButtonLoading(sendBtn, false);
    }
  }
}

function render() {
  updateComposerState();
  renderTranscript();
}

function setOpen(nextOpen, { persist = true } = {}) {
  state.isOpen = Boolean(nextOpen);
  panel?.classList.toggle("is-open", state.isOpen);
  backdrop?.classList.toggle("is-open", state.isOpen);
  panel?.setAttribute("aria-hidden", state.isOpen ? "false" : "true");
  openBtn?.setAttribute("aria-pressed", state.isOpen ? "true" : "false");
  if (persist) persistUiState();
}

function buildRequestContext(strategy) {
  const context = currentContext(strategy);
  return {
    strategy_name: strategy,
    run_id: context.run_id || null,
    version_id: context.version_id || state.currentVersion?.version_id || null,
    diagnosis_status: context.diagnosis_status || null,
    summary_available: Boolean(context.summary_available),
    version_source: context.version_source || state.currentVersionSource || "none",
  };
}

async function enqueuePrompt(prompt, { successToast = "AI request queued." } = {}) {
  const strategy = resolveStrategy();
  if (!strategy) {
    showToast("Select a strategy first.", "warning");
    return false;
  }

  if (!canUseAssistant(strategy)) {
    showToast("No run/diagnosis context yet. Load a persisted run from Backtesting first.", "warning");
    return false;
  }

  state.requestInFlight = true;
  updateComposerState();
  render();

  try {
    const response = await api.aiChat.createThreadMessage(strategy, {
      message: prompt,
      context: buildRequestContext(strategy),
    });

    await loadThread(strategy);
    if (response?.job_id) {
      startJobTracking(response.job_id);
    }
    showToast(successToast, "success", 2000);
    return true;
  } catch (error) {
    state.requestInFlight = false;
    updateComposerState();
    render();
    showToast(`AI request failed: ${error?.message || String(error)}`, "error");
    return false;
  }
}

async function handleSend() {
  if (state.requestInFlight) return;

  const prompt = String(inputEl?.value || "").trim();
  if (!prompt) {
    showToast("Enter a prompt first.", "warning");
    return;
  }

  const queued = await enqueuePrompt(prompt);
  if (queued && inputEl) {
    inputEl.value = "";
    persistUiState();
  }
}

function findSourceUserMessage(assistantMessageId) {
  const messages = mergedMessages();
  const assistantIndex = messages.findIndex((entry) => entry.id === assistantMessageId);
  if (assistantIndex < 0) return null;
  for (let index = assistantIndex - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role === "user" && String(message?.text || "").trim()) {
      return message;
    }
  }
  return null;
}

async function handleRedoAction(messageId) {
  if (state.requestInFlight) return;
  const sourceUserMessage = findSourceUserMessage(messageId);
  if (!sourceUserMessage) {
    showToast("Redo unavailable because no source user prompt was found.", "warning");
    return;
  }

  state.lastRedoTrace = {
    source_user_message_id: sourceUserMessage.id,
    redo_of_message_id: messageId,
  };

  await enqueuePrompt(String(sourceUserMessage.text || "").trim(), {
    successToast: "AI redo request queued.",
  });
}

function handleCopyMessage(messageId) {
  const message = mergedMessages().find((entry) => entry.id === messageId);
  const text = messageContentForCopy(message);
  if (!text) {
    showToast("Nothing to copy for this message.", "warning");
    return;
  }
  copyToClipboard(text);
  showToast("Message copied.", "success", 1600);
}

function handleCopyPayload(messageId, payloadKind) {
  const message = mergedMessages().find((entry) => entry.id === messageId);
  const text = payloadText(message, payloadKind);
  if (!text) {
    showToast("Nothing to copy for this payload.", "warning");
    return;
  }
  copyToClipboard(text);
  showToast(payloadKind === "code" ? "Code copied." : "Parameters copied.", "success", 1600);
}

async function handleApplyAction(messageId, action) {
  if (state.requestInFlight) return;

  const strategy = resolveStrategy();
  const context = currentContext(strategy);
  const message = mergedMessages().find((entry) => entry.id === messageId);
  if (!message || !strategy || !context.run_id) {
    showToast("No run/diagnosis context yet. Load a completed run before staging a candidate.", "warning");
    return;
  }
  if (!currentRunReady()) {
    showToast("Candidate staging unavailable for this message until a completed run diagnosis is loaded.", "warning");
    return;
  }

  state.requestInFlight = true;
  updateComposerState();
  render();

  try {
    const response = await api.backtest.createProposalCandidate(context.run_id, {
      source_kind: "ai_chat_draft",
      source_index: 0,
      candidate_mode: action === "apply-code" ? "code_patch" : "parameter_only",
      suggestions: action === "apply-parameters" && Array.isArray(message?.suggestions) ? message.suggestions : null,
      parameters: action === "apply-parameters" && !Array.isArray(message?.suggestions) ? message.parameters : null,
      code: action === "apply-code" ? message.code : null,
      summary: compactText(message.text || "AI chat candidate", 220),
    });
    rememberCandidateOverlay(strategy, messageId, response);
    if (response?.candidate_version_id) {
      setSelectedCandidateVersionId(response.candidate_version_id, context.run_id);
    }

    if (state.latestResultsPayload) {
      emit(EVENTS.RESULTS_LOADED, state.latestResultsPayload);
    }

    render();
    showToast(
      response?.candidate_version_id ? `Candidate version ${response.candidate_version_id} created.` : "Candidate version created.",
      "success",
    );
  } catch (error) {
    showToast(`Failed to create candidate: ${error?.message || String(error)}`, "error");
  } finally {
    state.requestInFlight = Boolean(state.activeJobId);
    updateComposerState();
    render();
  }
}

function handlePanelClick(event) {
  const actionButton = event.target.closest("[data-action]");
  if (!actionButton) return;

  const action = actionButton.dataset.action || "";
  const messageId = actionButton.dataset.messageId || "";
  if (action === "copy-message") {
    handleCopyMessage(messageId);
    return;
  }
  if (action === "copy-payload") {
    handleCopyPayload(messageId, actionButton.dataset.payloadKind || "");
    return;
  }
  if (action === "redo-message") {
    void handleRedoAction(messageId);
    return;
  }
  if (action === "apply-code" || action === "apply-parameters") {
    void handleApplyAction(messageId, action);
  }
}

function handleKeydown(event) {
  if (event.key === "Escape" && state.isOpen) {
    setOpen(false);
    return;
  }
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    void handleSend();
  }
}

function handleStrategyChange(strategyValue) {
  const strategy = String(strategyValue || "").trim();
  if (!state.isBacktestingPage) return;

  if (!strategy) {
    saveContext(defaultContext(""));
    state.thread = { strategy_name: "", messages: [], latest_context: {}, active_job: null };
    stopJobTracking();
    render();
    return;
  }

  const existing = currentContext(strategy);
  if (existing.strategy !== strategy || state.latestContext.strategy !== strategy) {
    saveContext(defaultContext(strategy));
  }
  void refreshConversation();
}

function handleResultsLoaded(payload) {
  state.latestResultsPayload = payload || null;
  if (!payload?.strategy) {
    render();
    return;
  }

  saveContext({
    strategy: payload.strategy,
    run_id: payload.run_id || null,
    version_id: payload.version_id || currentContext(payload.strategy).version_id || null,
    diagnosis_status: payload.diagnosis_status || null,
    summary_available: Boolean(payload.summary_available),
    version_source: state.currentVersionSource === "loading"
      ? currentContext(payload.strategy).version_source || "none"
      : state.currentVersionSource || currentContext(payload.strategy).version_source || "none",
  });

  void refreshConversation();
}

function init() {
  if (state.isInitialized || !panel || !messagesEl || !inputEl || !sendBtn) return;
  state.isInitialized = true;
  state.isBacktestingPage = Boolean(document.getElementById("bt-workspace"));

  const uiState = loadUiState();
  state.isOpen = Boolean(uiState.open);
  inputEl.value = String(uiState.draft || "");

  openBtn?.addEventListener("click", () => setOpen(!state.isOpen));
  closeBtn?.addEventListener("click", () => setOpen(false));
  backdrop?.addEventListener("click", () => setOpen(false));
  panel.addEventListener("click", handlePanelClick);
  inputEl.addEventListener("input", persistUiState);
  inputEl.addEventListener("keydown", handleKeydown);
  sendBtn.addEventListener("click", () => {
    void handleSend();
  });
  document.addEventListener("keydown", handleKeydown);

  onState("backtest.strategy", handleStrategyChange);
  onEvent(EVENTS.RESULTS_LOADED, handleResultsLoaded);

  panel.classList.toggle("is-open", state.isOpen);
  backdrop?.classList.toggle("is-open", state.isOpen);
  panel.setAttribute("aria-hidden", state.isOpen ? "false" : "true");

  if (state.isBacktestingPage) {
    const liveStrategy = String(getState("backtest.strategy") || "").trim();
    if (liveStrategy && state.latestContext.strategy !== liveStrategy) {
      saveContext(defaultContext(liveStrategy));
    }
  }

  render();
  void refreshConversation();
}

document.addEventListener("DOMContentLoaded", init);
