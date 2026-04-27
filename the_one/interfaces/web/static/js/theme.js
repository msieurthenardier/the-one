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

    // renderToggle(container, options?) — mounts a theme-preference toggle
    // widget into `container`.  Supported options:
    //   options.variant   'full' (default) — Light/Dark/Auto radio-group
    //                     'compact'        — single cycling button (MVP text
    //                                        labels L/D/A; leg 02 may swap
    //                                        for Lucide sun/moon/monitor icons
    //                                        if it adds them to icons.js —
    //                                        the ARIA contract defined here
    //                                        stays unchanged regardless).
    //   options.labelledBy  (full only) — id of the heading element used as
    //                                     aria-labelledby on the radiogroup.
    //
    // Cleanup contract: if container._themeListenerCleanup is a function at
    // the start of a renderToggle call it is invoked to remove the prior
    // event listener before a new one is wired (handles SPA re-renders where
    // the same container element is reused).
    renderToggle: function (container, options) {
      if (!container) return;
      options = options || {};
      var variant = options.variant === 'compact' ? 'compact' : 'full';

      // Clean up any prior listener on this container (re-render safety).
      if (typeof container._themeListenerCleanup === 'function') {
        container._themeListenerCleanup();
        container._themeListenerCleanup = null;
      }

      var currentPref = getPreference();

      if (variant === 'full') {
        // ── Full variant ────────────────────────────────────────────────
        // Renders a WCAG-conformant radiogroup with Light / Dark / Auto
        // options.  Accessibility attributes preserved verbatim from the
        // original admin.js implementation (lifted in F3 leg 01).
        var labelledBy = options.labelledBy || '';
        var OPTS = [
          { value: 'light', label: 'Light' },
          { value: 'dark',  label: 'Dark'  },
          { value: 'auto',  label: 'Auto'  }
        ];

        // Set container role/aria (caller may have pre-set these in HTML).
        container.setAttribute('role', 'radiogroup');
        if (labelledBy) {
          container.setAttribute('aria-labelledby', labelledBy);
        }

        // Build the option buttons.
        container.innerHTML = '';
        for (var i = 0; i < OPTS.length; i++) {
          var o = OPTS[i];
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'admin-theme-option' + (currentPref === o.value ? ' active' : '');
          btn.setAttribute('role', 'radio');
          btn.setAttribute('aria-checked', String(currentPref === o.value));
          btn.setAttribute('tabindex', currentPref === o.value ? '0' : '-1');
          btn.setAttribute('data-theme-pref', o.value);
          btn.textContent = o.label;
          container.appendChild(btn);
        }

        // updateActiveOption — DOM-only; never calls App.theme.set (avoids
        // event loop: set → dispatch → subscriber → set → …).
        function updateActiveOption(pref) {
          var btns = container.querySelectorAll('.admin-theme-option');
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
          window.App.theme.set(pref); // dispatches THEME_EVENT after applying
          btn.focus();
        }

        container.addEventListener('click', function (e) {
          selectThemeOption(e.target.closest('.admin-theme-option'));
        });

        container.addEventListener('keydown', function (e) {
          if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' &&
              e.key !== 'ArrowUp'  && e.key !== 'ArrowDown') return;
          var btns = Array.prototype.slice.call(
            container.querySelectorAll('.admin-theme-option')
          );
          var idx = btns.indexOf(document.activeElement);
          if (idx === -1) return;
          e.preventDefault();
          var dir = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 : -1;
          var next = btns[(idx + dir + btns.length) % btns.length];
          selectThemeOption(next);
        });

        // Subscribe to cross-mount sync event.
        var fullListener = function (e) { updateActiveOption(e.detail.pref); };
        document.addEventListener(THEME_EVENT, fullListener);
        container._themeListenerCleanup = function () {
          document.removeEventListener(THEME_EVENT, fullListener);
        };

      } else {
        // ── Compact variant ─────────────────────────────────────────────
        // Single cycling button: Light → Dark → Auto → Light.
        // Displays the PREFERENCE (not the resolved mode) so "auto" is
        // visually distinct from a forced light/dark.
        //
        // Leg 02 may replace the letter labels (L/D/A) with Lucide icons
        // (sun/moon/monitor) if it adds them to icons.js.  The aria-label
        // contract defined here stays the same regardless of the swap.
        var CYCLE = ['light', 'dark', 'auto'];
        var LABELS = { light: 'Light', dark: 'Dark', auto: 'Auto' };
        var LETTERS = { light: 'L', dark: 'D', auto: 'A' };

        var compactBtn = document.createElement('button');
        compactBtn.type = 'button';
        compactBtn.className = 'theme-toggle-compact';
        compactBtn.setAttribute(
          'aria-label',
          'Toggle theme; current: ' + LABELS[currentPref]
        );
        compactBtn.textContent = LETTERS[currentPref];
        container.innerHTML = '';
        container.appendChild(compactBtn);

        function updateCompact(pref) {
          compactBtn.textContent = LETTERS[pref] || pref;
          compactBtn.setAttribute(
            'aria-label',
            'Toggle theme; current: ' + (LABELS[pref] || pref)
          );
        }

        compactBtn.addEventListener('click', function () {
          var pref = getPreference();
          var idx = CYCLE.indexOf(pref);
          var next = CYCLE[(idx + 1) % CYCLE.length];
          window.App.theme.set(next); // dispatches THEME_EVENT
        });

        var compactListener = function (e) { updateCompact(e.detail.pref); };
        document.addEventListener(THEME_EVENT, compactListener);
        container._themeListenerCleanup = function () {
          document.removeEventListener(THEME_EVENT, compactListener);
        };
      }
    }
  };
})();
