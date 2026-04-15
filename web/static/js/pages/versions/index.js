import api from "../../core/api.js";
import { isValidPair, normalizePair } from "../../core/utils.js";
import showToast from "../../components/toast.js";
import { closeModal, openModal } from "../../components/modal.js";
import { renderVersionListPanel } from "./version-list-panel.js";
import { renderVersionDetailsPanel } from "./version-details-panel.js";


const STRATEGY_STORAGE_KEY = "4tie::versions:selectedStrategy";
const RUN_POLL_INTERVAL_MS = 2500;

const state = {
  strategies: [],
  timeframes: [],
  exchanges: [],
  selectedStrategy: "",
  includeArchived: true,
  versions: [],
  activeVersionId: "",
  selectedVersionId: "",
  selectedCompareVersionId: "",
  selectedTab: "overview",
  versionDetail: null,
  listStatus: "idle",
  listError: "",
  detailStatus: "idle",
  detailError: "",
  pendingAction: "",
  listRequestId: 0,
  detailRequestId: 0,
  runPollTimer: null,
  pendingRunId: "",
};

const elements = {
  strategySelect: document.getElementById("versions-strategy-select"),
  includeArchived: document.getElementById("versions-include-archived"),
  refreshButton: document.getElementById("versions-refresh-button"),
  summaryCards: document.getElementById("versions-summary-cards"),
  listContainer: document.getElementById("version-list"),
  countEl: document.getElementById("version-count"),
  detailsContainer: document.getElementById("version-details-panel"),
};

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

function formatDate(value) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
}

function formatPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${number.toFixed(2)}%`;
}

function shortVersionId(versionId) {
  const raw = String(versionId || "");
  if (!raw) return "-";
  return raw.length > 18 ? `${raw.slice(0, 18)}...` : raw;
}

function formatPairs(value) {
  return Array.isArray(value) ? value.join("\n") : "";
}

function sortVersions(versions) {
  return (Array.isArray(versions) ? versions : [])
    .slice()
    .sort((left, right) => String(right?.created_at || "").localeCompare(String(left?.created_at || "")));
}

function readSavedStrategy() {
  try {
    return String(localStorage.getItem(STRATEGY_STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
}

function saveSelectedStrategy(strategy) {
  try {
    localStorage.setItem(STRATEGY_STORAGE_KEY, String(strategy || ""));
  } catch {
    // Ignore storage failures.
  }
}

function urlStrategy() {
  const url = new URL(window.location.href);
  return String(url.searchParams.get("strategy") || "").trim();
}

function urlVersionId() {
  const url = new URL(window.location.href);
  return String(url.searchParams.get("version_id") || "").trim();
}

function syncUrlState() {
  const url = new URL(window.location.href);
  if (state.selectedStrategy) {
    url.searchParams.set("strategy", state.selectedStrategy);
  } else {
    url.searchParams.delete("strategy");
  }

  if (state.selectedVersionId) {
    url.searchParams.set("version_id", state.selectedVersionId);
  } else {
    url.searchParams.delete("version_id");
  }

  window.history.replaceState({}, "", url);
}

function stopRunPolling() {
  if (state.runPollTimer) {
    window.clearTimeout(state.runPollTimer);
    state.runPollTimer = null;
  }
  state.pendingRunId = "";
}

async function pollRunStatus(runId) {
  if (!runId) return;

  try {
    const response = await api.backtest.getRun(runId);
    const run = response?.run;
    if (!run) {
      stopRunPolling();
      return;
    }

    await loadVersions({ preserveSelection: true, silent: true });

    if (!["queued", "running"].includes(String(run?.status || ""))) {
      stopRunPolling();
      showToast(`Run ${runId} is now ${labelize(run?.status || "completed")}.`, "info");
      return;
    }
  } catch (error) {
    console.warn("[versions] Failed to poll run status:", error);
  }

  state.runPollTimer = window.setTimeout(() => {
    void pollRunStatus(runId);
  }, RUN_POLL_INTERVAL_MS);
}

function startRunPolling(runId) {
  stopRunPolling();
  state.pendingRunId = String(runId || "");
  if (!state.pendingRunId) return;
  state.runPollTimer = window.setTimeout(() => {
    void pollRunStatus(state.pendingRunId);
  }, RUN_POLL_INTERVAL_MS);
}

function renderStrategyOptions() {
  if (!elements.strategySelect) return;

  const current = state.selectedStrategy;
  const options = state.strategies.length
    ? state.strategies
    : [""];

  elements.strategySelect.innerHTML = options
    .map((strategy) => {
      const label = strategy || "No strategies found";
      return `<option value="${escapeHtml(strategy)}"${strategy === current ? " selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");

  elements.strategySelect.disabled = !state.strategies.length || state.listStatus === "loading";
}

