// App.nav - the unified leave guard (M25 F2 L5, flight DD5).
//
// One guard for every way of leaving an open editor with unsaved work:
//   - per-area dirty SOURCES: registerSource(areaId, {isDirty, discard}). An area
//     keeps ONE source for the page's lifetime (re-registering replaces it).
//     `isDirty` is `dirty && editorOpen()`; `discard` is a TEARDOWN to "no item
//     open" (never a URL write, never a re-render from saved state).
//   - confirmLeave(ctx) -> Promise<boolean>: clean -> true with no dialog; dirty
//     -> ONE App.confirmDialog (Stay / Continue, Stay focused). Continue calls
//     every dirty source's discard() (each in try/catch) and resolves true; Stay
//     resolves false.
//   - one `beforeunload` listener (reload / close).
//   - a bubble-phase link interceptor: in-app `#` links go through the router.
//
// ctx: {opener, router, caller, target}. `router: true` is the router's adapter
// (router.js runGuard, which keeps its own synchronous clean fast path and its
// own `deciding` join). A non-router caller names itself in `caller`; repeated
// calls from the SAME caller while pending get the SAME promise. A different
// caller, or any router/non-router mix, while a decision is pending resolves
// Stay: joining would run both actions on Continue.
//
// Load order: nav.js loads right after router.js, BEFORE dialog.js and the ui/
// factories, so App.confirmDialog is looked up lazily; confirmLeave and
// isDirty are callable before router.start without throwing.
(function () {
  'use strict';
  window.App = window.App || {};

  var sources = {};
  var order = [];
  var pending = null; // {router, caller, promise}

  function registerSource(areaId, source) {
    if (!source || typeof source.isDirty !== 'function') return;
    if (!sources[areaId]) order.push(areaId);
    sources[areaId] = source;
  }

  function dirtySources() {
    var out = [];
    for (var i = 0; i < order.length; i++) {
      var src = sources[order[i]];
      var d = false;
      try { d = !!src.isDirty(); } catch (e) { d = false; }
      if (d) out.push(src);
    }
    return out;
  }

  function isDirty() { return dirtySources().length > 0; }

  // True while a NON-router decision is pending (the router adapter resolves
  // Stay instead of joining it).
  function isPending() { return !!(pending && !pending.router); }

  function focusMain() {
    var main = document.getElementById('main-content');
    // <main> hidden (a narrow window showing the list pane): focus the visible pane.
    if (main && !main.getClientRects().length && window.App.shellPane) {
      window.App.shellPane.focusVisible();
      return;
    }
    if (main && typeof main.focus === 'function') {
      try { main.focus(); } catch (e) { /* ignore */ }
    }
  }

  function confirmLeave(ctx) {
    ctx = ctx || {};
    var router = !!ctx.router;
    var caller = ctx.caller || null;
    if (pending) {
      if (!pending.router && !router && pending.caller === caller) return pending.promise;
      return Promise.resolve(false);
    }
    var dirty = dirtySources();
    if (!dirty.length) return Promise.resolve(true);
    var dlg = window.App.confirmDialog;
    if (typeof dlg !== 'function') return Promise.resolve(false);
    var entry = { router: router, caller: caller, promise: null };
    entry.promise = new Promise(function (resolvePromise) {
      // Registered BEFORE the dialog opens: a dialog that fails to open settles
      // through onCancel (Stay) synchronously, which must find and clear it.
      pending = entry;
      var active = document.activeElement;
      var opener = ctx.opener ||
        (active && active !== document.body && active !== document.documentElement
          ? active : document.getElementById('main-content'));
      try {
        dlg({
          opener: opener,
          onConfirm: function () {
            if (pending === entry) pending = null;
            for (var i = 0; i < dirty.length; i++) {
              try { dirty[i].discard(); } catch (e) { /* navigate anyway */ }
            }
            resolvePromise(true);
            // After the commit (the resolution chain is microtasks): the modal has
            // already restored focus to the opener and called onClose, so the new
            // view's <main> takes focus last.
            setTimeout(focusMain, 0);
          },
          onCancel: function () {
            if (pending === entry) pending = null;
            resolvePromise(false);
          }
        });
      } catch (err) {
        // The dialog could not open: Stay, with nothing left pending.
        if (pending === entry) pending = null;
        resolvePromise(false);
      }
    });
    return entry.promise;
  }

  // ── beforeunload (the only one) ─────────────────────────────────────────
  // A native leave prompt wins over an open leave dialog (accepted).
  window.addEventListener('beforeunload', function (e) {
    var d = false;
    try { d = isDirty(); } catch (err) { d = false; }
    if (d) {
      e.preventDefault();
      e.returnValue = '';
      return '';
    }
  });

  // ── Link interceptor ────────────────────────────────────────────────────
  // Bubble phase on document, so a target handler's preventDefault is visible.
  document.addEventListener('click', function (e) {
    if (e.defaultPrevented) return;
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var t = e.target;
    var a = t && typeof t.closest === 'function' ? t.closest('a[href^="#"]') : null;
    if (!a) return;
    if (a.getAttribute('target') || a.hasAttribute('download')) return;
    var href = a.getAttribute('href');
    var r = window.App.router ? window.App.router.resolve(href) : { kind: 'unknown' };
    if (r.kind === 'element') return; // native fragment behaviour (#main-content)
    e.preventDefault();
    if (r.kind === 'route') window.App.router.go(href, { opener: a });
    // unknown / empty / bare '#': swallowed, no history entry
  });

  window.App.nav = {
    registerSource: registerSource,
    isDirty: isDirty,
    isPending: isPending,
    confirmLeave: confirmLeave,
    // Read-only view for tests: [{areaId, dirty}].
    _sources: function () {
      var out = [];
      for (var i = 0; i < order.length; i++) {
        var d = false;
        try { d = !!sources[order[i]].isDirty(); } catch (e) { d = false; }
        out.push({ areaId: order[i], dirty: d });
      }
      return out;
    }
  };
})();
