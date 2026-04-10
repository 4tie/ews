/**
 * events.js — App-level event bus for decoupled inter-module communication.
 */

const _handlers = {};

export function emit(event, data = null) {
  console.debug(`[event] ${event}`, data);
  (_handlers[event] || []).forEach(fn => fn(data));
}

export function on(event, handler) {
  if (!_handlers[event]) _handlers[event] = [];
  _handlers[event].push(handler);
}

export function off(event, handler) {
  if (_handlers[event]) {
    _handlers[event] = _handlers[event].filter(fn => fn !== handler);
  }
}

// Named app events
export const EVENTS = {
  BACKTEST_STARTED:   "backtest:started",
  BACKTEST_COMPLETE:  "backtest:complete",
  BACKTEST_FAILED:    "backtest:failed",
  BACKTEST_STOPPED:   "backtest:stopped",
  RESULTS_LOADED:     "results:loaded",
  OPTIMIZER_STARTED:  "optimizer:started",
  OPTIMIZER_STOPPED:  "optimizer:stopped",
  OPTIMIZER_EPOCH:    "optimizer:epoch",
  CHECKPOINT_SAVED:   "optimizer:checkpoint",
  SETTINGS_SAVED:     "settings:saved",
  PAIRS_UPDATED:      "pairs:updated",
  CONFIG_LOADED:      "config:loaded",
  TOAST:              "toast",
};

window._events = { emit, on, off, EVENTS };
