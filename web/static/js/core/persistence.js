/**
 * persistence.js — Local browser state persistence via localStorage.
 *
 * API:
 *   persistence.save(key, data)
 *   persistence.load(key, fallback)
 *   persistence.remove(key)
 */

const PREFIX = "4tie::";

export const KEYS = {
  BACKTEST_CONFIG: "backtest-config",
  OPTIMIZER_CONFIG: "optimizer_config_v1",
  SETTINGS_UI_STATE: "settings-ui-state",
  THEME: "theme",
  AI_CHAT_UI_STATE: "ai-chat-ui-state",
  AI_CHAT_CONTEXT: "ai-chat-context",
  AI_CHAT_MESSAGE_OVERLAYS: "ai-chat-message-overlays",
};

function prefixed(key) { return PREFIX + key; }

export const persistence = {
  save(key, data) {
    try {
      localStorage.setItem(prefixed(key), JSON.stringify(data));
    } catch (e) {
      console.warn("[persistence] save failed:", e);
    }
  },

  load(key, fallback = null) {
    try {
      const raw = localStorage.getItem(prefixed(key));
      return raw != null ? JSON.parse(raw) : fallback;
    } catch (e) {
      console.warn("[persistence] load failed:", e);
      return fallback;
    }
  },

  remove(key) {
    try {
      localStorage.removeItem(prefixed(key));
    } catch (e) {
      console.warn("[persistence] remove failed:", e);
    }
  },

  clearAll() {
    const toRemove = Object.keys(localStorage).filter(k => k.startsWith(PREFIX));
    toRemove.forEach(k => localStorage.removeItem(k));
  },
};

window.persistence = persistence;
window.PERSISTENCE_KEYS = KEYS;
export default persistence;
