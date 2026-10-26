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
//                  the new one and holds Test: disabled and labelled "Waiting for
//                  sign-in…" until the session ends (M31 F5 L08b, DD4)
//   endSession(s)  called by a session as it finalizes or is cancelled; gives Test its
//                  label and state back, also when the mount was destroyed meanwhile
//   sessionActive() whether a session is live
//   onSessionChange(fn)  fn(active) after every hold and release (Reset and Forget
//                  follow it)
//   onDestroy(fn)  registers a disposer run once by destroy (the field modules' destroy)
//   handles        the per-mount object the form helpers read (container, testBtn)
// A session is {cancel(), isDone()}; cancel() never closes the popup.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var WAITING_LABEL = 'Waiting for sign-in\u2026';

  // The button's visible text node(s), replaced; the icon element is kept.
  function labelOf(btn) {
    var text = '';
    for (var i = 0; i < btn.childNodes.length; i++) {
      if (btn.childNodes[i].nodeType === 3) text += btn.childNodes[i].nodeValue;
    }
    return text;
  }
  function setLabel(btn, text) {
    var nodes = [];
    for (var i = 0; i < btn.childNodes.length; i++) {
      if (btn.childNodes[i].nodeType === 3) nodes.push(btn.childNodes[i]);
    }
    for (var j = 1; j < nodes.length; j++) btn.removeChild(nodes[j]);
    if (nodes.length) nodes[0].nodeValue = text;
    else btn.appendChild(document.createTextNode(text));
  }

  function createMount() {
    var dead = false;
    var session = null;
    var disposers = [];
    var listeners = [];
    var heldLabel = null;
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
      var btn = mount.handles.testBtn;
      if (!dead && btn) {
        if (heldLabel === null) heldLabel = labelOf(btn);
        setLabel(btn, WAITING_LABEL);
        btn.disabled = true;
      }
      if (!dead) notify();
    };
    mount.endSession = function (s) {
      if (session !== s) return;
      var btn = mount.handles.testBtn;
      if (btn && heldLabel !== null) setLabel(btn, heldLabel);
      heldLabel = null;
      if (!dead && btn) btn.disabled = false;
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
