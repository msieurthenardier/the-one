(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  function validate(groups) {
    var seen = {};
    if (!Array.isArray(groups) || !groups.length) throw new Error('App.ui.navGroups: groups is required');
    for (var g = 0; g < groups.length; g++) {
      if (!groups[g].label) throw new Error('navGroups group ' + g + ': label required');
      if (!Array.isArray(groups[g].items)) throw new Error('navGroups group ' + groups[g].label + ': items required');
      for (var i = 0; i < groups[g].items.length; i++) {
        var item = groups[g].items[i];
        if (item.id === undefined || item.id === null || item.id === '') {
          throw new Error('navGroups item: id required');
        }
        if (!item.label) throw new Error('navGroups item ' + item.id + ': label required');
        if (!item.href) throw new Error('navGroups item ' + item.id + ': href required');
        if (Object.prototype.hasOwnProperty.call(seen, item.id)) {
          throw new Error('navGroups duplicate item id ' + item.id);
        }
        seen[item.id] = true;
      }
    }
  }

  // App.ui.navGroups(opts) -> controller {el, setSelected(id), destroy()}.
  // A grouped navigation of plain links (M25 F3 L1, DD6/DD10; reference spec
  // section 8.1): <nav aria-label> > h2 heading, then per group a caption and
  // a <ul> of <li><a href> items labelled by that caption.
  //   label (required): the landmark name
  //   heading: the h2 text (default: label)
  //   groups (required): [{label, items: [{id, label, href, and a per-item
  //   test id option placed on the link}]}]. A missing href or a duplicate id
  //   throws.
  //   selectedId: the id that starts as aria-current="page" (none when omitted)
  //   and the test id option on the nav root.
  // Items carry NO click handler and NO keyboard handling: they are plain
  // links in Tab order, so navigation, guarding and modifier-click passthrough
  // belong to the router and the app's link interceptor. The column's padding
  // and width belong to the host.
  App.ui.navGroups = function (opts) {
    opts = opts || {};
    if (!opts.label) throw new Error('App.ui.navGroups: label is required');
    validate(opts.groups);
    var util = App.ui.util;
    var nodes = {};
    var order = [];
    var selectedId = null;

    var nav = util.el('nav', { className: 'ui-nav-groups', 'aria-label': opts.label }, [
      util.el('h2', { className: 'ui-nav-groups-heading', text: opts.heading || opts.label })
    ]);
    if (opts.testid) nav.setAttribute('data-testid', opts.testid);

    for (var g = 0; g < opts.groups.length; g++) {
      var group = opts.groups[g];
      var capId = util.uid('ng-cap');
      var list = util.el('ul', { className: 'ui-nav-groups-list', 'aria-labelledby': capId });
      for (var i = 0; i < group.items.length; i++) {
        var item = group.items[i];
        var link = util.el('a', { className: 'ui-nav-groups-item', href: item.href, text: item.label });
        if (item.testid) link.setAttribute('data-testid', item.testid);
        nodes[item.id] = link;
        order.push(item.id);
        list.appendChild(util.el('li', null, [link]));
      }
      nav.appendChild(util.el('div', { className: 'ui-nav-groups-group' }, [
        util.el('div', { className: 'ui-nav-groups-caption', id: capId, text: group.label }),
        list
      ]));
    }

    // aria-current on exactly the selected item; an unknown id selects none.
    function setSelected(id) {
      selectedId = id !== undefined && id !== null && nodes[id] ? id : null;
      for (var k = 0; k < order.length; k++) {
        if (order[k] === selectedId) nodes[order[k]].setAttribute('aria-current', 'page');
        else nodes[order[k]].removeAttribute('aria-current');
      }
    }

    // Nothing is bound, so there is nothing to unbind; later calls are no-ops.
    function destroy() {
      nodes = {};
      order = [];
    }

    setSelected(opts.selectedId);
    return { el: nav, setSelected: setSelected, destroy: destroy };
  };
})();
