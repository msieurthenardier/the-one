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
//                  the new one and notifies the listeners. The controller's single
//                  onSessionChange listener (syncTestHold) holds Test through the shell
//                  (M31 F5 L10); this module never touches a button
//   endSession(s)  called by a session as it finalizes or is cancelled; notifies the
//                  listeners (a destroyed mount notifies nobody and writes nothing)
//   sessionActive() whether a session is live
//   onSessionChange(fn)  fn(active) after every hold and release (Reset and Forget
//                  follow it)
//   onDestroy(fn)  registers a disposer run once by destroy (the field modules' destroy)
//   handles        the per-mount object the controller keeps its module handles on
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
    var listeners = [];
    var mount = { handles: {} };

    function notify() {
      var active = !!(session && !session.isDone());
      for (var i = 0; i < listeners.length; i++) listeners[i](active);
    }

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
      if (!dead) notify();
    };
    mount.endSession = function (s) {
      if (session !== s) return;
      if (!dead) notify();
    };
    mount.onSessionChange = function (fn) { listeners.push(fn); };
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
