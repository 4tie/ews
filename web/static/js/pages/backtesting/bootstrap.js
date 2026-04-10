/**
 * bootstrap.js — Animated tab switching for the backtesting page.
 */

import { $$ } from "../../core/utils.js";

export function initTabs() {
  const tabBtns  = $$(".tab-btn");
  const tabPanes = $$(".tab-pane");
  const nav      = document.querySelector(".tabs__nav");

  function moveIndicator(activeBtn) {
    if (!nav || !activeBtn) return;
    const navRect = nav.getBoundingClientRect();
    const btnRect = activeBtn.getBoundingClientRect();
    const scrollLeft = nav.scrollLeft;
    nav.style.setProperty("--ind-left",  (btnRect.left - navRect.left + scrollLeft) + "px");
    nav.style.setProperty("--ind-width", btnRect.width + "px");
  }

  function switchTab(target) {
    tabBtns.forEach(b => b.classList.toggle("is-active", b.dataset.tab === target));
    tabPanes.forEach(p => p.classList.toggle("is-active", p.id === `tab-${target}`));
    const activeBtn = [...tabBtns].find(b => b.dataset.tab === target);
    moveIndicator(activeBtn);
  }

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // Set initial indicator position instantly (no slide-in on load)
  const initialActive = [...tabBtns].find(b => b.classList.contains("is-active"));
  if (initialActive) {
    requestAnimationFrame(() => {
      if (nav) nav.style.transition = "none";
      const pseudo = nav?.querySelector ? null : null; // ::after can't be queried
      // Temporarily disable the ::after transition via a class
      nav?.classList.add("tabs__nav--no-transition");
      moveIndicator(initialActive);
      requestAnimationFrame(() => nav?.classList.remove("tabs__nav--no-transition"));
    });
  }
}

document.addEventListener("DOMContentLoaded", initTabs);