function renderSummaryCards() {
  if (!elements.summaryCards) return;

  if (!state.selectedStrategy) {
    elements.summaryCards.innerHTML = `
      <div class="versions-summary-card versions-summary-card--empty">
        <strong>No strategy selected.</strong>
        <span>Choose a strategy to inspect its version lifecycle.</span>
      </div>
    `;
    return;
  }

  const versions = Array.isArray(state.versions) ? state.versions : [];
  const candidates = versions.filter((version) => String(version?.status || "") === "candidate").length;
  const archived = versions.filter((version) => String(version?.status || "") === "archived").length;
  const activeVersion = versions.find((version) => version?.version_id === state.activeVersionId) || null;
  const selectedVersion = versions.find((version) => version?.version_id === state.selectedVersionId) || null;
  const selectedProfit = state.versionDetail?.metrics?.profit_total_pct;

  elements.summaryCards.innerHTML = `
    <div class="versions-summary-card versions-summary-card--primary">
      <span class="versions-summary-card__label">Strategy</span>
      <strong class="versions-summary-card__value">${escapeHtml(state.selectedStrategy)}</strong>
      <span class="versions-summary-card__meta">${escapeHtml(`${versions.length} saved | ${candidates} pending decision`)}</span>
    </div>
    <div class="versions-summary-card">
      <span class="versions-summary-card__label">Live Version</span>
      <strong class="versions-summary-card__value">${escapeHtml(shortVersionId(state.activeVersionId || "-"))}</strong>
      <span class="versions-summary-card__meta">${escapeHtml(activeVersion?.summary || activeVersion?.source_context?.title || "No active version recorded.")}</span>
    </div>
    <div class="versions-summary-card">
      <span class="versions-summary-card__label">Decision Queue</span>
      <strong class="versions-summary-card__value">${escapeHtml(String(candidates))}</strong>
      <span class="versions-summary-card__meta">${escapeHtml(state.includeArchived ? `${archived} archived visible` : "Archived hidden")}</span>
    </div>
    <div class="versions-summary-card versions-summary-card--selection">
      <span class="versions-summary-card__label">Selected Workspace</span>
      <strong class="versions-summary-card__value">${escapeHtml(shortVersionId(selectedVersion?.version_id || "-"))}</strong>
      <span class="versions-summary-card__meta">${escapeHtml(selectedVersion ? `${labelize(selectedVersion?.status || "draft")} | ${selectedProfit != null ? formatPct(selectedProfit) : formatPct(selectedVersion?.backtest_profit_pct)}` : "Pick a version to inspect diffs, lineage, and decisions.")}</span>
    </div>
  `;
}

function renderPage() {
  renderStrategyOptions();
  renderSummaryCards();

  if (elements.includeArchived) {
    elements.includeArchived.checked = state.includeArchived;
    elements.includeArchived.disabled = !state.selectedStrategy || state.listStatus === "loading";
  }

  if (elements.refreshButton) {
    elements.refreshButton.disabled = !state.selectedStrategy || state.listStatus === "loading" || Boolean(state.pendingAction);
    elements.refreshButton.textContent = state.listStatus === "loading" ? "Refreshing..." : "Refresh";
  }

  renderVersionListPanel({
    container: elements.listContainer,
    countEl: elements.countEl,
    versions: state.versions,
    selectedVersionId: state.selectedVersionId,
    activeVersionId: state.activeVersionId,
    loading: state.listStatus === "loading" && !state.versions.length,
    error: state.listError,
    onSelect: handleSelectVersion,
  });

  renderVersionDetailsPanel({
    container: elements.detailsContainer,
    versionDetail: state.versionDetail,
    versions: state.versions,
    selectedVersionId: state.selectedVersionId,
    activeVersionId: state.activeVersionId,
    activeTab: state.selectedTab,
    loading: state.detailStatus === "loading" && !state.versionDetail,
    error: state.detailError,
    pendingAction: state.pendingAction,
    onAction: handleVersionAction,
    onCompareTargetChange: handleCompareTargetChange,
    onTabChange: handleTabChange,
  });
}

