/**
 * general-settings.js — Manages general settings fields.
 */

import { setState } from "../../core/state.js";

export function initGeneralSettings() {
  const exchange  = document.getElementById("set-exchange");
  const timeframe = document.getElementById("set-timeframe");

  exchange?.addEventListener("change",  () => setState("settings.default_exchange",  exchange.value));
  timeframe?.addEventListener("change", () => setState("settings.default_timeframe", timeframe.value));
}
