/**
 * toast.js — Non-blocking notification toasts.
 */

const container = document.getElementById("toast-container");

export function showToast(message, type = "info", duration = 4000) {
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast--${type}`;
  toast.innerHTML = `<span class="toast__message">${message}</span>`;
  container.appendChild(toast);

  const remove = () => {
    toast.classList.add("is-removing");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
  };

  const timer = setTimeout(remove, duration);
  toast.addEventListener("click", () => { clearTimeout(timer); remove(); });
}

// Listen to global toast events
document.addEventListener("DOMContentLoaded", () => {
  window.addEventListener("app:toast", (e) => {
    const { message, type, duration } = e.detail || {};
    showToast(message, type, duration);
  });
});

window.showToast = showToast;
export default showToast;
