/**
 * run-form.js — Optimizer run form: reads fields and builds the payload.
 */

import { normalizePair, isValidPair } from "../../core/utils.js";
import persistence, { KEYS } from "../../core/persistence.js";

export function getOptimizerPayload() {
  const strategy   = document.getElementById("opt-select-strategy")?.value || "";
  const timeframe  = document.getElementById("opt-select-timeframe")?.value || "";
  const epochs     = parseInt(document.getElementById("opt-input-epochs")?.value || "100");
  const loss       = document.getElementById("opt-select-loss")?.value || "SharpeHyperOptLoss";
  const timerange  = document.getElementById("opt-input-timerange")?.value || undefined;
  const pairsRaw   = document.getElementById("opt-input-pairs")?.value || "";
  const spaces     = Array.from(document.querySelectorAll('input[name="spaces"]:checked')).map(el => el.value);

  const pairs = pairsRaw
    .split(/[\s,;]+/)
    .map(p => p.trim().toUpperCase())
    .filter(isValidPair);

  return { strategy, timeframe, epochs, hyperopt_loss: loss, timerange, pairs, spaces };
}

export function seedFromBacktest() {
  const saved = persistence.load(KEYS.BACKTEST_CONFIG, {});
  const pairsInput = document.getElementById("opt-input-pairs");
  const stratSelect = document.getElementById("opt-select-strategy");
  const tfSelect    = document.getElementById("opt-select-timeframe");

  if (saved.pairs?.length && pairsInput) pairsInput.value = saved.pairs.join(", ");
  if (saved.strategy && stratSelect)     stratSelect.value = saved.strategy;
  if (saved.timeframe && tfSelect)       tfSelect.value = saved.timeframe;
}

export function initRunForm() {
  document.getElementById("opt-seed-from-backtest")?.addEventListener("click", (e) => {
    e.preventDefault();
    seedFromBacktest();
  });
}
