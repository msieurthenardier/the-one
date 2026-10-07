// App.focusAfter - focus after an in-place editor action (M25 F6 L1b, flight DD2).
//
// An in-place Save, Test or edit-mode Cancel re-renders or disables the control the
// keyboard user just activated, which drops focus to <body>. This helper puts it back:
//
//   var t = App.focusAfter.begin(button);   // when the action STARTS, before any disable
//   ...request, re-render/patch...
//   App.focusAfter.restore(t, targetOrFn);  // AFTER the final mount; returns boolean
//
// restore() acts only when (a) t is non-null and recorded `hadFocus`, (b) t is still the
// latest, uncancelled token, and (c) focus is LOST (activeElement null/body/html, the
// token's own control, a disabled element, or a detached one). So it never steals focus
// from a control the user moved to meanwhile. The focus lands in a setTimeout(0), after
// nav.js's post-Continue setTimeout(focusMain). `target` is an element or a function
// resolved when the timer fires; a disabled or detached target is left alone.
//
// cancel() invalidates every token and the deferred one (call it from every editor
// teardown). defer(t, targetFn) parks one pending restore for an async create mount and
// flush() runs it once at the mount site's final render.
(function () {
  'use strict';
  window.App = window.App || {};

  var seq = 0;
  var latest = 0;
  var pending = null; // {t, target}

  function begin(control) {
    seq += 1;
    latest = seq;
    var active = document.activeElement;
    return {
      id: seq,
      control: control || null,
      hadFocus: !!(control && active === control),
    };
  }

  function focusLost(t) {
    var a = document.activeElement;
    if (!a || a === document.body || a === document.documentElement) return true;
    if (a === t.control) return true;
    if (a.disabled) return true;
    if (!a.isConnected) return true;
    return false;
  }

  function usable(el) {
    return !!(el && el.isConnected && !el.disabled && typeof el.focus === 'function');
  }

  function restore(t, target) {
    if (!t || !t.hadFocus || t.id !== latest) return false;
    if (!focusLost(t)) return false;
    setTimeout(function () {
      if (t.id !== latest) return;
      var el = typeof target === 'function' ? target() : target;
      if (!usable(el)) return;
      // Re-check at fire time: the user may have moved focus since.
      if (!focusLost(t)) return;
      try {
        el.focus({ preventScroll: true });
      } catch (e) {
        el.focus();
      }
      if (typeof el.scrollIntoView === 'function') {
        try {
          el.scrollIntoView({ block: 'nearest' });
        } catch (e2) {
          /* older engines: focus alone is enough */
        }
      }
    }, 0);
    return true;
  }

  function cancel() {
    latest = ++seq;
    pending = null;
  }

  function defer(t, targetFn) {
    pending = t ? { t: t, target: targetFn } : null;
  }

  function flush() {
    var p = pending;
    pending = null;
    if (!p) return false;
    return restore(p.t, p.target);
  }

  window.App.focusAfter = {
    begin: begin,
    restore: restore,
    cancel: cancel,
    defer: defer,
    flush: flush,
  };
})();
