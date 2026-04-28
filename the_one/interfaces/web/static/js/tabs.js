// App.tabs — canonical W3C ARIA tablist helper (F5 leg 03).
//
// Implements the manual-activation tab idiom: arrow keys move focus + visual
// highlight only; Enter/Space (or click) commits — fires onChange, swaps
// panel visibility via [hidden], updates aria-selected and roving tabindex.
//
// Signature:
//   App.tabs(tablistEl, panelsEl, opts)
//   - tablistEl: <div role="tablist"> containing <button role="tab">.
//   - panelsEl:  parent of <div role="tabpanel"> elements (helper finds them
//                via [role="tabpanel"]).
//   - opts: { onChange?, initial? }
//     - onChange(tabId): fires on activation (after panel swap + URL upgrade
//                        deferred to caller; this helper only manipulates
//                        DOM + ARIA state).
//     - initial: tab id to activate on mount.
//
// Returns: { activate(tabId), getActive() } for imperative control.
//
// Roving-tabindex contract (W3C ARIA Authoring Practices):
//   - Only the active tab carries tabindex="0"; the other tabs carry
//     tabindex="-1" (excluded from natural Tab order).
//   - Arrow-key navigation moves focus to the next tab via .focus() —
//     browsers honor programmatic focus on tabindex="-1" elements; only
//     the natural Tab order excludes them.
//   - Roving tabindex updates only on activation (Enter/Space/click),
//     NOT on arrow nav. This is the manual-activation contract — the URL
//     and aria-selected state stay stable while the user explores.
//
// Tab-id mapping: each <button role="tab"> has aria-controls="<panel-id>"
// pointing to a <div role="tabpanel" id="<panel-id>">. The helper uses
// aria-controls (or data-tab-id as a fallback) to identify which panel
// belongs to which tab.
(function (window) {
  'use strict';
  window.App = window.App || {};

  window.App.tabs = function (tablistEl, panelsEl, opts) {
    opts = opts || {};
    var onChange = opts.onChange || function () {};
    var initial = opts.initial;
    // F5 leg 04: optional onBeforeChange(tabId, commit) hook. When provided,
    // wraps BOTH the click and Enter/Space keyboard activation paths — the
    // consumer either calls commit() to proceed (synchronously or after async
    // user interaction) or does nothing to abort. Arrow-key navigation does
    // NOT route through onBeforeChange (only commits go through). When
    // onBeforeChange is omitted, behavior is unchanged from leg 03.
    var onBeforeChange = typeof opts.onBeforeChange === 'function' ? opts.onBeforeChange : null;

    var tabs = Array.prototype.slice.call(tablistEl.querySelectorAll('[role="tab"]'));
    var panels = Array.prototype.slice.call(panelsEl.querySelectorAll('[role="tabpanel"]'));
    var activeId = null;

    // Tab/panel id resolution: prefer the short data-tab-id (so callers can
    // pass logical ids like 'general' without leaking DOM-id details) and
    // fall back to aria-controls / id for tabs and panels respectively.
    function tabIdOf(t) {
      return t.dataset.tabId || t.getAttribute('aria-controls');
    }
    function panelIdOf(p) {
      return p.dataset.tabId || p.id;
    }

    function activate(tabId) {
      activeId = tabId;
      for (var i = 0; i < tabs.length; i++) {
        var t = tabs[i];
        var match = tabIdOf(t) === tabId;
        t.setAttribute('aria-selected', match ? 'true' : 'false');
        t.setAttribute('tabindex', match ? '0' : '-1');
      }
      for (var j = 0; j < panels.length; j++) {
        var p = panels[j];
        var pmatch = panelIdOf(p) === tabId;
        if (pmatch) p.removeAttribute('hidden');
        else p.setAttribute('hidden', '');
      }
      onChange(tabId);
    }

    function getActive() { return activeId; }

    function focusedIndex() {
      for (var i = 0; i < tabs.length; i++) {
        if (tabs[i] === document.activeElement) return i;
      }
      return -1;
    }

    tablistEl.addEventListener('keydown', function (e) {
      var idx = focusedIndex();
      if (idx === -1) return;
      var next = idx;
      if (e.key === 'ArrowLeft') {
        next = (idx - 1 + tabs.length) % tabs.length;
      } else if (e.key === 'ArrowRight') {
        next = (idx + 1) % tabs.length;
      } else if (e.key === 'Home') {
        next = 0;
      } else if (e.key === 'End') {
        next = tabs.length - 1;
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        var commitId = tabIdOf(tabs[idx]);
        if (commitId) {
          if (onBeforeChange) {
            onBeforeChange(commitId, function () { activate(commitId); });
          } else {
            activate(commitId);
          }
        }
        return;
      } else {
        return;
      }
      e.preventDefault();
      // Move DOM focus only — DO NOT update tabindex (roving tabindex updates
      // only on activation, not on arrow-key navigation). Browsers honor
      // .focus() on tabindex="-1" elements, so the user has explicit focus
      // even while non-active tabs remain excluded from natural Tab order.
      tabs[next].focus();
    });

    for (var k = 0; k < tabs.length; k++) {
      (function (tab) {
        tab.addEventListener('click', function () {
          var clickId = tabIdOf(tab);
          if (!clickId) return;
          if (onBeforeChange) {
            onBeforeChange(clickId, function () { activate(clickId); });
          } else {
            activate(clickId);
          }
        });
      })(tabs[k]);
    }

    if (initial) activate(initial);

    return { activate: activate, getActive: getActive };
  };
})(window);
