/**
 * theme-settings.js — Handles theme, accent color, density, radius, and font size.
 */

import persistence, { KEYS } from "../../core/persistence.js";

const ACCENT_KEY  = "accent-color";
const DENSITY_KEY = "ui-density";
const RADIUS_KEY  = "ui-radius";
const FONT_KEY    = "ui-font";
const BG_KEY      = "ui-bg";

const DEFAULT_ACCENT  = "#4f8ef7";
const DEFAULT_DENSITY = "normal";
const DEFAULT_RADIUS  = "rounded";
const DEFAULT_FONT    = "default";
const DEFAULT_BG      = "solid";

export function initThemeSettings() {
  const accentInput  = document.getElementById("set-accent-color");
  const accentPreview = document.getElementById("accent-color-preview");
  const accentValue  = document.getElementById("accent-color-value");
  const accentPicker = accentInput?.closest(".accent-color-picker");

  // ── Color Theme ────────────────────────────────────────────────
  const themeBtns = document.querySelectorAll("#theme-selector .theme-btn");
  const savedTheme = persistence.load(KEYS.THEME, "dark");
  applyTheme(savedTheme);
  setActiveBtn(themeBtns, "data-theme", savedTheme);
  themeBtns.forEach(btn => btn.addEventListener("click", () => {
    const v = btn.dataset.theme;
    applyTheme(v);
    persistence.save(KEYS.THEME, v);
    setActiveBtn(themeBtns, "data-theme", v);
  }));

  // ── Accent Color ───────────────────────────────────────────────
  const accentPresetBtns = document.querySelectorAll("#accent-presets .accent-preset");
  const savedAccent = persistence.load(ACCENT_KEY, DEFAULT_ACCENT);
  applyAccent(savedAccent, accentInput, accentPreview, accentValue);
  markActivePreset(accentPresetBtns, savedAccent);
  accentPicker?.addEventListener("click", () => accentInput?.click());
  accentInput?.addEventListener("input", () => {
    const color = accentInput.value;
    applyAccent(color, accentInput, accentPreview, accentValue);
    persistence.save(ACCENT_KEY, color);
    markActivePreset(accentPresetBtns, color);
  });
  accentPresetBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const color = btn.dataset.color;
      applyAccent(color, accentInput, accentPreview, accentValue);
      persistence.save(ACCENT_KEY, color);
      markActivePreset(accentPresetBtns, color);
    });
  });

  // ── UI Density ─────────────────────────────────────────────────
  const densityBtns = document.querySelectorAll("#density-selector .theme-btn");
  const savedDensity = persistence.load(DENSITY_KEY, DEFAULT_DENSITY);
  applyDensity(savedDensity);
  setActiveBtn(densityBtns, "data-density", savedDensity);
  densityBtns.forEach(btn => btn.addEventListener("click", () => {
    const v = btn.dataset.density;
    applyDensity(v);
    persistence.save(DENSITY_KEY, v);
    setActiveBtn(densityBtns, "data-density", v);
  }));

  // ── Corner Radius ──────────────────────────────────────────────
  const radiusBtns = document.querySelectorAll("#radius-selector .theme-btn");
  const savedRadius = persistence.load(RADIUS_KEY, DEFAULT_RADIUS);
  applyRadius(savedRadius);
  setActiveBtn(radiusBtns, "data-radius", savedRadius);
  radiusBtns.forEach(btn => btn.addEventListener("click", () => {
    const v = btn.dataset.radius;
    applyRadius(v);
    persistence.save(RADIUS_KEY, v);
    setActiveBtn(radiusBtns, "data-radius", v);
  }));

  // ── Font Size ──────────────────────────────────────────────────
  const fontBtns = document.querySelectorAll("#font-selector .theme-btn");
  const savedFont = persistence.load(FONT_KEY, DEFAULT_FONT);
  applyFont(savedFont);
  setActiveBtn(fontBtns, "data-font", savedFont);
  fontBtns.forEach(btn => btn.addEventListener("click", () => {
    const v = btn.dataset.font;
    applyFont(v);
    persistence.save(FONT_KEY, v);
    setActiveBtn(fontBtns, "data-font", v);
  }));

  // ── Background Style ───────────────────────────────────────────
  const bgBtns = document.querySelectorAll("#bg-selector .theme-btn");
  const savedBg = persistence.load(BG_KEY, DEFAULT_BG);
  applyBg(savedBg);
  setActiveBtn(bgBtns, "data-bg", savedBg);
  bgBtns.forEach(btn => btn.addEventListener("click", () => {
    const v = btn.dataset.bg;
    applyBg(v);
    persistence.save(BG_KEY, v);
    setActiveBtn(bgBtns, "data-bg", v);
  }));
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

function applyDensity(density) {
  document.documentElement.dataset.density = density === DEFAULT_DENSITY ? "" : density;
  if (density === DEFAULT_DENSITY) {
    delete document.documentElement.dataset.density;
  }
}

function applyRadius(radius) {
  if (radius === DEFAULT_RADIUS) {
    delete document.documentElement.dataset.radius;
  } else {
    document.documentElement.dataset.radius = radius;
  }
}

function applyFont(font) {
  if (font === DEFAULT_FONT) {
    delete document.documentElement.dataset.font;
  } else {
    document.documentElement.dataset.font = font;
  }
}

function applyBg(bg) {
  if (bg === DEFAULT_BG) {
    delete document.documentElement.dataset.bg;
  } else {
    document.documentElement.dataset.bg = bg;
  }
}

function setActiveBtn(btns, attr, value) {
  btns.forEach(b => b.classList.toggle("is-active", b.getAttribute(attr) === value));
}

function applyAccent(color, input, preview, valueLabel) {
  document.documentElement.style.setProperty("--color-accent", color);
  if (input)      input.value = color;
  if (preview)    preview.style.background = color;
  if (valueLabel) valueLabel.textContent = color.toUpperCase();
}

function markActivePreset(btns, color) {
  const normalized = color.toLowerCase();
  btns.forEach(b => b.classList.toggle("is-active", b.dataset.color.toLowerCase() === normalized));
}