function pickSelectedStrategy(strategies) {
  const preferred = [urlStrategy(), readSavedStrategy(), state.selectedStrategy].find(Boolean);
  if (preferred && strategies.includes(preferred)) {
    return preferred;
  }
  return strategies[0] || "";
}

function pickSelectedVersionId(versions, activeVersionId) {
  const existing = state.selectedVersionId;
  if (existing && versions.some((version) => version?.version_id === existing)) {
    return existing;
  }

  const fromUrl = urlVersionId();
  if (fromUrl && versions.some((version) => version?.version_id === fromUrl)) {
    return fromUrl;
  }

  if (activeVersionId && versions.some((version) => version?.version_id === activeVersionId)) {
    return activeVersionId;
  }

  return versions[0]?.version_id || "";
}

async function loadOptions() {
  try {
    const response = await api.backtest.options();
    state.strategies = Array.isArray(response?.strategies) ? response.strategies : [];
    state.timeframes = Array.isArray(response?.timeframes) ? response.timeframes : [];
    state.exchanges = Array.isArray(response?.exchanges) ? response.exchanges : [];
    state.selectedStrategy = pickSelectedStrategy(state.strategies);
    saveSelectedStrategy(state.selectedStrategy);
    syncUrlState();
    renderPage();
  } catch (error) {
    showToast(`Failed to load strategy options: ${error?.message || String(error)}`, "error");
  }
}

async function loadVersions({ preserveSelection = true, silent = false } = {}) {
  const strategy = state.selectedStrategy;
  const requestId = ++state.listRequestId;

  if (!strategy) {
    state.versions = [];
    state.activeVersionId = "";
    state.selectedVersionId = "";
    state.selectedCompareVersionId = "";
    state.selectedTab = "overview";
    state.versionDetail = null;
    state.listStatus = "idle";
    state.listError = "";
    state.detailStatus = "idle";
    state.detailError = "";
    renderPage();
    return;
  }

  if (!silent) {
    state.listStatus = "loading";
    state.listError = "";
    renderPage();
  }

  try {
    const response = await api.versions.listVersions(strategy, state.includeArchived);
    if (requestId !== state.listRequestId) return;

    state.versions = sortVersions(response?.versions || []);
    state.activeVersionId = String(response?.active_version_id || "");
    state.listStatus = "ready";
    state.listError = "";
    state.selectedVersionId = preserveSelection
      ? pickSelectedVersionId(state.versions, state.activeVersionId)
      : pickSelectedVersionId(state.versions, state.activeVersionId);
    if (!state.versions.some((entry) => entry?.version_id === state.selectedCompareVersionId && entry?.version_id !== state.selectedVersionId)) {
      state.selectedCompareVersionId = "";
    }
    syncUrlState();
    renderPage();

    if (state.selectedVersionId) {
      await loadVersionDetail({ compareToVersionId: state.selectedCompareVersionId || null, silent });
    } else {
      state.versionDetail = null;
      state.detailStatus = "idle";
      state.detailError = "";
      renderPage();
    }
  } catch (error) {
    if (requestId !== state.listRequestId) return;
    state.listStatus = "error";
    state.listError = error?.message || String(error);
    state.versions = [];
    state.activeVersionId = "";
    state.selectedVersionId = "";
    state.versionDetail = null;
    state.detailStatus = "idle";
    state.detailError = "";
    renderPage();
  }
}

