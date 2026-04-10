/**
 * utils.js — General-purpose utility functions.
 */

export function $(selector, root = document) {
  return root.querySelector(selector);
}

export function $$(selector, root = document) {
  return Array.from(root.querySelectorAll(selector));
}

export function el(tag, attrs = {}, ...children) {
  const elem = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") elem.className = v;
    else if (k.startsWith("data-")) elem.dataset[k.slice(5)] = v;
    else elem.setAttribute(k, v);
  }
  for (const child of children) {
    if (typeof child === "string") elem.appendChild(document.createTextNode(child));
    else if (child) elem.appendChild(child);
  }
  return elem;
}

export function formatPct(val, decimals = 2) {
  if (val == null) return "—";
  const n = parseFloat(val);
  return `${n >= 0 ? "+" : ""}${n.toFixed(decimals)}%`;
}

export function formatNum(val, decimals = 4) {
  if (val == null) return "—";
  return parseFloat(val).toFixed(decimals);
}

export function formatDate(dateStr) {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleString();
}

export function debounce(fn, ms = 300) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

export function copyToClipboard(text) {
  navigator.clipboard?.writeText(text).catch(() => {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); document.body.removeChild(ta);
  });
}

export function normalizePair(raw) {
  return raw.trim().toUpperCase().replace(/[\s,;]+/g, "");
}

export function isValidPair(pair) {
  return /^[A-Z0-9]+\/[A-Z0-9]+$/.test(pair);
}

window._utils = { $, $$, el, formatPct, formatNum, formatDate, debounce, copyToClipboard, normalizePair, isValidPair };
