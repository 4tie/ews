/**
 * loading-state.js — Show/hide loading states on containers.
 */

export function setLoading(el, isLoading, message = "Loading…") {
  if (!el) return;
  if (isLoading) {
    el.dataset.prevContent = el.innerHTML;
    el.innerHTML = `<div class="info-empty">${message}</div>`;
    el.classList.add("is-loading");
  } else {
    if (el.dataset.prevContent !== undefined) {
      el.innerHTML = el.dataset.prevContent;
      delete el.dataset.prevContent;
    }
    el.classList.remove("is-loading");
  }
}

export function setButtonLoading(btn, isLoading, loadingText = "Loading…") {
  if (!btn) return;
  if (isLoading) {
    btn.dataset.origText = btn.textContent;
    btn.textContent = loadingText;
    btn.disabled = true;
  } else {
    btn.textContent = btn.dataset.origText || btn.textContent;
    btn.disabled = false;
    delete btn.dataset.origText;
  }
}
