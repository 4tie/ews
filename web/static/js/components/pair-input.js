/**
 * pair-input.js - Smart pair input: handles typed/pasted pairs and pasted JSON configs.
 */

import { $ } from "../core/utils.js";
import { parsePairInput } from "../core/pair-parser.js";
import { setState, getState } from "../core/state.js";
import { emit, EVENTS } from "../core/events.js";
import showToast from "./toast.js";

const addInput = $("#input-pair-add");
const addBtn = $("#btn-add-pair");
const tagList = $("#pairs-tag-list");
const feedback = $("#json-parse-feedback");
const quickPairsContainer = $("#quick-pairs");

function renderTags() {
  if (!tagList) return;
  const pairs = getState("backtest.pairs") || [];
  tagList.innerHTML = "";
  pairs.forEach((pair) => {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.innerHTML = `${pair}<span class="tag__remove" data-pair="${pair}">&times;</span>`;
    tagList.appendChild(tag);
  });
}

function addPairsFromRaw(rawText) {
  let parsed;
  try {
    parsed = parsePairInput(rawText);
  } catch (e) {
    const msg = "Could not parse pairs (malformed input)";
    setFeedback(msg, "error");
    showToast(msg, "error");
    return;
  }

  const extracted = parsed?.pairs || [];
  if (!extracted.length) {
    const msg = "No valid pairs found. Example: BTC/USDT, ETH/USDT";
    setFeedback(msg, "warning");
    showToast(msg, "warning");
    return;
  }

  const existing = [...(getState("backtest.pairs") || [])];
  let added = 0;
  let skipped = 0;

  extracted.forEach((pair) => {
    if (existing.includes(pair)) {
      skipped += 1;
      return;
    }
    existing.push(pair);
    added += 1;
  });

  setState("backtest.pairs", existing);
  renderTags();
  updateQuickPairButtons();
  emit(EVENTS.PAIRS_UPDATED, existing);

  const duplicateNote = parsed.hadDuplicates || skipped > 0 ? " (duplicates ignored)" : "";
  const msg = added > 0 ? `Added ${added} pair(s)${duplicateNote}` : `All pairs already added${duplicateNote}`;

  setFeedback(msg, added > 0 ? "success" : "warning");
  showToast(msg, added > 0 ? "success" : "info");
}

function removePair(pair) {
  const pairs = (getState("backtest.pairs") || []).filter((p) => p !== pair);
  setState("backtest.pairs", pairs);
  renderTags();
  updateQuickPairButtons();
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

  const msg =
    `Loaded ${result.pairs.length} pair(s) from JSON` +
    (result.timeframes.length ? ` · timeframes: ${result.timeframes.join(", ")}` : "");
  setFeedback(msg, "success");
  showToast(msg, "success");

  if (addInput) addInput.value = "";
}

function setFeedback(msg, type) {
  if (!feedback) return;
  feedback.textContent = msg;
  feedback.className =
    `field-hint${type === "error" ? " is-error" : type === "success" ? " is-success" : ""}`;
  if (msg)
    setTimeout(() => {
      if (feedback) {
        feedback.textContent = "";
        feedback.className = "field-hint";
      }
    }, 5000);
}

function handleAdd() {
  const raw = addInput?.value || "";
  if (!raw.trim()) return;

  if (looksLikeJson(raw)) {
    tryParseJson(raw);
  } else {
    addPairsFromRaw(raw);
    if (addInput) addInput.value = "";
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
  const raw = Array.isArray(pairs) ? pairs.map(String).join("\n") : String(pairs ?? "");
  const parsed = parsePairInput(raw);
  const cleaned = parsed.pairs;

  setState("backtest.pairs", cleaned);
  renderTags();
  updateQuickPairButtons();
  emit(EVENTS.PAIRS_UPDATED, cleaned);
}

function updateQuickPairButtons() {
  if (!quickPairsContainer) return;
  const pairs = getState("backtest.pairs") || [];
  const buttons = quickPairsContainer.querySelectorAll(".quick-pair-btn");
  buttons.forEach((btn) => {
    const pair = btn.dataset.pair;
    if (pairs.includes(pair)) {
      btn.classList.add("is-active");
    } else {
      btn.classList.remove("is-active");
    }
  });
}

function toggleQuickPair(pair) {
  const pairs = [...(getState("backtest.pairs") || [])];
  const index = pairs.indexOf(pair);
  if (index === -1) {
    pairs.push(pair);
  } else {
    pairs.splice(index, 1);
  }
  setState("backtest.pairs", pairs);
  renderTags();
  updateQuickPairButtons();
  emit(EVENTS.PAIRS_UPDATED, pairs);
}

quickPairsContainer?.addEventListener("click", (e) => {
  const btn = e.target.closest(".quick-pair-btn");
  if (btn) {
    e.preventDefault();
    toggleQuickPair(btn.dataset.pair);
  }
});

export { renderTags, updateQuickPairButtons };