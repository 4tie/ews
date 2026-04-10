/**
 * ai-chat-panel.js - Result-aware AI analysis and candidate creation for the backtesting page.
 */

import api from "../../../core/api.js";
import { getState, on as onState } from "../../../core/state.js";
import { on as onEvent, EVENTS } from "../../../core/events.js";
import showToast from "../../../components/toast.js";
import { setButtonLoading } from "../../../components/loading-state.js";
import { getLatestResultsPayload } from "./results-controller.js";

const panel = document.getElementById("ai-chat-panel");
const contextEl = document.getElementById("ai-chat-context");
const transcriptEl = document.getElementById("ai-chat-transcript");
const inputEl = document.getElementById("ai-chat-input");
const askBtn = document.getElementById("btn-ai-ask");
const candidateBtn = document.getElementById("btn-ai-generate-candidate");
const hintEl = document.getElementById("ai-chat-hint");

const MAX_HISTORY_ITEMS = 6;

let latestPayload = null;
let currentVersion = null;
let currentVersionSource = "none";
let versionLookupToken = 0;
let conversationStrategy = "";
let busy = false;
let messageSeq = 0;
const messages = [];

function isObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function hasKeys(value) {
  return isObject(value) && Object.keys(value).length > 0;
}

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function compactText(value, max = 700) {
  const text = String(value || "").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max)}...`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function currentPayload() {
  const strategy = getState("backtest.strategy") || "";
  if (!latestPayload) return null;
  if (strategy && latestPayload?.strategy && latestPayload.strategy !== strategy) {
    return null;
  }
  return latestPayload;
}

function resolveStrategy() {
  return getState("backtest.strategy") || currentPayload()?.strategy || "";
}

function labelize(value) {
  return String(value || "unknown").replace(/_/g, " ");
}

function pushMessage(role, message) {
  messages.push({
    id: `ai-chat-msg-${++messageSeq}`,
    role,
    title: message?.title || (role === "user" ? "You" : role === "assistant" ? "AI" : "Panel"),
    text: message?.text || "",
    meta: message?.meta || "",
    note: message?.note || "",
    recommendations: safeArray(message?.recommendations),
    parameters: hasKeys(message?.parameters) ? message.parameters : null,
    code: typeof message?.code === "string" && message.code.trim() ? message.code.trim() : null,
    versionId: message?.versionId || null,
  });
  renderMessages();
}

function resetConversation() {
  messages.length = 0;
  pushMessage("system", {
    title: "AI Panel",
    text: "Ask for analysis of the selected strategy or generate a candidate change from the latest loaded backtest. Candidate creation stages a new version only. Nothing is promoted automatically.",
  });
}

function syncConversationStrategy() {
  const strategy = resolveStrategy();
  if (strategy === conversationStrategy) return;
  conversationStrategy = strategy;
  resetConversation();
}

function renderContextItem(label, value) {
  return `
    <div class="ai-chat-context__item">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(value)}</span>
    </div>
  `;
}

function renderContext() {
  if (!contextEl && !hintEl) return;

  const strategy = resolveStrategy();
  const payload = currentPayload();
  const runId = payload?.run_id || "No latest run loaded";
  const versionId = payload?.version_id || currentVersion?.version_id || "Unavailable";
  const resultState = payload?.summary_available ? "Latest persisted run summary loaded" : "No latest persisted run summary loaded";

  let versionSourceLabel = "Version context unavailable";
  if (currentVersionSource === "run") versionSourceLabel = "Run-linked version snapshot";
  if (currentVersionSource === "active") versionSourceLabel = "Active version fallback";
  if (currentVersionSource === "loading") versionSourceLabel = "Loading version context";

  let codeState = "Code snapshot unavailable";
  if (currentVersionSource === "loading") {
    codeState = "Loading code snapshot";
  } else if (currentVersion?.code_snapshot) {
    codeState = `Code snapshot ready (${labelize(currentVersion?.status)})`;
  }

  if (!strategy) {
    if (contextEl) {
      contextEl.innerHTML = '<div class="results-context__note">Select a strategy to enable AI analysis and candidate generation.</div>';
    }
    if (hintEl) {
      hintEl.textContent = "Choose a strategy first. Candidate creation always stays versioned and unpromoted until you explicitly accept it.";
    }
    return;
  }

  if (contextEl) {
    contextEl.innerHTML = `
      <div class="ai-chat-context__grid">
        ${renderContextItem("Strategy", strategy)}
        ${renderContextItem("Run Context", runId)}
        ${renderContextItem("Version", versionId)}
        ${renderContextItem("Version Source", versionSourceLabel)}
        ${renderContextItem("Code Context", codeState)}
        ${renderContextItem("Result Context", resultState)}
      </div>
    `;
  }

  if (hintEl) {
    hintEl.textContent = payload?.summary_available
      ? "Questions and candidates are grounded in the latest loaded run. Candidate creation stages a new version only; it does not promote changes."
      : currentVersion?.code_snapshot
        ? "No latest run summary is loaded, so AI will rely mainly on the resolved strategy snapshot. Candidate creation still stays versioned."
        : "Load a run or ensure the strategy has a saved version snapshot for stronger AI context.";
  }
}