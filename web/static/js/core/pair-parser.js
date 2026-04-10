/**
 * pair-parser.js - Robust, noise-tolerant trading pair extraction.
 *
 * Canonical output format: BASE/QUOTE (uppercase).
 * Supports:
 *  - Explicit slash pairs: BTC/USDT (spaces around slash tolerated)
 *  - Combined symbols: BTCUSDT (requires known quote suffix or availablePairs mapping)
 *
 * Notes:
 * - Does NOT infer pairs from "BTC-USDT" or "BTC USDT" (treated as separators).
 * - If `availablePairs` is provided, parsed pairs are validated against it.
 */

const DEFAULT_QUOTE_SUFFIXES = [
  // Stablecoins / fiat
  "FDUSD",
  "USDT",
  "USDC",
  "BUSD",
  "TUSD",
  "USDP",
  "DAI",
  "PAX",
  "EUR",
  "GBP",
  "JPY",
  "TRY",
  "BRL",
  "AUD",
  "CAD",
  "CHF",
  // Common crypto quotes
  "BTC",
  "ETH",
  "BNB",
];

const VALID_PAIR_RE = /^[A-Z0-9]+\/[A-Z0-9]+$/;
const SLASH_VARIANTS_RE = /[\uFF0F\u2215\u2044]/g;

function hasLetter(symbol) {
  return /[A-Z]/.test(symbol);
}

function safeNormalizeText(rawText) {
  let text = String(rawText ?? "");
  if (typeof text.normalize === "function") {
    try {
      text = text.normalize("NFKC");
    } catch (_) {
      // Ignore invalid unicode normalization inputs.
    }
  }

  // Normalize common slash variants to ASCII slash.
  text = text.replace(SLASH_VARIANTS_RE, "/");

  // Treat most punctuation (incl. Arabic punctuation) as separators.
  // Keep only ASCII letters, digits, slash, and whitespace.
  text = text.replace(/[^A-Za-z0-9/]+/g, " ");
  return text.trim();
}

function normalizeSymbol(raw) {
  const up = String(raw ?? "").toUpperCase();
  const cleaned = up.replace(/[^A-Z0-9]+/g, "");
  return cleaned || "";
}

function canonicalFromSlash(baseRaw, quoteRaw) {
  const base = normalizeSymbol(baseRaw);
  const quote = normalizeSymbol(quoteRaw);
  if (base.length < 2 || quote.length < 2) return null;
  if (!hasLetter(base) || !hasLetter(quote)) return null;

  const pair = `${base}/${quote}`;
  if (!VALID_PAIR_RE.test(pair)) return null;
  return pair;
}

function canonicalFromCombined(tokenRaw, combinedToCanonical, quoteSuffixes) {
  const token = normalizeSymbol(tokenRaw);
  if (!token) return null;

  if (combinedToCanonical && combinedToCanonical.has(token)) {
    return combinedToCanonical.get(token);
  }

  // Split by a known quote suffix (longest-first).
  const suffixes = (quoteSuffixes || DEFAULT_QUOTE_SUFFIXES)
    .slice()
    .sort((a, b) => b.length - a.length);

  for (const quote of suffixes) {
    if (!quote) continue;
    if (token.length <= quote.length) continue;
    if (!token.endsWith(quote)) continue;

    const base = token.slice(0, token.length - quote.length);
    if (base.length < 2) continue;
    if (!hasLetter(base) || !hasLetter(quote)) continue;

    const pair = `${base}/${quote}`;
    if (!VALID_PAIR_RE.test(pair)) continue;
    return pair;
  }

  return null;
}

