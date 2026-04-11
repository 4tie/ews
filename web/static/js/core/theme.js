/**
 * Theme initialization
 * Reads computed CSS custom properties from the document root
 * Makes them available globally for components and scripts
 */

(function initTheme() {
  const data = {
    rootStyles: {
      '--color-bg': getComputedStyle(document.documentElement).getPropertyValue('--color-bg'),
      '--color-text': getComputedStyle(document.documentElement).getPropertyValue('--color-text'),
      '--color-accent': getComputedStyle(document.documentElement).getPropertyValue('--color-accent') || getComputedStyle(document.documentElement).getPropertyValue('--color-primary'),
      '--color-border': getComputedStyle(document.documentElement).getPropertyValue('--color-border'),
      '--space-scrollbar': '8px'
    }
  };

  // Make theme data globally available
  window.__themeData = data;

  console.debug('Theme initialized:', data);
})();
