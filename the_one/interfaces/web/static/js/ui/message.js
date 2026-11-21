(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var ROLE_CLASS = {
    user: 'ui-message--user',
    assistant: 'ui-message--assistant',
    tool: 'ui-message--tool',
    system: 'ui-message--system'
  };
  var SIDE_CLASS = {
    you: 'ui-message-attribution--you',
    agent: 'ui-message-attribution--agent',
    peer: 'ui-message-attribution--peer'
  };
  var MODIFIER_CLASS = {
    api: 'ui-message--api',
    error: 'ui-message--error',
    peer: 'ui-message--peer',
    operatorOnly: 'ui-message--operator-only'
  };

  // App.ui.message(opts) -> {el, destroy()}  (M31 F6 L04, DD4)
  //
  // One transcript bubble: div.ui-message with a role class (the look), then optional
  // markers, then the body.
  //
  // opts:
  //   role              'user', 'assistant', 'tool' or 'system' (required; else it throws)
  //   source            'api' (a user message injected through the API: the saturated look)
  //   tone              'error' (a failed tool result)
  //   body              a Node (wins over text; a finished bubble's rendered content)
  //   text              plain text, set as a text node
  //   visibility        'operator': the bubble is not visible to peers. Marked for every role
  //                     except 'user' (the operator's own messages carry no marker); the
  //                     value is always recorded in data-visibility
  //   visibilityStyle   'label' (default: a [operator-only] span) or 'chip' (an App.ui.chip)
  //   visibilityLabel   the chip's text (default 'Operator only')
  //   marker            {label}: an App.ui.chip (size sm) on any role, after the operator
  //                     chip and before the peer label and the body; null/undefined is a
  //                     no-op, a missing/empty/non-string label throws
  //   peerName          a peer-attributed user bubble: left-aligned, and a visually hidden
  //                     "From {peer}: " first, for assistive technology
  //   testid            placed on the root (supplied by the caller)
  //
  // A bubble is built whole: the chat no longer streams into one (sortie 16, DD3; a turn's
  // pending text shows in the work group's preview and the reply lands whole).
  // destroy() only marks the handle spent; it never removes the node.
  App.ui.message = function (opts) {
    opts = opts || {};
    var role = opts.role;
    if (!ROLE_CLASS[role]) throw new Error('App.ui.message: unknown role "' + role + '"');
    if (opts.source !== undefined && opts.source !== null && opts.source !== 'api') {
      throw new Error('App.ui.message: unknown source "' + opts.source + '"');
    }
    if (opts.tone !== undefined && opts.tone !== null && opts.tone !== 'error') {
      throw new Error('App.ui.message: unknown tone "' + opts.tone + '"');
    }
    var marker = opts.marker;
    if (marker !== undefined && marker !== null &&
        (typeof marker !== 'object' || typeof marker.label !== 'string' || marker.label === '')) {
      throw new Error('App.ui.message: marker needs a non-empty string label');
    }
    var style = opts.visibilityStyle || 'label';
    if (style !== 'label' && style !== 'chip') {
      throw new Error('App.ui.message: unknown visibilityStyle "' + style + '"');
    }
    var util = App.ui.util;
    var operatorOnly = opts.visibility === 'operator' && role !== 'user';
    var cls = 'ui-message ' + ROLE_CLASS[role];
    if (opts.source === 'api') cls += ' ' + MODIFIER_CLASS.api;
    if (opts.tone === 'error') cls += ' ' + MODIFIER_CLASS.error;
    if (opts.peerName) cls += ' ' + MODIFIER_CLASS.peer;
    if (operatorOnly) cls += ' ' + MODIFIER_CLASS.operatorOnly;
    var root = util.el('div', { className: cls });
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    if (opts.visibility) root.setAttribute('data-visibility', String(opts.visibility));

    if (operatorOnly) {
      if (style === 'chip') {
        root.appendChild(util.el('span', { className: 'ui-message-operator-chip' }, [
          App.ui.chip({ label: opts.visibilityLabel || 'Operator only', size: 'sm' })
        ]));
      } else {
        root.appendChild(util.el('span', {
          className: 'ui-message-operator-label',
          text: opts.visibilityLabel || '[operator-only]'
        }));
      }
    }
    if (marker) {
      root.appendChild(util.el('span', { className: 'ui-message-marker-chip' }, [
        App.ui.chip({ label: marker.label, size: 'sm' })
      ]));
    }
    if (opts.peerName) {
      root.appendChild(util.el('span', {
        className: 'ui-message-peer-label visually-hidden',
        text: 'From ' + opts.peerName + ': '
      }));
    }
    if (opts.body && opts.body.nodeType) {
      root.appendChild(opts.body);
    } else if (opts.text !== undefined && opts.text !== null && opts.text !== '') {
      root.appendChild(document.createTextNode(String(opts.text)));
    }
    var spent = false;

    return {
      el: root,
      destroy: function () { spent = true; }
    };
  };

  // App.ui.message.visibilityStyles: the `visibilityStyle` values by name ({label, chip}), so a
  // consumer can name the style without spelling the owned class token as a string.
  App.ui.message.visibilityStyles = { label: 'label', chip: 'chip' };

  // App.ui.message.attribution(opts) -> {el, setTimeLabel(text), setCopy(text|null)}
  //
  // The small line under a bubble: "{name} · {time}" and, optionally, a Copy reply button.
  //   side        'you', 'agent' or 'peer' (required; sets the alignment)
  //   name        the leading text
  //   timeLabel   the time, already formatted by the caller; empty or missing renders no
  //               separator, no time span and no data-ts
  //   ts          the raw timestamp, kept as data-ts on the time span (for relabel)
  //   copyText    a string or a function returning one: adds App.ui.copyButton (icon only,
  //               "Copy reply"). It copies the STORED content the caller gives, never the
  //               bubble's rendered text
  //   liveEl      one shared role=status node the copy confirmation announces in (pass the
  //               transcript's single node so each reply does not carry its own)
  //   copyTestid  placed on the copy button
  // setTimeLabel(text) shows, changes or (empty) removes the time. setCopy(text) adds or
  // retargets the copy button; setCopy(null) removes the node it owns.
  App.ui.message.attribution = function (opts) {
    opts = opts || {};
    if (!SIDE_CLASS[opts.side]) throw new Error('App.ui.message.attribution: unknown side "' + opts.side + '"');
    var util = App.ui.util;
    var root = util.el('div', { className: 'ui-message-attribution ' + SIDE_CLASS[opts.side] });
    if (opts.name !== undefined && opts.name !== null) root.appendChild(document.createTextNode(String(opts.name)));
    var sepNode = null;
    var tsEl = null;
    var copyEl = null;
    var copyValue = null;

    function setTimeLabel(text) {
      var label = text === undefined || text === null ? '' : String(text);
      if (!label) {
        if (sepNode) { root.removeChild(sepNode); sepNode = null; }
        if (tsEl) { root.removeChild(tsEl); tsEl = null; }
        return;
      }
      if (!tsEl) {
        sepNode = document.createTextNode(' · ');
        tsEl = util.el('span', { className: 'ui-message-attribution-ts' });
        if (opts.ts !== undefined && opts.ts !== null) tsEl.setAttribute('data-ts', String(opts.ts));
        root.insertBefore(sepNode, copyEl);
        root.insertBefore(tsEl, copyEl);
      }
      tsEl.textContent = label;
    }
    function setCopy(text) {
      if (text === null || text === undefined) {
        if (copyEl) { root.removeChild(copyEl); copyEl = null; }
        copyValue = null;
        return;
      }
      copyValue = text;
      if (copyEl) return;
      var copy = App.ui.copyButton({
        iconOnly: true,
        label: 'Copy reply',
        size: 'sm',
        text: function () { return typeof copyValue === 'function' ? copyValue() : copyValue; },
        liveEl: opts.liveEl,
        testid: opts.copyTestid,
        className: 'ui-message-attribution-copy'
      });
      copyEl = copy.el;
      root.appendChild(copyEl);
    }
    setTimeLabel(opts.timeLabel);
    if (opts.copyText !== undefined && opts.copyText !== null) setCopy(opts.copyText);

    return { el: root, setTimeLabel: setTimeLabel, setCopy: setCopy };
  };

  // App.ui.message.context(opts) -> {el}  (M36 F3 L4)
  //
  // The quiet line above a user bubble that names the page the message was sent from, such as
  // "Library › MCP servers › New MCP server". It is a SIBLING of the bubble (the transcript
  // inserts it before the bubble), never a .ui-message, so message counts do not see it.
  //   text      the line (required: a missing or empty string throws); set with textContent
  //   testid    placed on the root (supplied by the caller; the transcript uses 'message-context')
  App.ui.message.context = function (opts) {
    opts = opts || {};
    if (typeof opts.text !== 'string' || !opts.text) {
      throw new Error('App.ui.message.context: text must be a non-empty string');
    }
    var root = App.ui.util.el('div', { className: 'ui-message-context' });
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    root.textContent = opts.text;
    return { el: root };
  };

  // App.ui.message.relabel(root, fn): re-words every attribution time under root. fn(ts)
  // gets the span's data-ts string and returns the new label; a null or undefined return
  // leaves that span as it is. Used when the operator's time zone changes.
  App.ui.message.relabel = function (root, fn) {
    if (!root || typeof fn !== 'function') return;
    var spans = root.querySelectorAll('.ui-message-attribution-ts[data-ts]');
    for (var i = 0; i < spans.length; i++) {
      var next = fn(spans[i].getAttribute('data-ts'));
      if (next !== null && next !== undefined) spans[i].textContent = String(next);
    }
  };
})();
