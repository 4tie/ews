/**
 * persisted-runs-store.js - Shared read-only store for persisted backtest runs.
 */

import api from "../../../core/api.js";
import { on as onEvent, EVENTS } from "../../../core/events.js";
import { getState, on as onState } from "../../../core/state.js";

const listeners = new Set();
const snapshot = {
  status: "idle",
  strategy: "",
  runs: [],
  allRuns: [],
  error: null,
};

let initialized = false;
let requestId = 0;

export function initPersistedRunsStore() {
  if (initialized) return;
  initialized = true;

  onState("backtest.strategy", refreshPersistedRuns);
  onEvent(EVENTS.BACKTEST_COMPLETE, refreshPersistedRuns);
  onEvent(EVENTS.BACKTEST_FAILED, refreshPersistedRuns);
  onEvent(EVENTS.BACKTEST_STOPPED, refreshPersistedRuns);

  refreshPersistedRuns();
}

export function subscribePersistedRuns(listener) {
  listeners.add(listener);
  listener(getPersistedRunsSnapshot());
  return () => listeners.delete(listener);
}

export function getPersistedRunsSnapshot() {
  return {
    ...snapshot,
    runs: Array.isArray(snapshot.runs) ? [...snapshot.runs] : [],
    allRuns: Array.isArray(snapshot.allRuns) ? [...snapshot.allRuns] : [],
  };
}

export async function refreshPersistedRuns() {
  const strategy = getState("backtest.strategy") || "";
  const currentRequestId = ++requestId;

  snapshot.status = "loading";
  snapshot.strategy = strategy;
  snapshot.error = null;
  emitChange();

  try {
    const { runs = [] } = await api.backtest.listRuns();
    if (currentRequestId !== requestId) return;

    const allRuns = Array.isArray(runs) ? runs : [];
    snapshot.status = "ready";
    snapshot.strategy = strategy;
    snapshot.allRuns = allRuns;
    snapshot.runs = strategy ? allRuns.filter((run) => run?.strategy === strategy) : allRuns;
    snapshot.error = null;
    emitChange();
  } catch (error) {
    if (currentRequestId !== requestId) return;

    snapshot.status = "error";
    snapshot.strategy = strategy;
    snapshot.runs = [];
    snapshot.allRuns = [];
    snapshot.error = error?.message || String(error);
    emitChange();
  }
}

function emitChange() {
  const next = getPersistedRunsSnapshot();
  listeners.forEach((listener) => listener(next));
}
