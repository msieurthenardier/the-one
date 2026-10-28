(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var TONE_CLASS = { muted: 'ui-notice--muted', danger: 'ui-notice--danger' };

  // App.ui.notice(opts) -> {el, set(body), destroy()}  (M31 F6 L04, DD4)
  //
  // A line of text in the transcript: a quiet note or a danger note. It is NOT a
  // live region (no role, no aria-live): the message log that holds it announces it.
  //
  // opts:
  //   tone     'muted' (default) or 'danger'; anything else throws
  //   body     a Node or text (set with textContent, never as HTML); none is allowed
  //   testid   placed on the root (supplied by the caller)
  // set(body) replaces the contents with a Node or text; set() or set(null) empties it.
  App.ui.notice = function (opts) {
    opts = opts || {};
    var tone = opts.tone || 'muted';
    if (!TONE_CLASS[tone]) throw new Error('App.ui.notice: unknown tone "' + tone + '"');
    var root = App.ui.util.el('div', { className: 'ui-notice ' + TONE_CLASS[tone] });
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    function fill(body) {
      root.textContent = '';
      if (body === undefined || body === null) return;
      if (body.nodeType) root.appendChild(body);
      else root.appendChild(document.createTextNode(String(body)));
    }
    fill(opts.body);

    return {
      el: root,
      set: function (body) { fill(body); },
      destroy: function () {}
    };
  };
})();
