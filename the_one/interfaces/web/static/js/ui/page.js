(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // Page-level controls (M31 F4 L04a, DD4/DD12): pageHeader and banner. Each
  // owns a NEW marker class (ui-page-header, ui-banner) and keeps emitting its
  // legacy classes (page-header/page-title, banner/banner-*); the legacy names
  // join the owned list at the handover leg.

  // App.ui.pageHeader({title, headingId, intro, introTestid (on the intro paragraph,
  //   M31 F4 L10), actions, testid, titleClassName})
  //   -> {el, titleEl, setTitle(text), setIntro(text|null), actionsEl}.
  //   div.page-header.ui-page-header holds div.ui-page-header-text (the
  //   h1.page-title, tabindex -1, plus an optional p.ui-page-header-intro) and,
  //   when `actions` (a node) is given, div.ui-page-header-actions. headingId
  //   is the h1's id; titleClassName is appended to the h1's classes.
  App.ui.pageHeader = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    if (!opts.title) throw new Error('App.ui.pageHeader: title is required');
    var titleAttrs = {
      className: 'page-title' + (opts.titleClassName ? ' ' + opts.titleClassName : ''),
      tabindex: '-1',
      text: opts.title
    };
    if (opts.headingId) titleAttrs.id = opts.headingId;
    var titleEl = util.el('h1', titleAttrs);
    var textCol = util.el('div', { className: 'ui-page-header-text' }, [titleEl]);
    var introEl = null;

    function setIntro(text) {
      if (text === null || text === undefined || text === '') {
        if (introEl && introEl.parentNode) introEl.parentNode.removeChild(introEl);
        introEl = null;
      } else if (introEl) {
        introEl.textContent = text;
      } else {
        introEl = util.el('p', { className: 'ui-page-header-intro', text: text });
        if (opts.introTestid) introEl.setAttribute('data-testid', opts.introTestid);
        textCol.appendChild(introEl);
      }
    }
    setIntro(opts.intro);

    var root = util.el('div', { className: 'page-header ui-page-header' }, [textCol]);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    var actionsEl = null;
    if (opts.actions) {
      actionsEl = util.el('div', { className: 'ui-page-header-actions' }, [opts.actions]);
      root.appendChild(actionsEl);
    }
    return {
      el: root,
      titleEl: titleEl,
      actionsEl: actionsEl,
      textEl: textCol,
      setTitle: function (text) {
        titleEl.textContent = text;
      },
      setIntro: setIntro
    };
  };

  // App.ui.banner({tone, text, children, role, live, className, actions, hidden,
  // testid}) -> {el, set(text), setChildren(nodes), show(), hide()}.
  //   tone: 'info' (default), 'warning' or 'error'. role: 'note' (default),
  //   'status' or 'alert'. live: 'alert' | 'status' implies the matching role
  //   (a contradicting role throws) and keeps the node rendered while empty,
  //   collapsed to zero height through [data-empty], so a screen reader
  //   announces the text when it arrives. Unknown values throw.
  //   div.banner.banner-{tone}.ui-banner (+ className): the text is the first
  //   text node, then the children, then div.ui-banner-actions (actions nodes).
  var TONES = { info: 1, warning: 1, error: 1 };
  var ROLES = { note: 1, status: 1, alert: 1 };
  App.ui.banner = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var tone = opts.tone === undefined ? 'info' : opts.tone;
    if (!TONES.hasOwnProperty(tone)) {
      throw new Error('App.ui.banner: unknown tone "' + tone + '"');
    }
    var role = opts.role === undefined ? null : opts.role;
    if (role !== null && !ROLES.hasOwnProperty(role)) {
      throw new Error('App.ui.banner: unknown role "' + role + '"');
    }
    var live = opts.live === undefined ? null : opts.live;
    if (live !== null && live !== 'alert' && live !== 'status') {
      throw new Error('App.ui.banner: unknown live "' + live + '"');
    }
    if (live !== null && role !== null && role !== live) {
      throw new Error('App.ui.banner: role "' + role + '" contradicts live "' + live + '"');
    }
    var finalRole = live || role || 'note';
    var root = util.el('div', {
      className: 'banner banner-' + tone + ' ui-banner' + (opts.className ? ' ' + opts.className : ''),
      role: finalRole
    });
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    var textNode = document.createTextNode(opts.text || '');
    root.appendChild(textNode);
    var kids = [];
    var actionsWrap = null;

    function refresh() {
      if (live && textNode.data === '' && !kids.length && !actionsWrap) {
        root.setAttribute('data-empty', '');
      } else {
        root.removeAttribute('data-empty');
      }
    }
    function setChildren(nodes) {
      var i;
      for (i = 0; i < kids.length; i++) {
        if (kids[i].parentNode === root) root.removeChild(kids[i]);
      }
      kids = [];
      nodes = nodes || [];
      var anchor = textNode.nextSibling;
      for (i = 0; i < nodes.length; i++) {
        if (!nodes[i]) continue;
        root.insertBefore(nodes[i], anchor);
        kids.push(nodes[i]);
      }
      refresh();
    }
    if (opts.children) setChildren(opts.children);
    if (opts.actions && opts.actions.length) {
      actionsWrap = util.el('div', { className: 'ui-banner-actions' }, opts.actions);
      root.appendChild(actionsWrap);
    }
    if (opts.hidden) root.hidden = true;
    refresh();
    return {
      el: root,
      set: function (text) {
        textNode.data = text === null || text === undefined ? '' : String(text);
        refresh();
      },
      setChildren: setChildren,
      show: function () {
        root.hidden = false;
      },
      hide: function () {
        root.hidden = true;
      }
    };
  };

  // App.ui.codeBlock({text, trim, maxHeight, label, className, testid})
  //   -> {el, set(text), refresh()} (M31 F4 L04b). A read-only
  //   pre.code-block.ui-code-block (+ className); the legacy code-block class
  //   keeps the look until the handover leg (DD12). text is set with textContent.
  //   trim (default false) strips leading and trailing BLANK lines only, never
  //   indentation. maxHeight: 'tall' (24rem) or 'short' (18rem), with vertical
  //   scrolling (any other value throws). When the content overflows, the node gets
  //   tabindex=0, role=region and an aria-label from `label` so a keyboard user can
  //   scroll it (WCAG 2.1.1); a block with no label gets none of the three and
  //   stays out of the tab order, so a scrollable block needs a label. Overflow is measured on
  //   construction (and one frame later, for a node attached afterwards), on every
  //   set(text) and on refresh(); there is no ResizeObserver.
  var HEIGHTS = { tall: 'ui-code-block--tall', short: 'ui-code-block--short' };
  function trimBlankLines(text) {
    return text.replace(/^(?:[ \t]*\r?\n)+/, '').replace(/(?:\r?\n[ \t]*)+$/, '');
  }
  App.ui.codeBlock = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    if (opts.maxHeight !== undefined && !HEIGHTS.hasOwnProperty(opts.maxHeight)) {
      throw new Error('App.ui.codeBlock: unknown maxHeight "' + opts.maxHeight + '"');
    }
    var cls = 'code-block ui-code-block' + (opts.maxHeight ? ' ' + HEIGHTS[opts.maxHeight] : '') +
      (opts.className ? ' ' + opts.className : '');
    var pre = util.el('pre', { className: cls });
    if (opts.testid) pre.setAttribute('data-testid', opts.testid);
    function refresh() {
      var over = pre.isConnected &&
        (pre.scrollHeight > pre.clientHeight + 1 || pre.scrollWidth > pre.clientWidth + 1);
      if (over && opts.label) {
        pre.setAttribute('tabindex', '0');
        pre.setAttribute('role', 'region');
        pre.setAttribute('aria-label', opts.label);
      } else {
        pre.removeAttribute('tabindex');
        pre.removeAttribute('role');
        pre.removeAttribute('aria-label');
      }
    }
    function set(text) {
      var s = text === null || text === undefined ? '' : String(text);
      pre.textContent = opts.trim ? trimBlankLines(s) : s;
      refresh();
    }
    set(opts.text);
    if (window.requestAnimationFrame) window.requestAnimationFrame(refresh);
    return { el: pre, set: set, refresh: refresh };
  };

  // App.ui.facts({rows: [{label, value, mono, testid, valueTestid}], testid})
  //   -> {el, set(rows)} (M31 F4 L04b). dl.ui-facts of div.ui-facts-row > dt + dd
  //   (the wrapper carries the row's testid, the dd its valueTestid). value is text
  //   (textContent), a node, or an array of nodes; mono makes the dd monospace
  //   (ui-facts-value--mono). set(rows) replaces every row.
  App.ui.facts = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var dl = util.el('dl', { className: 'ui-facts' });
    if (opts.testid) dl.setAttribute('data-testid', opts.testid);
    function build(row) {
      var dd = util.el('dd', { className: 'ui-facts-value' + (row.mono ? ' ui-facts-value--mono' : '') });
      var v = row.value;
      if (Array.isArray(v)) {
        for (var i = 0; i < v.length; i++) if (v[i]) dd.appendChild(v[i]);
      } else if (v && v.nodeType) {
        dd.appendChild(v);
      } else if (v !== null && v !== undefined) {
        dd.textContent = String(v);
      }
      if (row.valueTestid) dd.setAttribute('data-testid', row.valueTestid);
      var wrap = util.el('div', { className: 'ui-facts-row' }, [
        util.el('dt', { className: 'ui-facts-label', text: row.label }),
        dd
      ]);
      if (row.testid) wrap.setAttribute('data-testid', row.testid);
      return wrap;
    }
    function set(rows) {
      while (dl.firstChild) dl.removeChild(dl.firstChild);
      rows = rows || [];
      for (var i = 0; i < rows.length; i++) dl.appendChild(build(rows[i]));
    }
    set(opts.rows);
    return { el: dl, set: set };
  };
})();