async function loadVersionDetail({ compareToVersionId = null, silent = false } = {}) {
  const strategy = state.selectedStrategy;
  const versionId = state.selectedVersionId;
  const requestId = ++state.detailRequestId;

  if (!strategy || !versionId) {
    state.versionDetail = null;
    state.detailStatus = "idle";
    state.detailError = "";
    renderPage();
    return;
  }

  if (!silent) {
    state.detailStatus = "loading";
    state.detailError = "";
    renderPage();
  }

  try {
    const detail = await api.versions.getVersionDetail(strategy, versionId, {
      compareToVersionId,
    });
    if (requestId !== state.detailRequestId) return;

    state.versionDetail = detail || null;
    state.selectedCompareVersionId = String(detail?.compare_version_id || compareToVersionId || "");
    state.detailStatus = "ready";
    state.detailError = "";
    syncUrlState();
    renderPage();
  } catch (error) {
    if (requestId !== state.detailRequestId) return;
    state.versionDetail = null;
    state.detailStatus = "error";
    state.detailError = error?.message || String(error);
    renderPage();
  }
}


function buildModalContext(fields = [], note = "") {
  return `
    <div class="versions-modal__context">
      ${fields.length ? `<div class="versions-modal__grid">${fields.map(([label, value]) => `
        <span><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</span>
      `).join("")}</div>` : ""}
      ${note ? `<div class="versions-modal__note">${escapeHtml(note)}</div>` : ""}
    </div>
  `;
}

function openNoteModal({ title, confirmLabel, noteLabel, placeholder, fields = [], note = "" }) {
  return new Promise((resolve) => {
    let settled = false;
    const body = `
      <form id="versions-note-form" class="versions-modal">
        ${buildModalContext(fields, note)}
        <label class="setup-field">
          <span class="form-label">${escapeHtml(noteLabel)}</span>
          <textarea id="versions-note-input" class="form-input versions-modal__textarea" rows="5" placeholder="${escapeHtml(placeholder)}"></textarea>
        </label>
      </form>
    `;
    const footer = `
      <button type="button" class="btn btn--ghost btn--sm" id="versions-note-cancel">Cancel</button>
      <button type="button" class="btn btn--secondary btn--sm" id="versions-note-confirm">${escapeHtml(confirmLabel)}</button>
    `;

    const settle = (value) => {
      if (settled) return;
      settled = true;
      closeModal();
      resolve(value);
    };

    openModal({
      title,
      body,
      footer,
      onClose: () => {
        if (!settled) {
          settled = true;
          resolve(null);
        }
      },
    });

    const input = document.getElementById("versions-note-input");
    document.getElementById("versions-note-cancel")?.addEventListener("click", () => settle(null));
    document.getElementById("versions-note-confirm")?.addEventListener("click", () => settle(String(input?.value || "").trim()));
    document.getElementById("versions-note-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      settle(String(input?.value || "").trim());
    });
  });
}

function resolveRunDefaults() {
  const detail = state.versionDetail || {};
  const snapshots = [
    detail?.latest_run?.request_snapshot,
    detail?.run_comparison?.right?.request_snapshot,
    detail?.run_comparison?.left?.request_snapshot,
  ];
  const snapshot = snapshots.find((entry) => entry && typeof entry === "object") || {};

  return {
    timeframe: String(snapshot?.timeframe || state.timeframes[0] || "").trim(),
    timerange: String(snapshot?.timerange || "").trim(),
    pairs: formatPairs(snapshot?.pairs || []),
    exchange: String(snapshot?.exchange || state.exchanges[0] || "binance").trim(),
    maxOpenTrades: snapshot?.max_open_trades ?? "",
    dryRunWallet: snapshot?.dry_run_wallet ?? "",
    configPath: String(snapshot?.config_path || "").trim(),
    extraFlags: Array.isArray(snapshot?.extra_flags) ? snapshot.extra_flags.join("\n") : "",
  };
}

