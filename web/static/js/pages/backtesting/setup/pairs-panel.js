/**
 * pairs-panel.js — Handle pair input and tag list.
 */

import { setState, getState } from "../../../core/state.js";
import { emit, EVENTS } from "../../../core/events.js";

export function initPairsPanel() {
  const pairInput = document.getElementById("input-pair-add");
  const addBtn = document.getElementById("btn-add-pair");
  const tagList = document.getElementById("pairs-tag-list");
  
  addBtn?.addEventListener("click", () => {
    const value = pairInput?.value?.trim();
    if (!value) return;
    
    // Parse comma or newline separated pairs
    const pairs = value.split(/[,\n]/).map(p => p.trim()).filter(Boolean);
    
    const currentPairs = getState("backtest.pairs") || [];
    const newPairs = [...new Set([...currentPairs, ...pairs])];
    
    setState("backtest.pairs", newPairs);
    if (pairInput) pairInput.value = "";
    
    renderPairTags(newPairs, tagList);
    emit(EVENTS.PAIRS_UPDATED, newPairs);
  });
  
  // Allow Enter key to add
  pairInput?.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      addBtn?.click();
    }
  });
  
  // Render initial pairs
  const initialPairs = getState("backtest.pairs") || [];
  renderPairTags(initialPairs, tagList);
}

function renderPairTags(pairs, container) {
  if (!container) return;
  
  container.innerHTML = "";
  
  pairs.forEach(pair => {
    const tag = document.createElement("div");
    tag.className = "tag";
    tag.innerHTML = `
      <span>${pair}</span>
      <button class="tag-remove" data-pair="${pair}">×</button>
    `;
    
    tag.querySelector(".tag-remove")?.addEventListener("click", () => {
      const updated = pairs.filter(p => p !== pair);
      setState("backtest.pairs", updated);
      renderPairTags(updated, container);
      emit(EVENTS.PAIRS_UPDATED, updated);
    });
    
    container.appendChild(tag);
  });
}
