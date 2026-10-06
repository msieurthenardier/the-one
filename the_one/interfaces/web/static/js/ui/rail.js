(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var ITEM_SELECTOR = 'a.ui-rail-item';

  function validate(items) {
    var seen = {};
    if (!Array.isArray(items) || !items.length) throw new Error('App.ui.rail: items is required');
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      if (item.id === undefined || item.id === null || item.id === '') {
        throw new Error('rail item: id required');
      }
      if (!item.label) throw new Error('rail item ' + item.id + ': label required');
      if (!item.icon) throw new Error('rail item ' + item.id + ': icon required');
      if (Object.prototype.hasOwnProperty.call(seen, item.id)) {
        throw new Error('rail duplicate item id ' + item.id);
      }
      seen[item.id] = true;
    }
  }

  function validateFooter(footer) {
    if (footer === undefined || footer === null) return;
    if (!Array.isArray(footer)) throw new Error('App.ui.rail: footer must be an array of nodes');
    for (var i = 0; i < footer.length; i++) {
      if (!footer[i] || !footer[i].nodeType) throw new Error('App.ui.rail: footer item ' + i + ' is not a node');
    }
  }

  // App.ui.rail(opts) -> controller {el, setCurrent(id), setHref(id, href), destroy()}.
  // The workbench rail (M25 F2 L6, DD7): a <nav aria-label="Main"> holding an
  // optional brand mark and one link per destination.
  //   items (required): [{id, label, icon (an App.icons key), href, and a
  //   per-item test id option placed on the link}]
  //   currentId: the id that starts as aria-current="page" (none when omitted)
  //   brand: {src, alt} - a 24px image shown first, named by alt
  //   label: the landmark name (default "Main"; a demo passes its own so the
  //   page never holds two landmarks with one name)
  //   footer: an array of Nodes (M25 F4 L7, DD9, DD14): the bottom action
  //   slot, a .ui-rail-footer pinned to the bottom of the rail (margin-top:
  //   auto), holding the nodes in order. The caller builds them, handlers
  //   included (the shell's Jump to button); the rail binds nothing on them.
  //   They are not .ui-rail-item, so each focusable one is its own Tab stop,
  //   outside the items' roving ArrowUp/ArrowDown. An icon-only button there
  //   is a 44px square. setCurrent and setHref never touch the footer.
  // Items are plain <a> links with NO click handler: navigation, guarding and
  // modifier-click passthrough belong to the app's link interceptor. The rail
  // never reads App.router; the shell feeds it hrefs through setHref. It keeps
  // a single tab stop (the current item, else the first) and moves it with
  // ArrowUp/ArrowDown/Home/End, clamped at the ends.
  App.ui.rail = function (opts) {
    opts = opts || {};
    validate(opts.items);
    validateFooter(opts.footer);
    var util = App.ui.util;
    var nodes = {};
    var order = [];
    var currentId = null;

    var nav = util.el('nav', { className: 'ui-rail', 'aria-label': opts.label || 'Main' });
    if (opts.brand && opts.brand.src) {
      nav.appendChild(util.el('img', {
        className: 'ui-rail-brand',
        src: opts.brand.src,
        alt: opts.brand.alt || '',
        width: 24,
        height: 24
      }));
    }

    for (var i = 0; i < opts.items.length; i++) {
      var item = opts.items[i];
      var link = util.el('a', { className: 'ui-rail-item', href: item.href || '#' }, [
        util.el('span', { className: 'ui-rail-icon' }, [util.icon(item.icon)]),
        util.el('span', { className: 'ui-rail-label', text: item.label })
      ]);
      if (item.testid) link.setAttribute('data-testid', item.testid);
      nodes[item.id] = link;
      order.push(item.id);
      nav.appendChild(link);
    }

    if (opts.footer && opts.footer.length) {
      nav.appendChild(util.el('div', { className: 'ui-rail-footer' }, opts.footer));
    }

    var unbind = util.rovingFocus(nav, ITEM_SELECTOR);

    // aria-current on the current item, and the single tab stop with it
    // (rovingFocus only rewrites tabindex on a keydown).
    function apply() {
      var stop = currentId !== null && nodes[currentId] ? currentId : order[0];
      for (var k = 0; k < order.length; k++) {
        var node = nodes[order[k]];
        if (order[k] === currentId) node.setAttribute('aria-current', 'page');
        else node.removeAttribute('aria-current');
        node.setAttribute('tabindex', order[k] === stop ? '0' : '-1');
      }
    }

    function setCurrent(id) {
      currentId = id !== undefined && id !== null && nodes[id] ? id : null;
      apply();
    }

    function setHref(id, href) {
      if (!nodes[id]) throw new Error('App.ui.rail: unknown item ' + id);
      nodes[id].setAttribute('href', href);
    }

    function destroy() {
      unbind();
    }

    setCurrent(opts.currentId);
    return { el: nav, setCurrent: setCurrent, setHref: setHref, destroy: destroy };
  };
})();
