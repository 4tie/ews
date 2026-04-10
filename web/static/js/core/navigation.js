/**
 * navigation.js — Animated page transitions and element entrance animations.
 */

const TRANSITION_DURATION = 180;

function init() {
  createOverlay();
  interceptLinks();
  scheduleEntranceAnimations();
}

// ── Transition overlay ───────────────────────────────────────────
function createOverlay() {
  if (document.getElementById("page-transition")) return;
  const el = document.createElement("div");
  el.id = "page-transition";
  document.body.appendChild(el);
}

function fadeOut(url) {
  const overlay = document.getElementById("page-transition");
  if (!overlay) { window.location.href = url; return; }
  overlay.classList.add("is-leaving");
  setTimeout(() => { window.location.href = url; }, TRANSITION_DURATION);
}

// ── Link interception ────────────────────────────────────────────
function interceptLinks() {
  document.addEventListener("click", (e) => {
    const link = e.target.closest("a[href]");
    if (!link) return;
    const href = link.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("http") || href.startsWith("mailto")) return;
    if (link.target === "_blank") return;
    if (e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    fadeOut(href);
  });
}

// ── Entrance animations (IntersectionObserver) ───────────────────
function scheduleEntranceAnimations() {
  const targets = document.querySelectorAll("[data-animate]");
  if (!targets.length) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        const el = entry.target;
        const delay = Number(el.dataset.animateDelay ?? i * 60);
        el.style.animationDelay = delay + "ms";
        el.classList.add("is-visible");
        observer.unobserve(el);
      }
    });
  }, { threshold: 0.08 });

  targets.forEach(el => observer.observe(el));
}

document.addEventListener("DOMContentLoaded", init);