function openRunBacktestModal() {
  const defaults = resolveRunDefaults();

  return new Promise((resolve) => {
    let settled = false;
    const body = `
      <form id="versions-run-form" class="versions-modal">
        ${buildModalContext(
          [
            ["Strategy", state.selectedStrategy],
            ["Version", state.selectedVersionId],
          ],
          "The run is pinned to this exact version_id. Fields are prefilled from the latest linked run when available."
        )}
        <label class="setup-field">
          <span class="form-label">Timeframe</span>
          <select id="versions-run-timeframe" class="form-select" required>
            ${state.timeframes.map((timeframe) => `
              <option value="${escapeHtml(timeframe)}"${timeframe === defaults.timeframe ? " selected" : ""}>${escapeHtml(timeframe)}</option>
            `).join("")}
          </select>
        </label>
        <label class="setup-field">
          <span class="form-label">Timerange</span>
          <input id="versions-run-timerange" class="form-input" type="text" placeholder="20240101-20240201" value="${escapeHtml(defaults.timerange)}" />
        </label>
        <label class="setup-field">
          <span class="form-label">Pairs</span>
          <textarea id="versions-run-pairs" class="form-input versions-modal__textarea" rows="5" placeholder="BTC/USDT&#10;ETH/USDT" required>${escapeHtml(defaults.pairs)}</textarea>
        </label>
        <label class="setup-field">
          <span class="form-label">Exchange</span>
          <select id="versions-run-exchange" class="form-select">
            ${state.exchanges.map((exchange) => `
              <option value="${escapeHtml(exchange)}"${exchange === defaults.exchange ? " selected" : ""}>${escapeHtml(exchange)}</option>
            `).join("")}
          </select>
        </label>
        <div class="versions-modal__split">
          <label class="setup-field">
            <span class="form-label">Max Open Trades</span>
            <input id="versions-run-max-trades" class="form-input" type="number" step="1" value="${escapeHtml(String(defaults.maxOpenTrades ?? ""))}" />
          </label>
          <label class="setup-field">
            <span class="form-label">Dry Run Wallet</span>
            <input id="versions-run-wallet" class="form-input" type="number" step="0.01" min="0" value="${escapeHtml(String(defaults.dryRunWallet ?? ""))}" />
          </label>
        </div>
        <label class="setup-field">
          <span class="form-label">Config Path</span>
          <input id="versions-run-config-path" class="form-input" type="text" value="${escapeHtml(defaults.configPath)}" />
        </label>
        <label class="setup-field">
          <span class="form-label">Extra Flags</span>
          <textarea id="versions-run-extra-flags" class="form-input versions-modal__textarea" rows="4" placeholder="One flag per line">${escapeHtml(defaults.extraFlags)}</textarea>
        </label>
      </form>
    `;
    const footer = `
      <button type="button" class="btn btn--ghost btn--sm" id="versions-run-cancel">Cancel</button>
      <button type="button" class="btn btn--secondary btn--sm" id="versions-run-confirm">Start Backtest</button>
    `;

    const settle = (value) => {
      if (settled) return;
      settled = true;
      closeModal();
      resolve(value);
    };

    const readPayload = () => {
      const pairs = String(document.getElementById("versions-run-pairs")?.value || "")
        .split(/[\n,]/)
        .map((pair) => normalizePair(pair))
        .filter(Boolean);

      if (!pairs.length) {
        showToast("Add at least one valid pair.", "warning");
        return null;
      }

      const invalidPair = pairs.find((pair) => !isValidPair(pair));
      if (invalidPair) {
        showToast(`Invalid pair: ${invalidPair}`, "warning");
        return null;
      }

      const timeframe = String(document.getElementById("versions-run-timeframe")?.value || "").trim();
      if (!timeframe) {
        showToast("Select a timeframe.", "warning");
        return null;
      }

      const maxOpenTradesRaw = String(document.getElementById("versions-run-max-trades")?.value || "").trim();
      const walletRaw = String(document.getElementById("versions-run-wallet")?.value || "").trim();
      const extraFlags = String(document.getElementById("versions-run-extra-flags")?.value || "")
        .split(/\r?\n/)
        .map((flag) => flag.trim())
        .filter(Boolean);

      return {
        strategy: state.selectedStrategy,
        timeframe,
        timerange: String(document.getElementById("versions-run-timerange")?.value || "").trim() || undefined,
        pairs,
        exchange: String(document.getElementById("versions-run-exchange")?.value || "binance").trim() || "binance",
        max_open_trades: maxOpenTradesRaw === "" ? undefined : Number(maxOpenTradesRaw),
        dry_run_wallet: walletRaw === "" ? undefined : Number(walletRaw),
        config_path: String(document.getElementById("versions-run-config-path")?.value || "").trim() || undefined,
        extra_flags: extraFlags,
        version_id: state.selectedVersionId,
        trigger_source: "manual",
      };
    };

    openModal({
      title: "Run Backtest For Version",
      body,
      footer,
      onClose: () => {
        if (!settled) {
          settled = true;
          resolve(null);
        }
      },
    });

    document.getElementById("versions-run-cancel")?.addEventListener("click", () => settle(null));
    document.getElementById("versions-run-confirm")?.addEventListener("click", () => {
      const payload = readPayload();
      if (!payload) return;
      settle(payload);
    });
    document.getElementById("versions-run-form")?.addEventListener("submit", (event) => {
      event.preventDefault();
      const payload = readPayload();
      if (!payload) return;
      settle(payload);
    });
  });
}

