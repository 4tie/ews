/**
 * pairs-panel.js — Restores saved pairs on load and persists changes.
 */

import { getState } from "../../../core/state.js";
import { on, EVENTS } from "../../../core/events.js";
import persistence, { KEYS } from "../../../core/persistence.js";
import { setPairsFromArray } from "../../../components/pair-input.js";
import { usePersistentState } from "../../../core/usePersistentState.js";

export function initPairsPanel() {
  const [savedConfig, setSavedConfig] = usePersistentState(KEYS.BACKTEST_CONFIG, {});
  
  if (savedConfig.pairs?.length) {
    setPairsFromArray(savedConfig.pairs);
  }

  on(EVENTS.PAIRS_UPDATED, (pairs) => {
    setSavedConfig(prev => ({ ...prev, pairs }));
  });
}
