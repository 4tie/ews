import api from "../core/api.js";
import { getState, on as onState } from "../core/state.js";
import { emit, on as onEvent, EVENTS } from "../core/events.js";
import persistence, { KEYS } from "../core/persistence.js";
import showToast from "./toast.js";
import { setButtonLoading } from "./loading-state.js";

const panel = document.getElementById("ai-chat-panel");
const backdrop = document.getElementById("ai-chat-backdrop");
const openBtn = document.getElementById("btn-open-ai-chat");
const closeBtn = document.getElementById("close-chat");
const messagesEl = document.getElementById("chat-messages");
const inputEl = document.getElementById("chat-input");
const sendBtn = document.getElementById("btn-send-chat");

const POLL_INTERVAL_MS = 1200;
const MAX_LIVE_EVENTS = 24;

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

function mergedMessages() {
  const strategy = resolveStrategy();
  const overlays = isObject(state.overlays?.[strategy]) ? state.overlays[strategy] : {};
  return safeArray(state.thread?.messages).map((message) => {
    const overlay = isObject(overlays?.[message?.id]) ? overlays[message.id] : {};
    return {
      ...message,
      candidate_version_id: overlay.candidate_version_id || message?.candidate_version_id || null,
      candidate_note: overlay.note || "",
    };
  });
}

function rememberCandidateOverlay(strategy, messageId, payload) {
  if (!strategy || !messageId) return;
  if (!isObject(state.overlays[strategy])) {
    state.overlays[strategy] = {};
  }
  state.overlays[strategy][messageId] = {
    candidate_version_id: payload?.candidate_version_id || null,
    note: payload?.note || "",
  };
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

function renderActions(message) {
  if (message?.candidate_version_id) return "";
  const hasCandidatePayload = Boolean(hasKeys(message?.parameters) || (typeof message?.code === "string" && message.code.trim()));
  if (!hasCandidatePayload) return "";

  const disabled = state.requestInFlight || !currentRunReady() ? " disabled" : "";
  const actions = [];
  if (hasKeys(message?.parameters)) {
    actions.push(`<button type="button" class="btn btn--secondary btn--sm" data-action="apply-parameters" data-message-id="${escapeHtml(message.id)}"${disabled}>Create Parameter Candidate</button>`);
  }
  if (typeof message?.code === "string" && message.code.trim()) {
    actions.push(`<button type="button" class="btn btn--secondary btn--sm" data-action="apply-code" data-message-id="${escapeHtml(message.id)}"${disabled}>Create Code Candidate</button>`);
  }

  const note = !currentRunReady()
    ? '<div class="ai-chat-message__note">Load a completed run diagnosis first. AI candidates still stage through the existing run-scoped version workflow.</div>'
    : "";
  return `${actions.length ? `<div class="ai-chat-message__actions">${actions.join("")}</div>` : ""}${note}`;
}

function renderStatusMessage() {
  const strategy = resolveStrategy();
  if (!strategy) {
    return `
      <article class="ai-chat-message ai-chat-message--system ai-chat-message--status">
        <div class="ai-chat-message__header">
          <span class="ai-chat-message__role">AI Panel</span>
        </div>
        <div class="ai-chat-message__body">Select a strategy in Backtesting to enable the assistant.</div>
      </article>
    `;
  }

  if (!canUseAssistant(strategy)) {
    return `
      <article class="ai-chat-message ai-chat-message--system ai-chat-message--status">
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
  const parameters = hasKeys(message?.parameters)
    ? `<pre class="ai-chat-message__payload">${escapeHtml(JSON.stringify(message.parameters, null, 2))}</pre>`
    : "";
  const code = typeof message?.code === "string" && message.code.trim()
    ? `<pre class="ai-chat-message__payload ai-chat-message__payload--code">${escapeHtml(message.code)}</pre>`
    : "";
  const noteText = message?.candidate_note || message?.note || "";
  const note = noteText ? `<div class="ai-chat-message__note">${escapeHtml(noteText)}</div>` : "";
  const versionNote = message?.candidate_version_id
    ? `<div class="ai-chat-message__note">Candidate version ${escapeHtml(message.candidate_version_id)} created. It remains pending until you explicitly accept it.</div>`
    : "";

  return `
    <article class="ai-chat-message ai-chat-message--${escapeHtml(message.role || "system")}">
      <div class="ai-chat-message__header">
        <span class="ai-chat-message__role">${escapeHtml(message.title || (message.role === "user" ? "You" : message.role === "assistant" ? "AI" : "Panel"))}</span>
        ${message?.meta ? `<span class="ai-chat-message__meta">${escapeHtml(message.meta)}</span>` : ""}
      </div>
      ${body}
      ${recommendations}
      ${parameters}
      ${code}
      ${renderActions(message)}
      ${note}
      ${versionNote}
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
    parts.push('<div class="chat-panel__empty">No conversation yet. Ask the assistant to analyze the grounded strategy context or generate a candidate.</div>');
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

async function handleSend() {
  if (state.requestInFlight) return;

  const prompt = String(inputEl?.value || "").trim();
  if (!prompt) {
    showToast("Enter a prompt first.", "warning");
    return;
  }

  const strategy = resolveStrategy();
  if (!strategy) {
    showToast("Select a strategy first.", "warning");
    return;
  }

  if (!canUseAssistant(strategy)) {
    showToast("Load a persisted run from Backtesting first.", "warning");
    return;
  }

  state.requestInFlight = true;
  updateComposerState();
  render();

  try {
    const response = await api.aiChat.createThreadMessage(strategy, {
      message: prompt,
      context: buildRequestContext(strategy),
    });

    if (inputEl) {
      inputEl.value = "";
    }
    persistUiState();
    await loadThread(strategy);
    if (response?.job_id) {
      startJobTracking(response.job_id);
    }
    showToast("AI request queued.", "success", 2000);
  } catch (error) {
    state.requestInFlight = false;
    updateComposerState();
    render();
    showToast(`AI request failed: ${error?.message || String(error)}`, "error");
  }
}

async function handleApplyAction(messageId, action) {
  if (state.requestInFlight) return;

  const strategy = resolveStrategy();
  const context = currentContext(strategy);
  const message = mergedMessages().find((entry) => entry.id === messageId);
  if (!message || !strategy || !context.run_id) {
    showToast("A completed run context is required before staging a candidate.", "warning");
    return;
  }
  if (!currentRunReady()) {
    showToast("Load a completed run diagnosis before staging a candidate.", "warning");
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
      parameters: action === "apply-parameters" ? message.parameters : null,
      code: action === "apply-code" ? message.code : null,
      summary: compactText(message.text || "AI chat candidate", 220),
    });

    rememberCandidateOverlay(strategy, messageId, {
      candidate_version_id: response?.candidate_version_id || null,
      note: response?.message || "Candidate version created.",
    });

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
  if (actionButton) {
    void handleApplyAction(actionButton.dataset.messageId || "", actionButton.dataset.action || "");
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