async function runVersionAction(action, executor) {
  if (state.pendingAction) return;
  state.pendingAction = action;
  renderPage();

  try {
    await executor();
  } finally {
    state.pendingAction = "";
    renderPage();
  }
}

async function handleAccept() {
  const versionId = state.selectedVersionId;
  const note = await openNoteModal({
    title: "Accept Version",
    confirmLabel: "Accept Version",
    noteLabel: "Decision note",
    placeholder: "Why this candidate should become the live strategy.",
    fields: [
      ["Strategy", state.selectedStrategy],
      ["Candidate", versionId],
      ["Current live", state.activeVersionId || "-"],
    ],
    note: "Accept promotes the selected candidate into the current live strategy target. This is the only path that writes the live strategy files.",
  });
  if (note === null) return;

  await runVersionAction("accept", async () => {
    const response = await api.versions.accept(state.selectedStrategy, {
      version_id: versionId,
      notes: note || undefined,
    });
    showToast(response?.message || `Accepted ${versionId}.`, "success");
    await loadVersions({ preserveSelection: true, silent: false });
  });
}

async function handleReject() {
  const versionId = state.selectedVersionId;
  const note = await openNoteModal({
    title: "Reject Version",
    confirmLabel: "Reject Version",
    noteLabel: "Decision note",
    placeholder: "Why this candidate should stay out of the live strategy.",
    fields: [
      ["Strategy", state.selectedStrategy],
      ["Candidate", versionId],
    ],
    note: "Reject marks the candidate as rejected and leaves the live strategy untouched.",
  });
  if (note === null) return;

  await runVersionAction("reject", async () => {
    const response = await api.versions.reject(state.selectedStrategy, {
      version_id: versionId,
      reason: note || undefined,
    });
    showToast(response?.message || `Rejected ${versionId}.`, "success");
    await loadVersions({ preserveSelection: true, silent: false });
  });
}

async function handleRollback(targetVersionId, runContext = null) {
  const versionId = targetVersionId || state.selectedVersionId;

  // Runtime guard: check if version_id exists
  if (!versionId) {
    showToast("No linked version available for this run", "error");
    return;
  }

  // Build modal fields
  const fields = [
    ["Strategy", state.selectedStrategy],
    ["Rollback target", versionId],
    ["Current live", state.activeVersionId || "-"],
  ];

  // Add run context fields if provided (optional - only if they exist)
  if (runContext) {
    if (runContext.runId) {
      fields.push(["Run", runContext.runId]);
    }
    if (runContext.completedAt) {
      fields.push(["Completed", formatDate(runContext.completedAt)]);
    }
    if (runContext.profit) {
      fields.push(["Profit", runContext.profit]);
    }
  }

  const note = await openNoteModal({
    title: runContext?.runId ? `Rollback to version linked to run ${runContext.runId}?` : "Rollback To Version",
    confirmLabel: "Rollback",
    noteLabel: "Decision note",
    placeholder: "Why the live strategy should return to this version.",
    fields,
    note: "Rollback restores the selected historical version as the live target and archives the currently active version.",
  });
  if (note === null) return;

  await runVersionAction("rollback", async () => {
    const response = await api.versions.rollback(state.selectedStrategy, {
      target_version_id: versionId,
      reason: note || undefined,
    });
    showToast(response?.message || `Rolled back to ${versionId}.`, "success");
    await loadVersions({ preserveSelection: true, silent: false });
  });
}

