/**
 * bootstrap.js ? Animated tab switching for the backtesting page.
 */

import { $$ } from "../../core/utils.js";

function getTabState() {
  return {
    tabBtns: $$(".tab-btn"),
    tabPanes: $$(".tab-pane"),
    nav: document.querySelector(".tabs__nav"),
  };
}

function moveIndicator(nav, activeBtn) {
  if (!nav || !activeBtn) return;
  const navRect = nav.getBoundingClientRect();
  const btnRect = activeBtn.getBoundingClientRect();
  const scrollLeft = nav.scrollLeft;
  nav.style.setProperty("--ind-left", `${btnRect.left - navRect.left + scrollLeft}px`);
  nav.style.setProperty("--ind-width", `${btnRect.width}px`);
}

export function activateBacktestTab(target) {
  const normalized = String(target || "").trim();
  if (!normalized) return false;

  const { tabBtns, tabPanes, nav } = getTabState();
  if (!tabBtns.length || !tabPanes.length) return false;

  const activeBtn = tabBtns.find((button) => button.dataset.tab === normalized);
  if (!activeBtn) return false;

  tabBtns.forEach((button) => button.classList.toggle("is-active", button.dataset.tab === normalized));
  tabPanes.forEach((pane) => pane.classList.toggle("is-active", pane.id === `tab-${normalized}`));
  moveIndicator(nav, activeBtn);
  return true;
}

export function initTabs() {
  const { tabBtns, nav } = getTabState();
  if (!tabBtns.length) return;

  tabBtns.forEach((button) => {
    button.addEventListener("click", () => {
      activateBacktestTab(button.dataset.tab || "");
    });
  });

  const initialActive = tabBtns.find((button) => button.classList.contains("is-active"));
  if (initialActive) {
    requestAnimationFrame(() => {
      nav?.classList.add("tabs__nav--no-transition");
      activateBacktestTab(initialActive.dataset.tab || "");
      requestAnimationFrame(() => nav?.classList.remove("tabs__nav--no-transition"));
    });
  }
}

document.addEventListener("DOMContentLoaded", initTabs);
