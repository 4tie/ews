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
    createProposalCandidate: (runId, data) => api.post(`/api/backtest/runs/${encodeURIComponent(runId)}/proposal-candidates`, data),
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

  aiChat: {
    chat: (data) => api.post("/api/ai/chat/chat", data),
    applyCode: (data) => api.post("/api/ai/chat/apply-code", data),
    applyParameters: (data) => api.post("/api/ai/chat/apply-parameters", data),
    getThread: (strategy) => api.get(`/api/ai/chat/threads/${encodeURIComponent(strategy)}`),
    createThreadMessage: (strategy, data) => api.post(`/api/ai/chat/threads/${encodeURIComponent(strategy)}/messages`, data),
    getJob: (jobId) => api.get(`/api/ai/chat/jobs/${encodeURIComponent(jobId)}`),
  },

  aiEvolution: {
    analyzeStrategy: (data) => api.post("/api/ai/evolution/analyze-strategy", data),
    analyzeMetrics: (data) => api.post("/api/ai/evolution/analyze-metrics", data),
  },

  versions: {
    listVersions: (strategy, includeArchived = false) => api.get(`/api/versions/${encodeURIComponent(strategy)}${toQuery({ include_archived: includeArchived })}`),
    getActive: (strategy) => api.get(`/api/versions/${encodeURIComponent(strategy)}/active`),
    getVersion: (strategy, versionId) => api.get(`/api/versions/${encodeURIComponent(strategy)}/${encodeURIComponent(versionId)}`),
    accept: (strategy, data) => api.post(`/api/versions/${encodeURIComponent(strategy)}/accept`, data),
    reject: (strategy, data) => api.post(`/api/versions/${encodeURIComponent(strategy)}/reject`, data),
    rollback: (strategy, data) => api.post(`/api/versions/${encodeURIComponent(strategy)}/rollback`, data),
  },
};

window.api = api;
export default api;
