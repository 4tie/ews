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
}function summarizeHistoryEntry(message) {
  if (message.parameters) {
    return `Structured parameter suggestion: ${compactText(JSON.stringify(message.parameters))}`;
  }
  if (message.code) {
    return "Structured code candidate returned for the current strategy.";
  }
  return compactText(message.text || "");
}

function buildConversationPrompt(prompt, mode) {
  const history = messages
    .filter((message) => message.role !== "system")
    .slice(-MAX_HISTORY_ITEMS)
    .map((message) => `${message.role === "user" ? "User" : "Assistant"}: ${summarizeHistoryEntry(message)}`)
    .join("\n\n");

  const contextLines = [];
  const payload = currentPayload();
  if (payload?.run_id) contextLines.push(`Latest run id: ${payload.run_id}`);
  if (payload?.version_id) contextLines.push(`Run-linked version id: ${payload.version_id}`);
  if (!payload?.version_id && currentVersion?.version_id) {
    contextLines.push(`Resolved version snapshot: ${currentVersion.version_id} (${currentVersionSource})`);
  }

  const promptParts = [];
  if (history) promptParts.push(`Conversation so far:\n${history}`);
  if (contextLines.length) promptParts.push(`Current UI context:\n${contextLines.join("\n")}`);
  promptParts.push(`Latest user request:\n${prompt.trim()}`);
  promptParts.push(
    mode === "candidate"
      ? "Return a concrete candidate change grounded in the current strategy and latest result. Prefer parameter-only changes when possible."
      : "Stay grounded in the current strategy and latest result context. Be specific and actionable."
  );

  return promptParts.join("\n\n");
}

function buildAiBacktestResults() {
  const payload = currentPayload();
  const summaryMetrics = isObject(payload?.summary_metrics) ? payload.summary_metrics : {};
  const diagnosis = isObject(payload?.diagnosis) ? payload.diagnosis : {};

  return {
    total_profit: summaryMetrics.profit_total_abs ?? summaryMetrics.absolute_profit ?? null,
    profit_ratio: summaryMetrics.profit_total_pct ?? summaryMetrics.total_profit_pct ?? null,
    win_rate: summaryMetrics.win_rate ?? summaryMetrics.winrate ?? null,
    max_drawdown: summaryMetrics.max_drawdown ?? summaryMetrics.max_drawdown_account ?? summaryMetrics.drawdown ?? null,
    profit_factor: summaryMetrics.profit_factor ?? null,
    sharpe: summaryMetrics.sharpe ?? null,
    sortino: summaryMetrics.sortino ?? null,
    total_trades: summaryMetrics.total_trades ?? null,
    avg_trade: summaryMetrics.avg_profit_pct ?? summaryMetrics.avg_trade ?? null,
    calmar: summaryMetrics.calmar ?? null,
    run_id: payload?.run_id ?? null,
    version_id: payload?.version_id ?? null,
    diagnosis_status: payload?.diagnosis_status ?? null,
    primary_flags: safeArray(diagnosis?.primary_flags)
      .map((flag) => flag?.message || flag?.rule)
      .filter(Boolean)
      .slice(0, 4),
    parameter_hints: safeArray(diagnosis?.parameter_hints).slice(0, 4),
    top_pairs: safeArray(payload?.results_per_pair)
      .filter((row) => row?.key && row.key !== "TOTAL")
      .slice(0, 4)
      .map((row) => ({
        pair: row.key,
        profit_pct: row.profit_total_pct ?? null,
        trades: row.trades ?? null,
      })),
  };
}

function renderRecommendations(message) {
  const items = safeArray(message?.recommendations).filter(Boolean);
  if (!items.length) return "";
  return `<ul class="ai-chat-message__list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderActions(message) {
  if (message?.versionId) return "";

  const actions = [];
  const disabled = busy ? " disabled" : "";

  if (message?.parameters) {
    actions.push(
      `<button type="button" class="btn btn--secondary btn--sm" data-action="apply-parameters" data-message-id="${escapeHtml(message.id)}"${disabled}>Create Parameter Candidate</button>`
    );
  }

  if (message?.code) {
    actions.push(
      `<button type="button" class="btn btn--secondary btn--sm" data-action="apply-code" data-message-id="${escapeHtml(message.id)}"${disabled}>Create Code Candidate</button>`
    );
  }

  return actions.length ? `<div class="ai-chat-message__actions">${actions.join("")}</div>` : "";
}

function renderMessages() {
  if (!transcriptEl) return;

  if (!messages.length) {
    transcriptEl.innerHTML = '<div class="info-empty">Ask AI about the selected strategy and latest loaded result.</div>';
    return;
  }

  transcriptEl.innerHTML = messages.map((message) => {
    const body = message?.text ? `<div class="ai-chat-message__body">${escapeHtml(message.text)}</div>` : "";
    const recommendations = renderRecommendations(message);
    const parameters = message?.parameters
      ? `<pre class="ai-chat-message__payload">${escapeHtml(JSON.stringify(message.parameters, null, 2))}</pre>`
      : "";
    const code = message?.code
      ? `<pre class="ai-chat-message__payload ai-chat-message__payload--code">${escapeHtml(message.code)}</pre>`
      : "";
    const note = message?.note ? `<div class="ai-chat-message__note">${escapeHtml(message.note)}</div>` : "";
    const versionNote = message?.versionId
      ? `<div class="ai-chat-message__note">Candidate version ${escapeHtml(message.versionId)} created. It remains pending until you explicitly accept it.</div>`
      : "";

    return `
      <article class="ai-chat-message ai-chat-message--${escapeHtml(message.role)}">
        <div class="ai-chat-message__header">
          <span class="ai-chat-message__role">${escapeHtml(message.title)}</span>
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
  }).join("");

  requestAnimationFrame(() => {
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
  });
}

async function refreshVersionContext() {
  const strategy = resolveStrategy();
  const payload = currentPayload();
  const versionId = payload?.version_id || null;
  const lookupToken = ++versionLookupToken;

  currentVersion = null;
  currentVersionSource = strategy ? "loading" : "none";
  renderContext();

  if (!strategy) {
    currentVersionSource = "none";
    renderContext();
    return;
  }

  let version = null;
  let source = "none";

  if (versionId) {
    try {
      version = await api.versions.getVersion(strategy, versionId);
      source = "run";
    } catch (error) {
      console.debug("[backtesting] AI chat panel could not load run-linked version:", error);
    }
  }

  if (!version) {
    try {
      version = await api.versions.getActive(strategy);
      source = "active";
    } catch (error) {
      console.debug("[backtesting] AI chat panel could not load active version:", error);
    }
  }

  if (lookupToken !== versionLookupToken) return;

  currentVersion = version;
  currentVersionSource = version ? source : "none";
  renderContext();
}

async function requestAnalysis(prompt) {
  const strategy = resolveStrategy();
  const strategyCode = currentVersion?.code_snapshot || undefined;
  const backtestResults = buildAiBacktestResults();

  if (strategyCode) {
    return api.aiEvolution.analyzeStrategy({
      strategy_name: strategy,
      strategy_code: strategyCode,
      backtest_results: backtestResults,
      user_question: prompt,
    });
  }

  return api.aiEvolution.analyzeMetrics({
    metrics: backtestResults,
    context: prompt,
  });
}

async function requestCandidate(prompt) {
  return api.aiChat.chat({
    message: prompt,
    strategy_name: resolveStrategy(),
    strategy_code: currentVersion?.code_snapshot || undefined,
    backtest_results: buildAiBacktestResults(),
    max_iterations: 4,
    temperature: 0.25,
  });
}