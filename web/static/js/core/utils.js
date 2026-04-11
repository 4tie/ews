/**
 * utils.js — Core DOM utilities and helpers.
 */

/**
 * Query selector wrapper that returns array of elements.
 * @param {string} selector - CSS selector
 * @returns {Element[]} Array of matching elements
 */
export function $$(selector) {
  return Array.from(document.querySelectorAll(selector));
}

/**
 * Query single element.
 * @param {string} selector - CSS selector
 * @returns {Element|null} First matching element or null
 */
export function $(selector) {
  return document.querySelector(selector);
}

/**
 * Add event listener to multiple elements.
 * @param {Element[]} elements - Array of elements
 * @param {string} event - Event name
 * @param {Function} handler - Event handler
 */
export function onAll(elements, event, handler) {
  elements.forEach(el => el?.addEventListener(event, handler));
}

/**
 * Set multiple attributes on an element.
 * @param {Element} el - Element to modify
 * @param {Object} attrs - Attributes to set
 */
export function setAttrs(el, attrs) {
  if (!el) return;
  Object.entries(attrs).forEach(([key, value]) => {
    if (value === null || value === undefined) {
      el.removeAttribute(key);
    } else {
      el.setAttribute(key, value);
    }
  });
}

/**
 * Add classes to element.
 * @param {Element} el - Element to modify
 * @param {...string} classes - Class names to add
 */
export function addClass(el, ...classes) {
  if (!el) return;
  el.classList.add(...classes.filter(Boolean));
}

/**
 * Remove classes from element.
 * @param {Element} el - Element to modify
 * @param {...string} classes - Class names to remove
 */
export function removeClass(el, ...classes) {
  if (!el) return;
  el.classList.remove(...classes.filter(Boolean));
}

/**
 * Toggle class on element.
 * @param {Element} el - Element to modify
 * @param {string} className - Class name to toggle
 * @param {boolean} force - Optional force add/remove
 */
export function toggleClass(el, className, force) {
  if (!el) return;
  el.classList.toggle(className, force);
}

/**
 * Check if element has class.
 * @param {Element} el - Element to check
 * @param {string} className - Class name
 * @returns {boolean}
 */
export function hasClass(el, className) {
  return el?.classList.contains(className) ?? false;
}

/**
 * Set element text content.
 * @param {Element} el - Element to modify
 * @param {string} text - Text content
 */
export function setText(el, text) {
  if (el) el.textContent = text;
}

/**
 * Set element HTML content.
 * @param {Element} el - Element to modify
 * @param {string} html - HTML content
 */
export function setHTML(el, html) {
  if (el) el.innerHTML = html;
}

/**
 * Show element.
 * @param {Element} el - Element to show
 */
export function show(el) {
  if (el) el.style.display = "";
}

/**
 * Hide element.
 * @param {Element} el - Element to hide
 */
export function hide(el) {
  if (el) el.style.display = "none";
}

/**
 * Toggle element visibility.
 * @param {Element} el - Element to toggle
 * @param {boolean} force - Optional force show/hide
 */
export function toggleVisibility(el, force) {
  if (!el) return;
  if (force === true) {
    show(el);
  } else if (force === false) {
    hide(el);
  } else {
    el.style.display === "none" ? show(el) : hide(el);
  }
}

/**
 * Enable/disable element.
 * @param {Element} el - Element to modify
 * @param {boolean} enabled - Enable or disable
 */
export function setEnabled(el, enabled) {
  if (!el) return;
  if (enabled) {
    el.removeAttribute("disabled");
  } else {
    el.setAttribute("disabled", "disabled");
  }
}

/**
 * Debounce function calls.
 * @param {Function} fn - Function to debounce
 * @param {number} delay - Delay in milliseconds
 * @returns {Function} Debounced function
 */
export function debounce(fn, delay = 300) {
  let timeoutId;
  return function(...args) {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

/**
 * Throttle function calls.
 * @param {Function} fn - Function to throttle
 * @param {number} delay - Delay in milliseconds
 * @returns {Function} Throttled function
 */
export function throttle(fn, delay = 300) {
  let lastCall = 0;
  return function(...args) {
    const now = Date.now();
    if (now - lastCall >= delay) {
      lastCall = now;
      fn(...args);
    }
  };
}
