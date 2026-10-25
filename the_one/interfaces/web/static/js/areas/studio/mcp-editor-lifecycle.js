// App.studio.mcpEditor.lifecycle — the MCP source editor's per-mount lifecycle
// (M31 F5 L03, DD4).
//
// createMount() returns the mount context one renderMcpSourceEditor call owns:
//   alive()        false once the mount was destroyed
//   ifAlive(fn)    fn wrapped so a continuation that lands after destroy is a no-op
//   destroy()      idempotent; marks the mount dead and cancels its consent session.
//                  It does NOT call App.focusAfter.cancel() (global: it would wipe
//                  the create -> edit restore the glue flushes); it aborts no request
//   setSession(s)  one consent session per mount: cancels the previous one, stores
//                  the new one and disables Test until the session ends
//   endSession(s)  called by a session as it finalizes or is cancelled; re-enables Test
//   sessionActive() whether a session is live
//   onDestroy(fn)  registers a disposer run once by destroy (the field modules' destroy)
//   handles        the per-mount object the form helpers read (container, testBtn)
// A session is {cancel(), isDone()}; cancel() never closes the popup.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  function createMount() {
    var dead = false;
    var session = null;
    var disposers = [];
    var mount = { handles: {} };

    mount.alive = function () { return !dead; };
    mount.ifAlive = function (fn) {
      return function () {
        if (dead) return undefined;
        return fn.apply(this, arguments);
      };
    };
    mount.sessionActive = function () { return !!(session && !session.isDone()); };
    mount.setSession = function (s) {
      var previous = session;
      session = s;
      if (previous && previous !== s) previous.cancel();
      if (!dead && mount.handles.testBtn) mount.handles.testBtn.disabled = true;
    };
    mount.endSession = function (s) {
      if (session !== s) return;
      if (!dead && mount.handles.testBtn) mount.handles.testBtn.disabled = false;
    };
    mount.onDestroy = function (fn) { disposers.push(fn); };
    mount.destroy = function () {
      if (dead) return;
      dead = true;
      if (session) session.cancel();
      var list = disposers;
      disposers = [];
      for (var i = 0; i < list.length; i++) list[i]();
    };
    return mount;
  }

  window.App.studio.mcpEditor.lifecycle = { createMount: createMount };
})();
