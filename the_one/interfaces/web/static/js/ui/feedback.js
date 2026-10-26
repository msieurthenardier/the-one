(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // The .badge--<kind> modifiers in css/components.css. A unit test pins this
  // list against the selectors in static/css/*.css.
  var BADGE_KINDS = [
    'anthropic',
    'anthropic-plan',
    'anthropic-plan-token',
    'approved',
    'connectors',
    'dismissed',
    'execution',
    'filesystem',
    'local',
    'mock',
    'ollama',
    'openai',
    'openai-compatible',
    'openrouter',
    'remote',
    'time',
    'unknown',
    'web'
  ];

  // App.ui.badge(opts) -> HTMLSpanElement (class badge, plus badge--<kind>).
  //   text (required, set with textContent), kind (one of App.ui.badge.KINDS;
  //   omit for the neutral badge), title.
  //   The test id option is placed on the span itself (supplied by the caller).
  //   A badge never carries meaning by colour alone: the text is always shown.
  App.ui.badge = function (opts) {
    opts = opts || {};
    if (opts.text === undefined || opts.text === null || opts.text === '') {
      throw new Error('App.ui.badge: text is required');
    }
    if (opts.kind && BADGE_KINDS.indexOf(opts.kind) === -1) {
      throw new Error('App.ui.badge: unknown kind "' + opts.kind + '"');
    }
    var node = App.ui.util.el('span', {
      className: opts.kind ? 'badge badge--' + opts.kind : 'badge',
      text: String(opts.text)
    });
    if (opts.title) node.setAttribute('title', opts.title);
    if (opts.testid) node.setAttribute('data-testid', opts.testid);
    return node;
  };
  App.ui.badge.KINDS = BADGE_KINDS.slice();

  // App.ui.badge.dot(kind) -> HTMLSpanElement: the text-less, aria-hidden 8px disc
  // (the provider dot, a list row's `lead`). `kind` is a provider type slug: one of
  // KINDS, any other string maps to 'unknown', and null/undefined draws the hollow
  // "no provider" ring. The meaning is carried by the row's accessible name, never the colour.
  App.ui.badge.dot = function (kind) {
    var cls;
    if (kind === null || kind === undefined) {
      cls = 'badge badge-dot badge-dot--none';
    } else {
      cls = 'badge badge--' + (BADGE_KINDS.indexOf(kind) !== -1 ? kind : 'unknown') + ' badge-dot';
    }
    return App.ui.util.el('span', { className: cls, 'aria-hidden': 'true' });
  };

  // App.ui.emptyState(opts) -> HTMLDivElement.
  //   title (required), body, action (an element), icon (an App.icons name),
  //   headingLevel (1-6, default 3), titleTag ('p': the title is a paragraph, not a
  //   heading, for a panel that must not add an outline entry; default a heading),
  //   size ('inline' | 'pane', default inline),
  //   variant ('plain': the title reads as quiet running text, inheriting the
  //   container's size, weight and ink instead of the medium-weight primary title;
  //   inline size only; default none; 'flush': plain, and the root as well is a flush,
  //   left-aligned, body-sm line with a space-3 gap below instead of the centred padded
  //   block, for a "nothing here yet" line at the top of a list; default none),
  //   role (set on the root when given; listPane passes none, its own live region announces).
  //   The test id option is placed on the root element (supplied by the caller).
  //   inline: div.empty-state. pane: div.empty-canvas > div.empty-canvas-inner;
  //   the action gains .empty-canvas-cta (its own classes are kept).
  App.ui.emptyState = function (opts) {
    opts = opts || {};
    if (!opts.title) throw new Error('App.ui.emptyState: title is required');
    var size = opts.size || 'inline';
    if (size !== 'inline' && size !== 'pane') {
      throw new Error('App.ui.emptyState: unknown size "' + size + '"');
    }
    if (opts.variant !== undefined && opts.variant !== 'plain' && opts.variant !== 'flush') {
      throw new Error('App.ui.emptyState: unknown variant "' + opts.variant + '"');
    }
    var level = opts.headingLevel === undefined ? 3 : opts.headingLevel;
    if (typeof level !== 'number' || level < 1 || level > 6 || level % 1 !== 0) {
      throw new Error('App.ui.emptyState: headingLevel must be 1-6');
    }
    if (opts.titleTag !== undefined && opts.titleTag !== 'p') {
      throw new Error('App.ui.emptyState: titleTag must be "p"');
    }
    var util = App.ui.util;
    var children = [];
    if (opts.icon) children.push(util.el('span', { className: 'ui-empty-icon' }, [util.icon(opts.icon)]));
    children.push(util.el(opts.titleTag === 'p' ? 'p' : 'h' + level, { className: 'ui-empty-title', text: opts.title }));
    if (opts.body) children.push(util.el('p', { className: 'ui-empty-body', text: opts.body }));
    if (opts.action) {
      if (!opts.action.nodeType) throw new Error('App.ui.emptyState: action must be an element');
      if (size === 'pane') opts.action.classList.add('empty-canvas-cta');
      children.push(opts.action);
    }
    var root;
    if (size === 'pane') {
      root = util.el('div', { className: 'empty-canvas' }, [
        util.el('div', { className: 'empty-canvas-inner' }, children)
      ]);
    } else {
      root = util.el('div', {
        className: 'empty-state' + (opts.variant === 'plain' ? ' empty-state--plain'
          : opts.variant === 'flush' ? ' empty-state--plain empty-state--flush' : '')
      }, children);
    }
    if (opts.role) root.setAttribute('role', opts.role);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    return root;
  };

  // App.ui.flash(message, opts) -> HTMLDivElement (class app-flash, plus error).
  //   error: role=alert; otherwise role=status with aria-live=polite.
  //   container: where it is appended (default document.body).
  //   duration: the visible dwell in ms (default 5000, WCAG 2.2.1 reading time).
  //   It shows after 10ms (.visible) and is removed 300ms after the fade starts.
  App.ui.flash = function (message, opts) {
    opts = opts || {};
    var container = opts.container || document.body;
    var dwell = typeof opts.duration === 'number' ? opts.duration : 5000;
    var node = App.ui.util.el('div', {
      className: 'app-flash' + (opts.error ? ' error' : ''),
      role: opts.error ? 'alert' : 'status',
      'aria-live': opts.error ? null : 'polite',
      text: String(message)
    });
    container.appendChild(node);
    setTimeout(function () { if (node.isConnected) node.classList.add('visible'); }, 10);
    setTimeout(function () {
      node.classList.remove('visible');
      setTimeout(function () { if (node.isConnected) node.remove(); }, 300);
    }, dwell);
    return node;
  };

  var STATUS_STATES = ['success', 'warning', 'danger', 'idle', 'pending'];

  // App.ui.status(opts) -> { el, set(state, text, opts) }: the LED and the status line.
  //   state: success | warning | danger | idle | pending (pending shows the idle LED).
  //   text: the status words; ledLabel: the LED's name when there is no text.
  //   live: 'polite' (default; role=status on the line) or 'off'.
  //   role: 'status' (default) or 'alert' (the line is role=alert, for an error that
  //   must interrupt); ignored when live is 'off'.
  //   led: false draws no LED at all (the words alone; the state stays on data-state).
  //   The test id option is placed on the p.ui-status root (supplied by the caller);
  //   ledTestid is placed on the LED span (ignored with led:false; set() rewrites only
  //   the LED's class and aria attributes, so it persists).
  //   textTone: true colours the text with the danger or warning token for those states
  //   (root class ui-status--tone); other states and the default are unchanged.
  //   With text the LED is decorative (aria-hidden). Without text the LED is role=img
  //   named by ledLabel only when one is given (opts.ledLabel, or per call:
  //   set(state, text, {ledLabel})); with no label it stays aria-hidden, never an unnamed
  //   image. No glyphs: the state is the LED plus the words.
  App.ui.status = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var showLed = opts.led !== false;
    var led = util.el('span', {});
    var label = util.el('span', { className: 'ui-status-text' });
    var root = util.el('p', { className: 'ui-status' }, showLed ? [led, label] : [label]);
    if (opts.role !== undefined && opts.role !== 'status' && opts.role !== 'alert') {
      throw new Error('App.ui.status: unknown role "' + opts.role + '"');
    }
    if (opts.live !== 'off') root.setAttribute('role', opts.role || 'status');
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    if (opts.textTone) root.classList.add('ui-status--tone');
    if (showLed && opts.ledTestid) led.setAttribute('data-testid', opts.ledTestid);
    function set(state, text, callOpts) {
      if (STATUS_STATES.indexOf(state) === -1) {
        throw new Error('App.ui.status: unknown state "' + state + '"');
      }
      root.setAttribute('data-state', state);
      label.textContent = text ? String(text) : '';
      if (!showLed) return;
      led.className = 'indicator-led indicator-led--' + (state === 'pending' ? 'idle' : state);
      var ledLabel = (callOpts && callOpts.ledLabel) || opts.ledLabel;
      if (!text && ledLabel) {
        led.removeAttribute('aria-hidden');
        led.setAttribute('role', 'img');
        led.setAttribute('aria-label', ledLabel);
      } else {
        led.setAttribute('aria-hidden', 'true');
        led.removeAttribute('role');
        led.removeAttribute('aria-label');
      }
    }
    set(opts.state || 'idle', opts.text);
    return { el: root, set: set };
  };

  // App.ui.chip(opts) -> HTMLSpanElement (class chip), display only.
  //   label (required), tone: neutral (default) | danger | warning, size: omit | 'sm',
  //   title, dataset (a plain object copied to data-*).
  //   The test id option is placed on the span itself (supplied by the caller).
  App.ui.chip = function (opts) {
    opts = opts || {};
    if (opts.label === undefined || opts.label === null || opts.label === '') {
      throw new Error('App.ui.chip: label is required');
    }
    var tone = opts.tone || 'neutral';
    if (tone !== 'neutral' && tone !== 'danger' && tone !== 'warning') {
      throw new Error('App.ui.chip: unknown tone "' + tone + '"');
    }
    if (opts.size && opts.size !== 'sm') {
      throw new Error('App.ui.chip: unknown size "' + opts.size + '"');
    }
    var classes = ['chip'];
    if (tone === 'danger') classes.push('chip--danger');
    if (tone === 'warning') classes.push('chip--warning');
    if (opts.size === 'sm') classes.push('chip--sm');
    var node = App.ui.util.el('span', { className: classes.join(' '), text: String(opts.label) });
    if (opts.title) node.setAttribute('title', opts.title);
    App.ui.util.applyDataset(node, opts.dataset);
    if (opts.testid) node.setAttribute('data-testid', opts.testid);
    return node;
  };

  // App.ui.progress(opts) -> { el, bar, cancelButton, set(value, text), setCancelDisabled(bool) }.
  //   label: the accessible name. value: 0-1, or null for indeterminate. text: the
  //   words shown. onCancel: adds an icon-only cancel button named cancelLabel
  //   (default "Cancel"). Test ids: the testid option on the root, cancelTestid on
  //   the cancel button (both supplied by the caller).
  //   Structure: el is a plain div.ui-progress; role=progressbar (value, label, valuetext)
  //   sits on the inner div.ui-progress-track, and the words and the cancel button are
  //   its SIBLINGS, never its children (a progressbar's children are presentational, which
  //   would hide the button from assistive technology). cancelButton is null without onCancel.
  App.ui.progress = function (opts) {
    opts = opts || {};
    if (!opts.label) throw new Error('App.ui.progress: label is required');
    var util = App.ui.util;
    var fill = util.el('div', { className: 'ui-progress-fill' });
    var bar = util.el('div', {
      className: 'ui-progress-track',
      role: 'progressbar',
      'aria-label': opts.label,
      'aria-valuemin': '0',
      'aria-valuemax': '100'
    }, [fill]);
    var text = util.el('span', { className: 'ui-progress-text' });
    var kids = [bar, text];
    var cancel = null;
    if (typeof opts.onCancel === 'function') {
      cancel = util.el('button', {
        type: 'button',
        className: 'ui-progress-cancel',
        'aria-label': opts.cancelLabel || 'Cancel',
        onClick: opts.onCancel
      }, [App.ui.icon('x')]);
      if (opts.cancelTestid) cancel.setAttribute('data-testid', opts.cancelTestid);
      kids.push(cancel);
    }
    var root = util.el('div', { className: 'ui-progress' }, kids);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    function set(value, words) {
      if (value === null || value === undefined) {
        root.classList.add('ui-progress--indeterminate');
        bar.removeAttribute('aria-valuenow');
        fill.style.width = '';
      } else {
        var v = Math.max(0, Math.min(1, Number(value) || 0));
        root.classList.remove('ui-progress--indeterminate');
        bar.setAttribute('aria-valuenow', String(Math.round(v * 100)));
        fill.style.width = (v * 100) + '%';
      }
      if (words !== undefined && words !== null) {
        text.textContent = String(words);
        bar.setAttribute('aria-valuetext', String(words));
      }
    }
    set(opts.value, opts.text);
    return {
      el: root,
      bar: bar,
      cancelButton: cancel,
      set: set,
      setCancelDisabled: function (disabled) { if (cancel) cancel.disabled = !!disabled; }
    };
  };
})();
