/**
 * persisted-versions-store.js - Shared read-only store for persisted strategy versions.
 */

import api from "../../../core/api.js";
import { on as onEvent, EVENTS } from "../../../core/events.js";
import { getState, on as onState } from "../../../core/state.js";

const listeners = new Set();
const snapshot = {
  status: "idle",
  strategy: "",
  versions: [],
  activeVersionId: null,
  error: null,
};

let initialized = false;
let requestId = 0;

export function initPersistedVersionsStore() {
  if (initialized) return;
  initialized = true;

  onState("backtest.strategy", refreshPersistedVersions);
  onEvent(EVENTS.BACKTEST_COMPLETE, refreshPersistedVersions);
  onEvent(EVENTS.BACKTEST_FAILED, refreshPersistedVersions);
  onEvent(EVENTS.BACKTEST_STOPPED, refreshPersistedVersions);

  refreshPersistedVersions();
}

export function subscribePersistedVersions(listener) {
  listeners.add(listener);
  listener(getPersistedVersionsSnapshot());
  return () => listeners.delete(listener);
}

export function getPersistedVersionsSnapshot() {
  return {
    ...snapshot,
    versions: Array.isArray(snapshot.versions) ? [...snapshot.versions] : [],
  };
}

export async function refreshPersistedVersions(strategyOverride = null, options = {}) {
  const strategy = typeof strategyOverride === "string" ? strategyOverride : (getState("backtest.strategy") || "");
  const currentRequestId = ++requestId;

  if (!strategy) {
    snapshot.status = "idle";
    snapshot.strategy = "";
    snapshot.versions = [];
    snapshot.activeVersionId = null;
    snapshot.error = null;
    emitChange();
    return;
  }

  if (!options?.silent) {
    snapshot.status = "loading";
    snapshot.strategy = strategy;
    snapshot.error = null;
    emitChange();
  }

  try {
    const response = await api.versions.listVersions(strategy, true);
    if (currentRequestId !== requestId) return;

    snapshot.status = "ready";
    snapshot.strategy = strategy;
    snapshot.versions = Array.isArray(response?.versions) ? response.versions : [];
    snapshot.activeVersionId = response?.active_version_id || null;
    snapshot.error = null;
    emitChange();
  } catch (error) {
    if (currentRequestId !== requestId) return;

    snapshot.status = "error";
    snapshot.strategy = strategy;
    snapshot.versions = [];
    snapshot.activeVersionId = null;
    snapshot.error = error?.message || String(error);
    emitChange();
  }
}

function emitChange() {
  const next = getPersistedVersionsSnapshot();
  listeners.forEach((listener) => listener(next));
}
