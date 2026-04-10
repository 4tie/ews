/**
 * form-helpers.js — Utilities for reading/writing form field values.
 */

export function getFormValues(formOrSelector) {
  const form = typeof formOrSelector === "string"
    ? document.querySelector(formOrSelector)
    : formOrSelector;
  if (!form) return {};

  const data = {};
  const inputs = form.querySelectorAll("input, select, textarea");
  inputs.forEach(el => {
    if (!el.name) return;
    if (el.type === "checkbox") {
      if (!data[el.name]) data[el.name] = [];
      if (el.checked) data[el.name].push(el.value);
    } else {
      data[el.name] = el.value;
    }
  });
  return data;
}

export function populateForm(formOrSelector, data = {}) {
  const form = typeof formOrSelector === "string"
    ? document.querySelector(formOrSelector)
    : formOrSelector;
  if (!form || !data) return;

  const inputs = form.querySelectorAll("input, select, textarea");
  inputs.forEach(el => {
    if (!el.name || !(el.name in data)) return;
    const val = data[el.name];
    if (el.type === "checkbox") {
      el.checked = Array.isArray(val) ? val.includes(el.value) : Boolean(val);
    } else {
      el.value = val ?? "";
    }
  });
}
