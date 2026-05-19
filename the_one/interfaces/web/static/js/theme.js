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

  // Event channel for multi-mount toggle sync.
  var THEME_EVENT = 'theme-preference-changed';

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
      // Notify all renderToggle instances so they sync without polling.
      document.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: { pref: pref } }));
    },

    // renderToggle(container, options?) — mounts a Light/Dark/Auto radiogroup
    // into `container`. options.labelledBy is the id of the heading element
    // used as aria-labelledby on the radiogroup.
    //
    // Cleanup contract: if container._themeListenerCleanup is a function at
    // the start of a renderToggle call it is invoked to remove the prior
    // event listener before a new one is wired (handles SPA re-renders where
    // the same container element is reused).
    renderToggle: function (container, options) {
      if (!container) return;
      options = options || {};

      if (typeof container._themeListenerCleanup === 'function') {
        container._themeListenerCleanup();
        container._themeListenerCleanup = null;
      }

      var currentPref = getPreference();
      var labelledBy = options.labelledBy || '';
      var OPTS = [
        { value: 'light', label: 'Light' },
        { value: 'dark',  label: 'Dark'  },
        { value: 'auto',  label: 'Auto'  }
      ];

      container.setAttribute('role', 'radiogroup');
      if (labelledBy) {
        container.setAttribute('aria-labelledby', labelledBy);
      }

      container.innerHTML = '';
      var seg = document.createElement('div');
      seg.className = 'seg';
      for (var i = 0; i < OPTS.length; i++) {
        var o = OPTS[i];
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'seg-btn' + (currentPref === o.value ? ' active' : '');
        btn.setAttribute('role', 'radio');
        btn.setAttribute('aria-checked', String(currentPref === o.value));
        btn.setAttribute('tabindex', currentPref === o.value ? '0' : '-1');
        btn.setAttribute('data-theme-pref', o.value);
        btn.textContent = o.label;
        seg.appendChild(btn);
      }
      container.appendChild(seg);

      // DOM-only; never calls App.theme.set (avoids event loop:
      // set → dispatch → subscriber → set → …).
      function updateActiveOption(pref) {
        var btns = container.querySelectorAll('.seg-btn');
        for (var j = 0; j < btns.length; j++) {
          var isActive = btns[j].getAttribute('data-theme-pref') === pref;
          btns[j].classList.toggle('active', isActive);
          btns[j].setAttribute('aria-checked', String(isActive));
          btns[j].setAttribute('tabindex', isActive ? '0' : '-1');
        }
      }

      function selectThemeOption(btn) {
        if (!btn) return;
        var pref = btn.getAttribute('data-theme-pref');
        window.App.theme.set(pref);
        btn.focus();
      }

      container.addEventListener('click', function (e) {
        selectThemeOption(e.target.closest('.seg-btn'));
      });

      container.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' &&
            e.key !== 'ArrowUp'  && e.key !== 'ArrowDown') return;
        var btns = Array.prototype.slice.call(
          container.querySelectorAll('.seg-btn')
        );
        var idx = btns.indexOf(document.activeElement);
        if (idx === -1) return;
        e.preventDefault();
        var dir = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : -1;
        var next = btns[(idx + dir + btns.length) % btns.length];
        selectThemeOption(next);
      });

      var listener = function (e) { updateActiveOption(e.detail.pref); };
      document.addEventListener(THEME_EVENT, listener);
      container._themeListenerCleanup = function () {
        document.removeEventListener(THEME_EVENT, listener);
      };
    }
  };
})();
