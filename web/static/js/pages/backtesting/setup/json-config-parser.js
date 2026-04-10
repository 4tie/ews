/**
 * json-config-parser.js - Parse pasted freqtrade JSON config snippets.
 *
 * Designed to extract:
 *   - pair_whitelist
 *   - feature_parameters.include_corr_pairlist
 *   - feature_parameters.include_timeframes
 */

import { parsePairInput } from "../../../core/pair-parser.js";

/**
 * Attempt to parse raw JSON text.
 * @param {string} text
 * @returns {{ ok: boolean, data?: object, error?: string }}
 */
export function parseJsonText(text) {
  try {
    const data = JSON.parse(text.trim());
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

/**
 * Extract pairs from a plain array (e.g., ["BTC/USDT", "ETH/USDT"]).
 * @param {Array} arr
 * @returns {string[]}
 */
function extractFromPlainArray(arr) {
  if (!Array.isArray(arr)) return [];
  return parsePairInput(arr.map(String).join("\n")).pairs;
}

/**
 * Extract pairs from arbitrary pasted text.
 * @param {string} text
 * @returns {string[]}
 */
function extractFromPlainText(text) {
  if (typeof text !== "string") return [];
  return parsePairInput(text).pairs;
}

/**
 * Extract and normalize pairs from a parsed config object.
 * Pulls from pair_whitelist and feature_parameters.include_corr_pairlist.
 * Also handles plain arrays and raw strings.
 *
 * @param {object|Array|string} config
 * @returns {{ pairs: string[], timeframes: string[], raw: any }}
 */
export function extractFromConfig(config) {
  if (!config) {
    return { pairs: [], timeframes: [], raw: config };
  }

  if (Array.isArray(config)) {
    return { pairs: extractFromPlainArray(config), timeframes: [], raw: config };
  }

  if (typeof config === "string") {
    return { pairs: extractFromPlainText(config), timeframes: [], raw: config };
  }

  if (typeof config !== "object") {
    return { pairs: [], timeframes: [], raw: config };
  }

  const rawPairs = [
    ...(config.pair_whitelist || []),
    ...((config.feature_parameters || {}).include_corr_pairlist || []),
  ];

  const timeframes = (config.feature_parameters || {}).include_timeframes || [];
  const pairs = parsePairInput(rawPairs.map(String).join("\n")).pairs;

  return { pairs, timeframes, raw: config };
}

/**
 * Full pipeline: parse text -> extract pairs + timeframes.
 * Tries JSON first, then falls back to plain text parsing.
 *
 * @param {string} text
 * @returns {{ ok: boolean, pairs?: string[], timeframes?: string[], raw?: any, error?: string }}
 */
export function parseAndExtract(text) {
  const jsonResult = parseJsonText(text);

  if (jsonResult.ok) {
    const extracted = extractFromConfig(jsonResult.data);
    return { ok: true, ...extracted };
  }

  const pairs = extractFromPlainText(text);
  if (pairs.length > 0) {
    return { ok: true, pairs, timeframes: [], raw: text };
  }

  return { ok: false, error: jsonResult.error };
}