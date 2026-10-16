(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};
  App.ui.util = App.ui.util || {};

  // App.ui.util - the control library's shared helpers (M25 F1 L2, DD1/DD4/DD5).
  //
  // Rules for everything under static/js/ui/:
  //   - ES5 only (no class, let/const or arrow functions); IIFE per file.
  //   - No HTML strings and no HTML-string sinks: nodes are built with el()
  //     and SVG icons are parsed with DOMParser (DD4).
  //   - Touch no app.js globals (App.router, App.config, ...): the disk
  //     harness loads only icons.js before this directory.
  //   - Composites install no persistent document-level listener (DD1).

  var uidCounter = 0;

  // el(tag, attrs, children) - DOM builder.
  //   attrs: className, text (textContent), dataset (object), on<event>
  //   (function, bound with addEventListener), everything else through
  //   setAttribute. null/undefined/false attribute values are skipped and
  //   true sets an empty attribute.
  //   children: array of strings (text nodes), nodes, or null (skipped).
  App.ui.util.el = function (tag, attrs, children) {
    var node = document.createElement(tag);
    var key;
    attrs = attrs || {};
    for (key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      var value = attrs[key];
      if (value === null || value === undefined || value === false) continue;
      if (key === 'className') {
        node.className = value;
      } else if (key === 'text') {
        node.textContent = value;
      } else if (key === 'dataset') {
        var dk;
        for (dk in value) {
          if (Object.prototype.hasOwnProperty.call(value, dk)) node.dataset[dk] = value[dk];
        }
      } else if (key.slice(0, 2) === 'on' && typeof value === 'function') {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else {
        node.setAttribute(key, value === true ? '' : String(value));
      }
    }
    if (children) {
      for (var i = 0; i < children.length; i++) {
        var child = children[i];
        if (child === null || child === undefined || child === false) continue;
        if (typeof child === 'string' || typeof child === 'number') {
          node.appendChild(document.createTextNode(String(child)));
        } else {
          node.appendChild(child);
        }
      }
    }
    return node;
  };

  // applyDataset(node, dataset) - copies a plain object onto node.dataset. A
  // `testid` key is ignored: the test id option owns data-testid (M31 F1 L4).
  App.ui.util.applyDataset = function (node, dataset) {
    if (!dataset) return;
    var key;
    for (key in dataset) {
      if (!Object.prototype.hasOwnProperty.call(dataset, key) || key === 'testid') continue;
      node.dataset[key] = dataset[key];
    }
  };

  // uid(prefix) - a monotonic, page-unique id: ui-<prefix>-<n>.
  App.ui.util.uid = function (prefix) {
    uidCounter += 1;
    return 'ui-' + (prefix || 'id') + '-' + uidCounter;
  };

  // buildIcon(name, who) - an SVGElement parsed from App.icons[name] with
  // DOMParser and imported into the document. Throws on an unknown name or a
  // parse failure (App.icon only warns and returns an empty string). The node
  // is hidden from assistive technology and not focusable.
  function buildIcon(name, who) {
    var source = window.App.icons && window.App.icons[name];
    if (!source) throw new Error(who + ': unknown icon "' + name + '"');
    var doc = new DOMParser().parseFromString(source, 'image/svg+xml');
    var root = doc && doc.documentElement;
    // A failed parse yields a parser-error document (root element varies by
    // engine: some nest the error inside an svg root), so check both.
    if (!root || root.nodeName !== 'svg' || root.getElementsByTagName('parsererror').length) {
      throw new Error(who + ': icon "' + name + '" did not parse as svg');
    }
    var svg = document.importNode(root, true);
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    return svg;
  }

  // App.ui.icon(name, opts) - the icon control (M31 F1 L2, DD6). Returns an
  // aria-hidden, non-focusable SVG node carrying the owned class `ui-icon`
  // (16px). opts.size 'sm' adds `ui-icon--sm` (14px); opts.className is
  // appended. Throws on an unknown name.
  App.ui.icon = function (name, opts) {
    opts = opts || {};
    var svg = buildIcon(name, 'App.ui.icon');
    var cls = 'ui-icon' + (opts.size === 'sm' ? ' ui-icon--sm' : '');
    if (opts.className) cls += ' ' + opts.className;
    svg.setAttribute('class', cls);
    return svg;
  };

  // util.icon(name) - the unsized form the library's own callers use: the same
  // node as App.ui.icon without the size classes, so a host's own `svg` rule
  // keeps sizing it. Shares App.ui.icon's builder.
  App.ui.util.icon = function (name) {
    return buildIcon(name, 'App.ui.util.icon');
  };

  // rovingFocus(container, itemSelector, opts) - roving-tabindex keyboard
  // handling bound on the container only (one keydown listener on it, none on
  // the document). Items are queried at event time because rows re-render.
  //   Handles ArrowUp, ArrowDown, Home, End (plus ArrowLeft/ArrowRight when
  //   opts.horizontal). Clamps at the ends unless opts.wrap is true.
  //   Never handles Enter or Space, so links keep native navigation and
  //   ctrl-click. Events with ctrl/alt/meta held are ignored.
  // Returns a function that unbinds the listener.
  App.ui.util.rovingFocus = function (container, itemSelector, opts) {
    opts = opts || {};
    var prevKey = opts.horizontal ? 'ArrowLeft' : null;
    var nextKey = opts.horizontal ? 'ArrowRight' : null;

    function onKeydown(e) {
      if (e.defaultPrevented || e.ctrlKey || e.altKey || e.metaKey) return;
      var key = e.key;
      var isPrev = key === 'ArrowUp' || key === prevKey;
      var isNext = key === 'ArrowDown' || key === nextKey;
      if (!isPrev && !isNext && key !== 'Home' && key !== 'End') return;
      var items = Array.prototype.slice.call(container.querySelectorAll(itemSelector));
      if (!items.length) return;
      var current = e.target && e.target.closest ? e.target.closest(itemSelector) : null;
      var idx = items.indexOf(current);
      if (idx === -1) return;
      var target = idx;
      if (key === 'Home') {
        target = 0;
      } else if (key === 'End') {
        target = items.length - 1;
      } else if (isNext) {
        target = idx + 1;
        if (target >= items.length) target = opts.wrap ? 0 : items.length - 1;
      } else {
        target = idx - 1;
        if (target < 0) target = opts.wrap ? items.length - 1 : 0;
      }
      e.preventDefault();
      for (var i = 0; i < items.length; i++) {
        items[i].setAttribute('tabindex', i === target ? '0' : '-1');
      }
      items[target].focus();
    }

    container.addEventListener('keydown', onKeydown);
    return function unbind() {
      container.removeEventListener('keydown', onKeydown);
    };
  };
})();
