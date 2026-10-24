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

  // ── Desktop shell signal (M25 F5 L2) ───────────────────────────────────
  // Inside the desktop webview only, tell the shell the resolved theme so the
  // native title bar follows (POST /api/window/chrome). Gate: WebView2 has
  // window.chrome.webview from document start; any pywebview backend has
  // window.pywebview once it injects (the pywebviewready listener below). A
  // plain browser tab never posts, so it cannot recolour the desktop window.
  // Dedup against the last theme sent OK; one POST in flight with later
  // changes coalesced to the latest; a failed post is retried once (after 2s,
  // or on the next apply()), then left. Nothing is ever shown to the user.
  var chromeSent = null;
  var chromeWanted = null;
  var chromeInFlight = false;
  var chromeFailTheme = null;
  var chromeFailures = 0;

  // The one desktop-webview check, shared as App.desktop.isWebview() (sortie 04
  // DD3). theme.js loads first and creates window.App; later scripts extend it
  // in place. Chat's sign-in is the only other caller (it skips its about:blank
  // pre-open in the webview, where window.open hands the URL to the system browser).
  window.App = window.App || {};
  window.App.desktop = window.App.desktop || {};
  window.App.desktop.isWebview = function () {
    return !!((window.chrome && window.chrome.webview) || window.pywebview);
  };

  function isDesktopWebview() {
    return window.App.desktop.isWebview();
  }

  function chromePump() {
    if (chromeInFlight || chromeWanted === null || chromeWanted === chromeSent) return;
    if (chromeWanted === chromeFailTheme && chromeFailures >= 2) return;
    var theme = chromeWanted;
    chromeInFlight = true;
    var ok = false;
    try {
      fetch('/api/window/chrome', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ theme: theme })
      }).then(function (r) {
        ok = !!(r && r.ok);
      }, function () {
        ok = false;
      }).then(function () {
        chromeInFlight = false;
        if (ok) {
          chromeSent = theme;
          chromeFailTheme = null;
          chromeFailures = 0;
        } else {
          if (chromeFailTheme !== theme) { chromeFailTheme = theme; chromeFailures = 0; }
          chromeFailures += 1;
          if (chromeFailures < 2) setTimeout(chromePump, 2000);
        }
        chromePump();
      });
    } catch (e) {
      chromeInFlight = false;
    }
  }

  function notifyShell(theme) {
    if (!isDesktopWebview()) return;
    if (theme !== 'light' && theme !== 'dark') return;
    if (theme !== chromeFailTheme) chromeFailures = 0;
    chromeWanted = theme;
    chromePump();
  }

  window.addEventListener('pywebviewready', function () {
    notifyShell(document.documentElement.getAttribute('data-theme'));
  });

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    notifyShell(theme);
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

  // Event channel for multi-mount toggle sync.
  var THEME_EVENT = 'theme-preference-changed';

  // Cross-tab theme sync (M17 F2 L3): reapply when ANOTHER tab writes or
  // removes the stored preference. `storage` events never fire in the
  // originating tab, so no same-tab echo guard is needed. Read the EVENT's
  // newValue — never re-read localStorage (a re-read races a subsequent
  // write; the event carries the value this notification is about).
  // Key removed (newValue === null) means the other tab chose auto;
  // garbage values degrade to auto via resolve()'s fallthrough.
  window.addEventListener('storage', function (e) {
    if (e.key !== STORAGE_KEY) return;
    var pref = e.newValue === null ? 'auto' : e.newValue;
    apply(resolve(pref));
    // Sync any toggle mounted in THIS tab (checked state), same channel
    // as set(). Normalize so the toggle never receives a garbage pref.
    var normalized = (pref === 'dark' || pref === 'light') ? pref : 'auto';
    document.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { pref: normalized } }));
  });

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
      // Notify mounted theme pickers (the Appearance page's radio group) so they sync
      // without polling.
      document.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { pref: pref } }));
    }
  };
})();
