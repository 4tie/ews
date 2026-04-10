/**
 * json-config-parser.js — Parse pasted freqtrade JSON config snippets.
 *
 * Designed to extract:
 *   - pair_whitelist
 *   - feature_parameters.include_corr_pairlist
 *   - feature_parameters.include_timeframes
 */

import { normalizePair, isValidPair } from "../../../core/utils.js";

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
 * Extract and normalize pairs from a parsed config object.
 * Pulls from pair_whitelist and feature_parameters.include_corr_pairlist.
 * @param {object} config
 * @returns {{ pairs: string[], timeframes: string[], raw: object }}
 */
export function extractFromConfig(config) {
  if (!config || typeof config !== "object") {
    return { pairs: [], timeframes: [], raw: config };
  }

  const rawPairs = [
    ...(config.pair_whitelist || []),
    ...((config.feature_parameters || {}).include_corr_pairlist || []),
  ];

  const timeframes = ((config.feature_parameters || {}).include_timeframes || []);

  const pairs = deduplicatePairs(
    rawPairs.map(normalizePair).filter(isValidPair)
  );

  return { pairs, timeframes, raw: config };
}

/**
 * Full pipeline: parse text → extract pairs + timeframes.
 * @param {string} text
 * @returns {{ ok: boolean, pairs?: string[], timeframes?: string[], error?: string }}
 */
export function parseAndExtract(text) {
  const parsed = parseJsonText(text);
  if (!parsed.ok) return parsed;
  const extracted = extractFromConfig(parsed.data);
  return { ok: true, ...extracted };
}

function deduplicatePairs(pairs) {
  return [...new Set(pairs)];
}
