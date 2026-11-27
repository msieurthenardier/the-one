// App.shellPane - one pane at a time below 768px (sortie 21 L1, flight DD1).
//
// The router owns the operator's pane intent ('list' | 'detail', see
// App.router.paneIntent). This file stamps it on `.app-shell-row[data-pane]`
// (an attribute, never a class: the row's className is pinned), which the
// base-layer rules under `@media (max-width: 767.98px)` turn into "one pane
// visible"; at 768px and wider the stamp is inert and both panes show.
//
// It also keeps focus out of the hidden pane: after a pane change, and on the
// 768px media change, focus that is on <body> or inside the hidden pane moves
// to the visible pane. The classic max-width form (not range syntax) is used
// in CSS and JS alike: the range form needs WebKitGTK 2.40+ / Safari 16.4+.
//
// Loaded after router.js and nav.js; subscribes at script top level because
// App.router.start runs from app.js. DOM APIs only; appends nothing to <body>.
(function () {
  'use strict';
  window.App = window.App || {};

  var NARROW_QUERY = '(max-width: 767.98px)';
  var FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), ' +
    'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  var mql = typeof window.matchMedia === 'function' ? window.matchMedia(NARROW_QUERY) : null;

  function row() { return document.querySelector('.app-shell-row'); }
  function sidebar() { return document.getElementById('app-sidebar'); }
  function main() { return document.getElementById('main-content'); }
  function narrow() { return !!(mql && mql.matches); }
  function stamped() {
    var r = row();
    return r ? r.getAttribute('data-pane') : null;
  }

  // The pane the operator should see now: #app-sidebar or #main-content below
  // 768px; null at 768px and wider (both).
  function visiblePane() {
    if (!narrow()) return null;
    var pane = stamped();
    if (pane === 'list') return sidebar();
    if (pane === 'detail') return main();
    return null;
  }

  function hiddenPane() {
    var vis = visiblePane();
    if (!vis) return null;
    return vis === sidebar() ? main() : sidebar();
  }

  function focusIn(el) {
    if (!el || typeof el.focus !== 'function') return false;
    try { el.focus(); } catch (e) { return false; }
    return document.activeElement === el;
  }

  // list: the sidebar's current row, else its first focusable control;
  // detail: #main-content (tabindex -1).
  function focusVisible() {
    var vis = visiblePane();
    if (!vis) vis = stamped() === 'list' ? sidebar() : main();
    if (!vis) return false;
    if (vis.inert) return false; // covered by a fill drawer: leave focus alone
    if (vis === sidebar()) {
      var cur = vis.querySelector('[aria-current]');
      if (cur && focusIn(cur)) return true;
      var items = vis.querySelectorAll(FOCUSABLE);
      for (var i = 0; i < items.length; i++) {
        if (items[i].getClientRects().length && focusIn(items[i])) return true;
      }
      return false;
    }
    return focusIn(vis);
  }

  // Below 768px focus is never on <body> and never inside the hidden pane.
  function checkFocus() {
    var hidden = hiddenPane();
    if (!hidden) return;
    var active = document.activeElement;
    if (!active || active === document.body || active === document.documentElement || hidden.contains(active)) {
      return focusVisible();
    }
    return true;
  }

  function scheduleCheck() { setTimeout(checkFocus, 0); }

  // For a drawer closed by a navigation: the opener may be hidden or unmounted a little later (the
  // old area deactivates, a list renders), which drops focus to <body> after a first check. So
  // check on a short run of ticks (0, then 50ms apart, about 1s in all). No single hook covers
  // it: the opener's visibility changes in the area's own deactivation and in async list renders,
  // after every commit subscriber has run. The retry is safe because checkFocus acts only when
  // focus is on <body> or inside the hidden pane; it never moves focus from a visible element
  // (a rail link keeps it; tests: a rail click while each drawer covers).
  function scheduleCheckRetry(left) {
    setTimeout(function () {
      checkFocus();
      if (left > 0) scheduleCheckRetry(left - 1);
    }, left === 20 ? 0 : 50);
  }

  // Stamp the row from the router's intent. 'list' needs a shown aside (a
  // `sidebar: false` destination would otherwise show nothing).
  function restamp() {
    var intent = window.App.router && window.App.router.paneIntent && window.App.router.paneIntent();
    var r = row();
    if (!r || !intent) return;
    var aside = sidebar();
    var pane = intent === 'list' && aside && !aside.hidden ? 'list' : 'detail';
    if (r.getAttribute('data-pane') === pane) return;
    r.setAttribute('data-pane', pane);
    scheduleCheck();
  }

  if (window.App.router) {
    if (typeof window.App.router.onPaneIntentChange === 'function') {
      window.App.router.onPaneIntentChange(restamp);
    }
    // After every commit and sync: the aside's [hidden] state is final by then.
    if (typeof window.App.router.onRouteChange === 'function') {
      window.App.router.onRouteChange(restamp);
    }
  }

  if (mql) {
    var onMedia = function () { scheduleCheck(); };
    if (typeof mql.addEventListener === 'function') mql.addEventListener('change', onMedia);
    else if (typeof mql.addListener === 'function') mql.addListener(onMedia);
  }

  // ── Cover (sortie 21 L2, flight DD4) ──────────────────────────────────────
  // A drawer shown in `fill` mode covers both panes: they carry `inert` (the rail stays live).
  // Owners register with setCovered(owner, on, {el, close}); `inert` is removed only when no owner
  // covers. A commit not marked keepCovered (only GleepGlorp's fills are) closes every covering
  // drawer through its `close` callback.
  var covering = {}; // owner -> {el, close}

  function anyCover() {
    for (var k in covering) if (Object.prototype.hasOwnProperty.call(covering, k)) return covering[k];
    return null;
  }

  function inPane(node) {
    var s = sidebar();
    var m = main();
    return !!(node && ((s && s.contains(node)) || (m && m.contains(node))));
  }

  function setCovered(owner, on, opts) {
    opts = opts || {};
    if (on) {
      covering[owner] = { el: opts.el || null, close: opts.close || null };
    } else if (covering[owner]) {
      delete covering[owner];
      // Whatever closed it (a navigation may have unmounted the opener), keep focus off <body>.
      scheduleCheckRetry(20);
    }
    var cover = !!anyCover();
    var active = document.activeElement;
    var stranded = on && (!active || active === document.body || inPane(active));
    [sidebar(), main()].forEach(function (p) {
      if (!p) return;
      if (cover) p.setAttribute('inert', '');
      else p.removeAttribute('inert');
    });
    // Focus on <body> or in a pane about to be unreachable moves into the drawer (once shown).
    if (on && opts.el && !opts.el.hidden && (stranded || inPane(document.activeElement) || document.activeElement === document.body)) {
      focusIn(opts.el);
    }
  }

  if (window.App.router && typeof window.App.router.onCommit === 'function') {
    window.App.router.onCommit(function () {
      var d = typeof window.App.router.lastDecision === 'function' ? window.App.router.lastDecision() : null;
      if (d && d.keepCovered) return;      var owners = Object.keys(covering);
      if (!owners.length) return;
      owners.forEach(function (o) {
        var c = covering[o];
        if (c && typeof c.close === 'function') {
          try { c.close(); } catch (e) { /* a subscriber must never break a commit */ }
        }
      });
      // The drawer's opener may be unmounted by this very navigation: keep focus off <body>.
      scheduleCheckRetry(20);
    });
  }

  // Below 768px with <main> hidden, the skip link goes to the visible pane.
  var skip = document.querySelector('.skip-link');
  if (skip) {
    skip.addEventListener('click', function (e) {
      var m = main();
      var cover = anyCover();
      if (m && m.inert && cover && cover.el) {
        e.preventDefault();
        focusIn(cover.el);
        return;
      }
      if (narrow() && m && !m.getClientRects().length) {
        e.preventDefault();
        focusVisible();
      }
    });
  }

  window.App.shellPane = { visiblePane: visiblePane, focusVisible: focusVisible, setCovered: setCovered };
})();