async function handleRunBacktest() {
  const payload = await openRunBacktestModal();
  if (payload === null) return;

  await runVersionAction("run", async () => {
    const response = await api.backtest.run(payload);
    showToast(response?.run_id ? `Backtest started: ${response.run_id}` : "Backtest started.", "success");
    await loadVersions({ preserveSelection: true, silent: true });
    if (response?.run_id) {
      startRunPolling(response.run_id);
    }
  });
}

async function handleCompare() {
  state.selectedTab = "diff";
  renderPage();
  await loadVersionDetail({
    compareToVersionId: state.selectedCompareVersionId || null,
    silent: false,
  });
}

function handleSelectVersion(versionId) {
  const nextVersionId = String(versionId || "").trim();
  if (!nextVersionId || nextVersionId === state.selectedVersionId) return;
  state.selectedVersionId = nextVersionId;
  state.selectedCompareVersionId = "";
  state.selectedTab = "overview";
  state.versionDetail = null;
  syncUrlState();
  renderPage();
  void loadVersionDetail({ compareToVersionId: null, silent: false });
}

function handleCompareTargetChange(versionId) {
  state.selectedCompareVersionId = String(versionId || "").trim();
  state.selectedTab = "diff";
  renderPage();
  void loadVersionDetail({
    compareToVersionId: state.selectedCompareVersionId || null,
    silent: false,
  });
}

function handleTabChange(tabName) {
  const nextTab = String(tabName || "overview").trim();
  if (!["overview", "diff", "snapshots", "lineage", "runs"].includes(nextTab)) {
    return;
  }
  state.selectedTab = nextTab;
}

function handleVersionAction(action, extra) {
  if (!state.versionDetail?.version) return;

  if (action === "compare") {
    void handleCompare();
    return;
  }
  if (action === "run") {
    void handleRunBacktest();
    return;
  }
  if (action === "accept") {
    void handleAccept();
    return;
  }
  if (action === "reject") {
    void handleReject();
    return;
  }
  if (action === "rollback") {
    void handleRollback();
    return;
  }
  if (action === "rollback-config") {
    void handleRollback();
    return;
  }
  if (action === "rollback-to-version") {
    // Extract data from the button that triggered the action
    const button = extra?.target;
    const versionId = button?.dataset?.versionId;
    const runId = button?.dataset?.runId;

    // Runtime guard: check if version_id exists
    if (!versionId) {
      showToast("No linked version available for this run", "error");
      return;
    }

    // Build optional run context
    const runContext = runId ? { runId } : null;

    void handleRollback(versionId, runContext);
    return;
  }
  if (action === "select-version") {
    handleSelectVersion(extra);
    return;
  }
}

function attachTopLevelListeners() {
  elements.strategySelect?.addEventListener("change", () => {
    state.selectedStrategy = String(elements.strategySelect?.value || "").trim();
    state.selectedVersionId = "";
    state.selectedCompareVersionId = "";
    state.selectedTab = "overview";
    state.versionDetail = null;
    saveSelectedStrategy(state.selectedStrategy);
    syncUrlState();
    void loadVersions({ preserveSelection: false, silent: false });
  });

  elements.includeArchived?.addEventListener("change", () => {
    state.includeArchived = Boolean(elements.includeArchived?.checked);
    void loadVersions({ preserveSelection: true, silent: false });
  });

  elements.refreshButton?.addEventListener("click", () => {
    void loadVersions({ preserveSelection: true, silent: false });
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  attachTopLevelListeners();
  renderPage();
  await loadOptions();
  await loadVersions({ preserveSelection: true, silent: false });
});




