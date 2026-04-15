/**
 * state.js - Lightweight reactive application state store.
 */

const _listeners = {};
const _state = {
  backtest: {
    isRunning: false,
    strategy: "",
    timeframe: "",
    pairs: [],
    startDate: "",
    endDate: "",
    exchange: "binance",
    dry_run_wallet: "",
    maxOpenTrades: "",
    lastResult: null,
    selectedCandidateVersionId: null,
    selectedCandidateVersionBySourceRef: {},
  },
  optimizer: {
    isRunning: false,
    runId: null,
    currentEpoch: 0,
    bestResult: null,
    checkpoints: [],
  },
  settings: {},
};

export function getState(path) {
  const parts = path.split(".");
  let node = _state;
  for (const p of parts) {
    if (node == null) return undefined;
    node = node[p];
  }
  return node;
}

export function setState(path, value) {
  const parts = path.split(".");
  let node = _state;
  for (let i = 0; i < parts.length - 1; i++) {
    node = node[parts[i]];
  }
  node[parts[parts.length - 1]] = value;
  emit(path, value);
}

export function on(path, callback) {
  if (!_listeners[path]) _listeners[path] = [];
  _listeners[path].push(callback);
}

export function off(path, callback) {
  if (_listeners[path]) {
    _listeners[path] = _listeners[path].filter(fn => fn !== callback);
  }
}

function emit(path, value) {
  (_listeners[path] || []).forEach(fn => fn(value));
  // also emit parent paths
  const parts = path.split(".");
  if (parts.length > 1) {
    emit(parts.slice(0, -1).join("."), getState(parts.slice(0, -1).join(".")));
  }
}

window._appState = _state;

