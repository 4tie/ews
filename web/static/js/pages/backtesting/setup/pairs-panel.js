/**
 * pairs-panel.js — Restores saved pairs on load and persists changes.
 */

import { getState } from "../../../core/state.js";
import { on, EVENTS } from "../../../core/events.js";
import persistence, { KEYS } from "../../../core/persistence.js";
import { setPairsFromArray } from "../../../components/pair-input.js";

export function initPairsPanel() {
  const saved = persistence.load(KEYS.BACKTEST_CONFIG, {});
  if (saved.pairs?.length) {
    setPairsFromArray(saved.pairs);
  }

  on(EVENTS.PAIRS_UPDATED, (pairs) => {
    const cfg = persistence.load(KEYS.BACKTEST_CONFIG, {});
    cfg.pairs = pairs;
    persistence.save(KEYS.BACKTEST_CONFIG, cfg);
  });
}
