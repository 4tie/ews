/**
 * pair-input.js — Smart pair input: handles typed pairs and pasted JSON configs.
 */

import { normalizePair, isValidPair, $ } from "../core/utils.js";
import { setState, getState } from "../core/state.js";
import { emit, EVENTS } from "../core/events.js";
import showToast from "./toast.js";

const addInput = $("#input-pair-add");
const addBtn   = $("#btn-add-pair");
const tagList  = $("#pairs-tag-list");
const feedback = $("#json-parse-feedback");

function renderTags() {
  if (!tagList) return;
  const pairs = getState("backtest.pairs") || [];
  tagList.innerHTML = "";
  pairs.forEach(pair => {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.innerHTML = `${pair}<span class="tag__remove" data-pair="${pair}">&times;</span>`;
    tagList.appendChild(tag);
  });
}

function addPair(raw) {
  const pair = normalizePair(raw);
  if (!pair) return;
  if (!isValidPair(pair)) {
    showToast(`Invalid pair format: ${pair}`, "warning");
    return;
  }
  const pairs = [...(getState("backtest.pairs") || [])];
  if (pairs.includes(pair)) {
    showToast(`${pair} already added`, "info");
    return;
  }
  pairs.push(pair);
  setState("backtest.pairs", pairs);
  renderTags();
  emit(EVENTS.PAIRS_UPDATED, pairs);
}

function removePair(pair) {
  const pairs = (getState("backtest.pairs") || []).filter(p => p !== pair);
  setState("backtest.pairs", pairs);
  renderTags();
  emit(EVENTS.PAIRS_UPDATED, pairs);
}

function looksLikeJson(text) {
  const t = text.trim();
  return t.startsWith("{") || t.startsWith("[");
}

async function tryParseJson(text) {
  const { parseAndExtract } = await import("../pages/backtesting/setup/json-config-parser.js");
  const result = parseAndExtract(text);

  if (!result.ok) {
    setFeedback("Invalid JSON: " + result.error, "error");
    showToast("Could not parse JSON", "error");
    return;
  }
  if (!result.pairs.length) {
    setFeedback("No pairs found in config", "warning");
    showToast("No pairs found in config", "warning");
    return;
  }

  setPairsFromArray(result.pairs);

  const msg = `Loaded ${result.pairs.length} pair(s) from JSON` +
    (result.timeframes.length ? ` · timeframes: ${result.timeframes.join(", ")}` : "");
  setFeedback(msg, "success");
  showToast(msg, "success");

  if (addInput) addInput.value = "";
}

function setFeedback(msg, type) {
  if (!feedback) return;
  feedback.textContent = msg;
  feedback.className = `field-hint${type === "error" ? " is-error" : type === "success" ? " is-success" : ""}`;
  if (msg) setTimeout(() => {
    if (feedback) { feedback.textContent = ""; feedback.className = "field-hint"; }
  }, 5000);
}

function handleAdd() {
  const raw = addInput?.value?.trim() || "";
  if (!raw) return;

  if (looksLikeJson(raw)) {
    tryParseJson(raw);
  } else {
    addPair(raw);
    if (addInput) addInput.value = "";
    setFeedback("", "");
  }
}

addBtn?.addEventListener("click", handleAdd);

addInput?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    handleAdd();
  }
});

addInput?.addEventListener("paste", (e) => {
  const pasted = e.clipboardData?.getData("text") || "";
  if (looksLikeJson(pasted)) {
    e.preventDefault();
    tryParseJson(pasted);
  }
});

tagList?.addEventListener("click", (e) => {
  const removeBtn = e.target.closest(".tag__remove");
  if (removeBtn) removePair(removeBtn.dataset.pair);
});

export function setPairsFromArray(pairs) {
  const validated = (pairs || []).map(normalizePair).filter(isValidPair);
  setState("backtest.pairs", [...new Set(validated)]);
  renderTags();
  emit(EVENTS.PAIRS_UPDATED, [...new Set(validated)]);
}

export { renderTags };
