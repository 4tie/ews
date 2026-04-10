/**
 * checkpoint-panel.js — Lists checkpoints and handles rollback.
 */

import api from "../../core/api.js";
import showToast from "../../components/toast.js";
import { emit, EVENTS } from "../../core/events.js";
import { formatPct } from "../../core/utils.js";

const listEl = document.getElementById("opt-checkpoint-list");

export async function loadCheckpoints(runId) {
  if (!listEl || !runId) return;
  try {
    const { checkpoints } = await api.optimizer.getCheckpoints(runId);
    renderCheckpoints(checkpoints, runId);
  } catch (e) {
    showToast("Failed to load checkpoints: " + e.message, "error");
  }
}

function renderCheckpoints(checkpoints, runId) {
  if (!listEl) return;
  if (!checkpoints?.length) {
    listEl.innerHTML = '<div class="info-empty">No checkpoints saved yet.</div>';
    return;
  }
  listEl.innerHTML = "";
  checkpoints.forEach(cp => {
    const pct = cp.profit_pct ?? 0;
    const item = document.createElement("div");
    item.className = "checkpoint-item";
    item.innerHTML = `
      <div class="checkpoint-item__meta">
        <span class="checkpoint-item__id">${cp.checkpoint_id}</span>
        <span class="checkpoint-item__profit ${pct >= 0 ? "positive" : "negative"}">
          Profit: ${formatPct(pct)} — epoch ${cp.epoch}
        </span>
      </div>
      <button class="btn btn--ghost btn--sm" data-rollback="${cp.checkpoint_id}">Rollback</button>
    `;
    listEl.appendChild(item);
  });

  listEl.addEventListener("click", async (e) => {
    const checkId = e.target.dataset.rollback;
    if (!checkId) return;
    if (!confirm(`Roll back to checkpoint ${checkId}?`)) return;
    try {
      await api.optimizer.rollback(runId, checkId);
      showToast("Rollback successful.", "success");
    } catch (e) {
      showToast("Rollback failed: " + e.message, "error");
    }
  });
}
