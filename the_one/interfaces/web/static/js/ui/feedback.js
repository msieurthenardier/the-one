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
    'mock',
    'ollama',
    'openai',
    'openai-compatible',
    'openrouter',
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

  // App.ui.emptyState(opts) -> HTMLDivElement.
  //   title (required), body, action (an element), icon (an App.icons name),
  //   headingLevel (1-6, default 3), size ('inline' | 'pane', default inline),
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
    var level = opts.headingLevel === undefined ? 3 : opts.headingLevel;
    if (typeof level !== 'number' || level < 1 || level > 6 || level % 1 !== 0) {
      throw new Error('App.ui.emptyState: headingLevel must be 1-6');
    }
    var util = App.ui.util;
    var children = [];
    if (opts.icon) children.push(util.el('span', { className: 'ui-empty-icon' }, [util.icon(opts.icon)]));
    children.push(util.el('h' + level, { className: 'ui-empty-title', text: opts.title }));
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
      root = util.el('div', { className: 'empty-state' }, children);
    }
    if (opts.role) root.setAttribute('role', opts.role);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    return root;
  };
})();
