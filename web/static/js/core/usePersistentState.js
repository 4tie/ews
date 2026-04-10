/**
 * usePersistentState.js — Unified persistent state management.
 * 
 * Provides a simple API to create state that automatically persists to localStorage.
 * Integrates with existing persistence.js infrastructure.
 * 
 * Usage:
 *   const [state, setState] = usePersistentState('key', defaultValue);
 *   const [complexState, setComplexState] = usePersistentState('complexKey', { ... });
 */

import persistence from "./persistence.js";

const _states = {};
const _listeners = new Map();

function _generateId(key) {
  return key;
}

export function usePersistentState(key, defaultValue) {
  const id = _generateId(key);
  
  if (!_states[id]) {
    const stored = persistence.load(key, null);
    _states[id] = stored !== null ? stored : defaultValue;
  }
  
  const state = _states[id];
  
  const setState = (value) => {
    const next = typeof value === 'function' ? value(_states[id]) : value;
    _states[id] = next;
    persistence.save(key, next);
    _notifyListeners(id, next);
  };
  
  return [state, setState];
}

function _notifyListeners(id, value) {
  if (_listeners.has(id)) {
    _listeners.get(id).forEach(fn => fn(value));
  }
}

export function subscribe(key, callback) {
  const id = _generateId(key);
  if (!_listeners.has(id)) {
    _listeners.set(id, []);
  }
  _listeners.get(id).push(callback);
  
  return () => {
    const cbs = _listeners.get(id);
    const idx = cbs.indexOf(callback);
    if (idx !== -1) cbs.splice(idx, 1);
  };
}

export function getPersistentState(key, defaultValue = null) {
  const id = _generateId(key);
  return _states[id] !== undefined ? _states[id] : (persistence.load(key, defaultValue) ?? defaultValue);
}

export function setPersistentState(key, value) {
  const id = _generateId(key);
  const next = typeof value === 'function' ? value(_states[id] ?? persistence.load(key, null)) : value;
  _states[id] = next;
  persistence.save(key, next);
  _notifyListeners(id, next);
}

export function clearPersistentState(key) {
  const id = _generateId(key);
  delete _states[id];
  persistence.remove(key);
  _notifyListeners(id, undefined);
}

window.usePersistentState = usePersistentState;
window.subscribe = subscribe;
window.getPersistentState = getPersistentState;
window.setPersistentState = setPersistentState;
window.clearPersistentState = clearPersistentState;