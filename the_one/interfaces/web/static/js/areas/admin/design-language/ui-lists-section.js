(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.listPane: groups, selection, filter, badges, count, density
  // regular and compact, and the empty state. Rows are buttons (onSelect), so
  // the page never navigates. App.ui.rail is demonstrated here too (links to
  // the in-page skip target, so the demo never routes).
  function noop() {}

  function items(prefix) {
    return [
      { id: prefix + '-a', label: 'Alpha', meta: 'First row', onSelect: noop,
        badges: [{ text: 'openai', kind: 'openai' }], count: 3 },
      { id: prefix + '-b', label: 'Beta', meta: 'Second row', onSelect: noop,
        badges: ['plain'], count: 12 },
      { id: prefix + '-c', label: 'Gamma', onSelect: noop }
    ];
  }

  function render(host) {
    var d = App.admin.designLanguage.uiDemo;
    var ui = App.ui;

    d.demo(host, 'listPane', function (pane, theme) {
      var regular = ui.listPane({
        title: 'Regular (' + theme + ')',
        filter: { label: 'Filter regular list', placeholder: 'Filter' },
        selectedId: 'r-b',
        items: items('r')
      });
      pane.appendChild(regular.el);

      var grouped = ui.listPane({
        title: 'Grouped (' + theme + ')',
        density: 'compact',
        selectedId: 'g-1',
        groups: [
          { label: 'Group one', items: [
            { id: 'g-1', label: 'Selected row', onSelect: noop, count: 2 },
            { id: 'g-2', label: 'Another row', onSelect: noop }
          ] },
          { label: 'Group two', items: [
            { id: 'g-3', label: 'Third row', onSelect: noop,
              badges: [{ text: 'approved', kind: 'approved' }] }
          ] }
        ]
      });
      pane.appendChild(grouped.el);

      var empty = ui.listPane({
        title: 'Empty (' + theme + ')',
        emptyText: 'No items yet',
        items: []
      });
      pane.appendChild(empty.el);
    });

    // App.ui.rail: a non-routing demo. Every href is the in-page skip target
    // (#main-content, which the link interceptor leaves to the browser), the
    // second item is shown current statically, and the brand image carries
    // its accessible name.
    d.demo(host, 'rail', function (pane, theme) {
      var rail = ui.rail({
        label: 'Rail demo (' + theme + ')',
        brand: { src: '/static/brand/topbar-icon-24.png', alt: 'GleepGlorp AI' },
        currentId: 'agents',
        items: [
          { id: 'chats', label: 'Chats', icon: 'chat', href: '#main-content' },
          { id: 'agents', label: 'Agents', icon: 'studio', href: '#main-content' },
          { id: 'library', label: 'Library', icon: 'database', href: '#main-content' },
          { id: 'settings', label: 'Settings', icon: 'admin', href: '#main-content' }
        ]
      });
      pane.appendChild(d.row([rail.el]));
    });
  }

  window.App.admin.designLanguage.uiListsSection = { render: render };
})();
