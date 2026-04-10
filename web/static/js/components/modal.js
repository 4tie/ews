/**
 * modal.js — Generic modal dialog controller.
 */

const overlay = document.getElementById("modal-overlay");
const modal   = document.getElementById("modal");
const titleEl = document.getElementById("modal-title");
const bodyEl  = document.getElementById("modal-body");
const footerEl = document.getElementById("modal-footer");
const closeBtn = document.getElementById("modal-close");

export function openModal({ title = "", body = "", footer = "" } = {}) {
  if (!overlay) return;
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
}

export function closeModal() {
  if (!overlay) return;
  overlay.hidden = true;
  document.body.style.overflow = "";
}

closeBtn?.addEventListener("click", closeModal);
overlay?.addEventListener("click", (e) => { if (e.target === overlay) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

window.openModal = openModal;
window.closeModal = closeModal;
