/**
 * modal.js - Generic modal dialog controller.
 */

const overlay = document.getElementById("modal-overlay");
const modal = document.getElementById("modal");
const titleEl = document.getElementById("modal-title");
const bodyEl = document.getElementById("modal-body");
const footerEl = document.getElementById("modal-footer");
const closeBtn = document.getElementById("modal-close");
let activeOnClose = null;

export function openModal({ title = "", body = "", footer = "", onClose = null } = {}) {
  if (!overlay) return;
  activeOnClose = typeof onClose === "function" ? onClose : null;
  titleEl.textContent = title;
  if (typeof body === "string") {
    bodyEl.innerHTML = body;
  } else {
    bodyEl.innerHTML = "";
    bodyEl.appendChild(body);
  }
  footerEl.innerHTML = footer;
  overlay.hidden = false;
  document.body.style.overflow = "hidden";

  requestAnimationFrame(() => {
    const focusTarget = modal?.querySelector("[autofocus], textarea, input, button, select");
    focusTarget?.focus();
  });
}

export function closeModal() {
  if (!overlay || overlay.hidden) return;
  overlay.hidden = true;
  document.body.style.overflow = "";
  const onClose = activeOnClose;
  activeOnClose = null;
  if (typeof onClose === "function") {
    onClose();
  }
}

closeBtn?.addEventListener("click", closeModal);
overlay?.addEventListener("click", (e) => { if (e.target === overlay) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

window.openModal = openModal;
window.closeModal = closeModal;
