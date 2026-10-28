(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var DEFAULT_LABEL = 'Tool activity';
  var CHEVRONS = ['css', 'icon'];
  var COUNT_STYLES = ['span', 'dot'];

  function itemsName(label, n) {
    return label + ', ' + n + ' ' + (n === 1 ? 'item' : 'items');
  }

  // Builds the handle over a trace root. Nothing is stored apart from the DOM: the
  // label is read from data-trace-label, the count style from the root's classes, and
  // count() from the body's children, so a handle re-wrapped by find() cannot drift.
  function wrap(root) {
    var details = root.firstChild;
    var summary = details.firstChild;
    var body = details.lastChild;
    var label = root.getAttribute('data-trace-label') || DEFAULT_LABEL;
    var dot = root.classList.contains('ui-trace--count-dot');
    var labelEl = summary.querySelector('.ui-trace-label');
    var countEl = summary.querySelector('.ui-trace-count');
    var gone = false;

    function refresh() {
      var n = body.children.length;
      if (dot) labelEl.textContent = label + ' · ' + n;
      else if (countEl) countEl.textContent = String(n);
      summary.setAttribute('aria-label', itemsName(label, n));
    }
    return {
      el: root,
      append: function (node) {
        if (gone || !node) return;
        body.appendChild(node);
        refresh();
      },
      count: function () { return body.children.length; },
      destroy: function () { gone = true; }
    };
  }

  // App.ui.trace(opts) -> {el, append(node), count(), destroy()}  (M31 F6 L04, DD4)
  //
  // The per-turn "Tool activity" disclosure: a native <details> in div.ui-trace, its
  // summary the label and a count, its body the appended nodes (tool messages).
  //
  // opts:
  //   id          data-parent-msg-id on the root (the parent message id)
  //   label       the summary text (default 'Tool activity')
  //   chevron     'css' (default: the CSS triangle) or 'icon' (a chevron icon node)
  //   countStyle  'span' (default: a separate count after the label) or 'dot' (the label
  //               reads "Tool activity · 4" and there is no count node)
  //   testid      placed on the root (supplied by the caller)
  //
  // The summary's accessible name is "{label}, N items" either way (the visible count is
  // aria-hidden). append(node) adds to the body and updates the count and that name;
  // count() derives from the body's children. destroy() only marks the handle spent: it
  // never removes content.
  //
  // Why not App.ui.disclosure: its summary is named by aria-labelledby over its text and
  // meta nodes, which cannot give this summary the exact name "Tool activity, N items",
  // and its look (proportional text, bordered card) is not this mono, left-ruled voice.
  App.ui.trace = function (opts) {
    opts = opts || {};
    var chevron = opts.chevron || 'css';
    var countStyle = opts.countStyle || 'span';
    if (CHEVRONS.indexOf(chevron) === -1) throw new Error('App.ui.trace: unknown chevron "' + chevron + '"');
    if (COUNT_STYLES.indexOf(countStyle) === -1) {
      throw new Error('App.ui.trace: unknown countStyle "' + countStyle + '"');
    }
    var util = App.ui.util;
    var label = opts.label === undefined || opts.label === null ? DEFAULT_LABEL : String(opts.label);
    var dot = countStyle === 'dot';
    var kids = [];
    if (chevron === 'icon') kids.push(util.el('span', { className: 'ui-trace-chevron' }, [util.icon('chevron-right')]));
    kids.push(util.el('span', { className: 'ui-trace-label', text: dot ? label + ' · 0' : label }));
    if (!dot) kids.push(util.el('span', { className: 'ui-trace-count', 'aria-hidden': 'true', text: '0' }));
    var summary = util.el('summary', { className: 'ui-trace-toggle', 'aria-label': itemsName(label, 0) }, kids);
    var body = util.el('div', { className: 'ui-trace-body' });
    var details = util.el('details', { className: 'ui-trace-details' }, [summary, body]);
    var cls = 'ui-trace';
    if (chevron === 'icon') cls += ' ui-trace--icon-chevron';
    if (dot) cls += ' ui-trace--count-dot';
    var root = util.el('div', { className: cls, 'data-trace-label': label }, [details]);
    if (opts.id !== undefined && opts.id !== null) root.setAttribute('data-parent-msg-id', String(opts.id));
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    return wrap(root);
  };

  // App.ui.trace.find(root, id) -> a handle or null. Finds the .ui-trace under root whose
  // data-parent-msg-id is id and re-wraps it (a node built by an earlier handle, after a
  // reconnect replay). The thinking disclosure also carries data-parent-msg-id, so the
  // lookup is scoped to .ui-trace.
  App.ui.trace.find = function (root, id) {
    if (!root || id === undefined || id === null) return null;
    var nodes = root.querySelectorAll('.ui-trace');
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].getAttribute('data-parent-msg-id') === String(id)) return wrap(nodes[i]);
    }
    return null;
  };

  // App.ui.trace.thinking(opts) -> {el, destroy()}: the collapsed extended-thinking
  // disclosure, a native <details> that is not part of a trace.
  //   label (default 'Thinking'), body (text; none or empty is fine), parentId (sets
  //   data-parent-msg-id when given), testid (on the <details>).
  App.ui.trace.thinking = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var label = opts.label === undefined || opts.label === null ? 'Thinking' : String(opts.label);
    var text = opts.body === undefined || opts.body === null ? '' : String(opts.body);
    var details = util.el('details', { className: 'ui-trace-thinking' }, [
      util.el('summary', { className: 'ui-trace-thinking-toggle', text: label }),
      util.el('div', { className: 'ui-trace-thinking-body', text: text })
    ]);
    if (opts.parentId !== undefined && opts.parentId !== null) {
      details.setAttribute('data-parent-msg-id', String(opts.parentId));
    }
    if (opts.testid) details.setAttribute('data-testid', opts.testid);
    return { el: details, destroy: function () {} };
  };
})();
