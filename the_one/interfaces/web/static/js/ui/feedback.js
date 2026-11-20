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
    'builtin',
    'local',
    'mock',
    'ollama',
    'openai',
    'openai-compatible',
    'openrouter',
    'remote',
    'unknown'
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

  // App.ui.badge.live(opts) -> { el, set({kind, text}) }: a badge whose kind and text change
  //   in place (the model badge on the new-chat state and in the agent drawer). opts: kind,
  //   text, title, testid (as App.ui.badge). Unlike App.ui.badge, empty or null text is not
  //   an error: the badge is hidden (the hidden attribute) until it has text. set() validates
  //   kind like App.ui.badge (unknown kind throws, an omitted kind is the neutral badge)
  //   and patches the class and the text in place; the node is never replaced.
  App.ui.badge.live = function (opts) {
    opts = opts || {};
    var node = App.ui.util.el('span', { className: 'badge' });
    if (opts.title) node.setAttribute('title', opts.title);
    if (opts.testid) node.setAttribute('data-testid', opts.testid);
    function set(next) {
      next = next || {};
      if (next.kind && BADGE_KINDS.indexOf(next.kind) === -1) {
        throw new Error('App.ui.badge.live: unknown kind "' + next.kind + '"');
      }
      var text = next.text === undefined || next.text === null ? '' : String(next.text);
      node.className = next.kind ? 'badge badge--' + next.kind : 'badge';
      node.textContent = text;
      node.hidden = text === '';
    }
    set({ kind: opts.kind, text: opts.text });
    return { el: node, set: set };
  };

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
  //   Always appended to one page region (App.ui.flash.region()), never to a caller's
  //   element, so it outlives the editor that raised it; while an App.ui.modal is open it
  //   goes inside that dialog (its top layer would hide the page region), and the modal
  //   moves it back out when it closes. The newest toast replaces the one showing.
  //   A `container` option is ignored.
  //   duration: the visible dwell in ms (default 5000, WCAG 2.2.1 reading time).
  //   It shows after 10ms (.visible) and is removed 300ms after the fade starts.
  var flashRegion = null;
  var showing = null;
  function flashRegionNode() {
    if (!flashRegion) flashRegion = App.ui.util.el('div', { className: 'app-flash-region' });
    if (!flashRegion.isConnected) document.body.appendChild(flashRegion);
    return flashRegion;
  }
  function dropToast(node) {
    if (!node) return;
    var timers = node._flashTimers || [];
    for (var i = 0; i < timers.length; i++) clearTimeout(timers[i]);
    node._flashTimers = [];
    node.remove();
  }
  App.ui.flash = function (message, opts) {
    opts = opts || {};
    var dwell = typeof opts.duration === 'number' ? opts.duration : 5000;
    var node = App.ui.util.el('div', {
      className: 'app-flash' + (opts.error ? ' error' : ''),
      role: opts.error ? 'alert' : 'status',
      'aria-live': opts.error ? null : 'polite',
      text: String(message)
    });
    dropToast(showing);
    showing = node;
    (App.ui.modal && App.ui.modal.top && App.ui.modal.top() || flashRegionNode()).appendChild(node);
    node._flashTimers = [setTimeout(function () {
      if (node.isConnected) node.classList.add('visible');
    }, 10), setTimeout(function () {
      node.classList.remove('visible');
      node._flashTimers.push(setTimeout(function () {
        if (node.isConnected) node.remove();
      }, 300));
    }, dwell)];
    return node;
  };
  // App.ui.flash.region() -> the page region (div.app-flash-region, a plain block: no
  // transform or containment, which would make a containing block for the fixed toast),
  // created on first use and re-appended to document.body when detached.
  App.ui.flash.region = flashRegionNode;

  // App.ui.noteFlag(opts) -> HTMLSpanElement (span.note-flag, role=img): the warning-triangle
  //   flag on an untrusted note or routine. opts.sources: the origins (an array of strings)
  //   named in the sentence, which is both the title and the accessible name. opts.subject:
  //   'note' (default), 'routine' (M33 F2 L5) or 'proposal' (M36 F2 L6, "made" for "written");
  //   any other value throws. The test id option
  //   is placed on the span (supplied by the caller).
  App.ui.noteFlag = function (opts) {
    opts = opts || {};
    var subject = opts.subject === undefined ? 'note' : opts.subject;
    if (subject !== 'note' && subject !== 'routine' && subject !== 'proposal') {
      throw new Error('App.ui.noteFlag: subject must be "note", "routine" or "proposal"');
    }
    var list = (opts.sources || []).join(', ');
    // A proposal is "made", a note or routine "written" (M36 F2 L6).
    var verb = subject === 'proposal' ? 'made' : 'written';
    var sentence = 'Check this ' + subject + ': it was ' + verb + ' after content that didn\'t come from you' +
      (list ? ' (' + list + ')' : '') + '. It may have been planted.';
    var flag = App.ui.util.el('span', {
      className: 'note-flag', role: 'img', title: sentence, 'aria-label': sentence
    }, [App.ui.util.icon('alert-triangle')]);
    if (opts.testid) flag.setAttribute('data-testid', opts.testid);
    return flag;
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
  //   lead: a Node placed before the label (the thumbnail). onRemove + removeLabel (required
  //   with onRemove) add a trailing ghost small icon-only x button named removeLabel
  //   (removeTestid on it); the chip stays a span and the button is its only control.
  //   labelHidden (M31 F6 L05a): the label is visually hidden (.visually-hidden) but still the
  //   chip's text, so a lead-only chip (a thumbnail) is named. truncate: one line with an
  //   ellipsis (the chip gets min-width 0 and max-width 100%, the label min-width 0).
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
    if (opts.truncate) classes.push('chip--truncate');
    if (typeof opts.onRemove === 'function' && !opts.removeLabel) {
      throw new Error('App.ui.chip: onRemove requires removeLabel');
    }
    var node = App.ui.util.el('span', { className: classes.join(' ') });
    if (opts.lead) {
      node.classList.add('chip--lead');
      var lead = App.ui.util.el('span', { className: 'chip-lead' });
      lead.appendChild(opts.lead);
      node.appendChild(lead);
      node.appendChild(App.ui.util.el('span', {
        className: 'chip-label' + (opts.labelHidden ? ' visually-hidden' : ''),
        text: String(opts.label)
      }));
    } else if (opts.labelHidden || opts.truncate) {
      node.appendChild(App.ui.util.el('span', {
        className: 'chip-label' + (opts.labelHidden ? ' visually-hidden' : ''),
        text: String(opts.label)
      }));
    } else {
      node.textContent = String(opts.label);
    }
    if (typeof opts.onRemove === 'function') {
      node.appendChild(App.ui.button({
        variant: 'ghost', size: 'sm', iconOnly: true, icon: 'x', ariaLabel: opts.removeLabel,
        className: 'chip-remove-btn', testid: opts.removeTestid,
        onClick: function () { opts.onRemove(); }
      }));
    }
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
