/**
 * api.js - Centralized fetch wrapper for all backend API calls.
 */

const BASE = "";

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== null) opts.body = JSON.stringify(body);

  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

function toQuery(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === "") return;
    search.set(key, String(value));
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body),
  delete: (path) => request("DELETE", path),

  backtest: {
    options: () => api.get("/api/backtest/options"),
    run: (data) => api.post("/api/backtest/run", data),
    downloadData: (data) => api.post("/api/backtest/download-data", data),
    validateData: (data) => api.post("/api/backtest/validate-data", data),
    listRuns: (filters = {}) => api.get(`/api/backtest/runs${toQuery(filters)}`),
    getRun: (runId) => api.get(`/api/backtest/runs/${encodeURIComponent(runId)}`),
    getRunDiagnosis: (runId, options = {}) => api.get(`/api/backtest/runs/${encodeURIComponent(runId)}/diagnosis${toQuery({ include_ai: options.include_ai })}`),
    compareRuns: (leftRunId, rightRunId) => api.get(`/api/backtest/compare${toQuery({ left_run_id: leftRunId, right_run_id: rightRunId })}`),
    summary: (strat) => api.get(`/api/backtest/summary?strategy=${encodeURIComponent(strat)}`),
    trades: (strat) => api.get(`/api/backtest/trades?strategy=${encodeURIComponent(strat)}`),
    listConfigs: () => api.get("/api/backtest/configs"),
    loadConfig: (name) => api.get(`/api/backtest/configs/${encodeURIComponent(name)}`),
    saveConfig: (data) => api.post("/api/backtest/configs", data),
    deleteConfig: (name) => api.delete(`/api/backtest/configs/${encodeURIComponent(name)}`),
  },

  optimizer: {
    startRun: (data) => api.post("/api/optimizer/runs", data),
    getCheckpoints: (runId) => api.get(`/api/optimizer/runs/${runId}/checkpoints`),
    rollback: (runId, checkId) => api.post(`/api/optimizer/runs/${runId}/rollback/${checkId}`, {}),
    streamLogs: (runId) => new EventSource(`/api/optimizer/runs/${runId}/logs/stream`),
  },

  settings: {
    get: () => api.get("/api/settings"),
    save: (data) => api.post("/api/settings", data),
  },
};

window.api = api;
export default api;

