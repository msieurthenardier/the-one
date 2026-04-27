/* Theme switcher — F2 scaffold leg.
 *
 * Tri-state preference (Light / Dark / Auto) persisted in localStorage under
 * "theme-preference". When "auto" or unset, follows prefers-color-scheme live.
 *
 * Runs in <head> BEFORE any stylesheet load to avoid FOUC. Exposes API on
 * App.theme; creates window.App if it doesn't yet exist (theme.js loads
 * before app.js, and app.js mutates window.App in place to preserve this).
 */

(function () {
  'use strict';

  var STORAGE_KEY = 'theme-preference';
  var darkMedia = window.matchMedia('(prefers-color-scheme: dark)');
  var lightMedia = window.matchMedia('(prefers-color-scheme: light)');

  // localStorage may throw in private-browsing / Storage-disabled contexts.
  function safeGet() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }
  function safeSet(value) {
    try {
      localStorage.setItem(STORAGE_KEY, value);
    } catch (e) { /* no-op — degrade to non-persistent */ }
  }
  function safeRemove() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) { /* no-op */ }
  }

  function getPreference() {
    var pref = safeGet();
    if (pref === 'dark' || pref === 'light' || pref === 'auto') return pref;
    return 'auto';
  }

  function resolve(pref) {
    if (pref === 'dark' || pref === 'light') return pref;
    // 'auto': follow OS if it has a preference; else default to dark.
    if (darkMedia.matches) return 'dark';
    if (lightMedia.matches) return 'light';
    return 'dark'; // no OS preference — our canonical default
  }

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  function reapply() {
    apply(resolve(getPreference()));
  }

  // Synchronous initial application — runs before render.
  apply(resolve(getPreference()));

  // Live OS-preference response when in auto mode (listen on BOTH queries).
  function onMediaChange() {
    if (getPreference() === 'auto') reapply();
  }
  darkMedia.addEventListener('change', onMediaChange);
  lightMedia.addEventListener('change', onMediaChange);

  // Public API (App.theme).
  window.App = window.App || {};
  window.App.theme = {
    get: function () { return getPreference(); },
    resolved: function () {
      return document.documentElement.getAttribute('data-theme');
    },
    set: function (pref) {
      if (pref !== 'dark' && pref !== 'light' && pref !== 'auto') {
        throw new Error('Invalid theme preference: ' + pref);
      }
      if (pref === 'auto') {
        safeRemove();
      } else {
        safeSet(pref);
      }
      reapply();
    }
  };
})();