function buildAvailableMaps(availablePairs) {
  if (!Array.isArray(availablePairs) || availablePairs.length === 0) {
    return {
      availableSet: null,
      combinedToCanonical: null,
      quoteSuffixes: DEFAULT_QUOTE_SUFFIXES,
    };
  }

  const availableSet = new Set();
  const combinedToCanonical = new Map();

  for (const raw of availablePairs) {
    const str = String(raw ?? "");
    let canonical = null;

    if (str.includes("/")) {
      const parts = str.split("/");
      if (parts.length === 2) canonical = canonicalFromSlash(parts[0], parts[1]);
    } else {
      canonical = canonicalFromCombined(str, null, DEFAULT_QUOTE_SUFFIXES);
    }

    if (!canonical) continue;
    availableSet.add(canonical);
    combinedToCanonical.set(canonical.replace("/", ""), canonical);
  }

  // Infer quote suffixes from the allowlist (improves combined-token splitting).
  const quoteSuffixes = Array.from(
    new Set(
      Array.from(availableSet)
        .map((p) => p.split("/")[1])
        .filter(Boolean)
    )
  ).sort((a, b) => b.length - a.length);

  return {
    availableSet,
    combinedToCanonical,
    quoteSuffixes: quoteSuffixes.length ? quoteSuffixes : DEFAULT_QUOTE_SUFFIXES,
  };
}

/**
 * Parse a raw user-provided input string and extract unique valid trading pairs.
 *
 * @param {string} rawText
 * @param {string[]=} availablePairs Optional allowlist of supported pairs.
 * @returns {{pairs: string[], invalidTokens: string[], hadDuplicates: boolean}}
 */
export function parsePairInput(rawText, availablePairs) {
  const { availableSet, combinedToCanonical, quoteSuffixes } = buildAvailableMaps(availablePairs);

  const pairs = [];
  const invalidTokens = [];
  let hadDuplicates = false;

  const seen = new Set();
  const text = safeNormalizeText(rawText);
  if (!text) return { pairs, invalidTokens, hadDuplicates };

  // Scan left-to-right to preserve first-seen order across formats.
  const scanRe = /([A-Za-z0-9]{2,24})\s*\/\s*([A-Za-z0-9]{2,24})|([A-Za-z0-9]{6,32})/g;
  let match;

  while ((match = scanRe.exec(text)) !== null) {
    let canonical = null;
    let rawToken = match[0];

    if (match[1] && match[2]) {
      rawToken = `${match[1]}/${match[2]}`;
      canonical = canonicalFromSlash(match[1], match[2]);
    } else if (match[3]) {
      rawToken = match[3];
      canonical = canonicalFromCombined(match[3], combinedToCanonical, quoteSuffixes);
    }

    if (!canonical) {
      // Keep invalid token reporting low-noise.
      const upper = normalizeSymbol(rawToken);
      if (upper && upper.length <= 24 && hasLetter(upper) && invalidTokens.length < 20) {
        invalidTokens.push(rawToken);
      }
      continue;
    }

    if (availableSet && !availableSet.has(canonical)) {
      if (invalidTokens.length < 20) invalidTokens.push(rawToken);
      continue;
    }

    if (seen.has(canonical)) {
      hadDuplicates = true;
      continue;
    }

    seen.add(canonical);
    pairs.push(canonical);
  }

  return { pairs, invalidTokens, hadDuplicates };
}

// Unit-test-like examples (safe to import; not executed automatically).
export const PAIR_PARSER_EXAMPLES = [
  {
    input: "ETH/USDT, BTC/USDT, ETH/USDT",
    expected: ["ETH/USDT", "BTC/USDT"],
  },
  {
    input: "eth/usdt\nbtc/usdt\nsol/usdt",
    expected: ["ETH/USDT", "BTC/USDT", "SOL/USDT"],
  },
  {
    input: "hello ### ETH/USDT ... BTCUSDT ... ??? SOL/USDT",
    expected: ["ETH/USDT", "BTC/USDT", "SOL/USDT"],
  },
  {
    input: "ETH USDT, BTC-USDT, XRP/USDT, xrpusdt",
    expected: ["XRP/USDT"],
  },
];

export function runPairParserExamples() {
  const failures = [];
  for (const ex of PAIR_PARSER_EXAMPLES) {
    const got = parsePairInput(ex.input).pairs;
    const ok = JSON.stringify(got) === JSON.stringify(ex.expected);
    if (!ok) failures.push({ input: ex.input, expected: ex.expected, got });
  }
  return { ok: failures.length === 0, failures };
}

if (typeof window !== "undefined") {
  window._pairParser = { parsePairInput, runPairParserExamples, PAIR_PARSER_EXAMPLES };
}