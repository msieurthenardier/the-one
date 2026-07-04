(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // M17 F3 tab vocabulary: selected = quiet 2px accent underline keyed off
  // aria-selected (the v2 L-bracket chamfer is retired); hover = fg shift.
  // Rendered via createElement per the innerHTML-sink freeze (M17 F1).
  //
  // Uses the canonical window.App.tabs(tablistEl, panelsEl, opts) signature
  // per tabs.js — matches existing consumers at agent-editor.js and
  // tools-grid.js. The helper wires keyboard nav (manual activation),
  // roving tabindex, and [role="tab"]/[role="tabpanel"] ARIA. There is NO
  // App.tabs.wire(...) method.
  var TABS = [
    { id: 'tab-1', label: 'Tab One',
      text: 'Panel one content. Arrow keys move focus; Enter/Space activates.' },
    { id: 'tab-2', label: 'Tab Two', text: 'Panel two content.' },
    { id: 'tab-3', label: 'Tab Three', text: 'Panel three content.' }
  ];

  function render(host) {
    var tablist = document.createElement('div');
    tablist.setAttribute('role', 'tablist');
    tablist.className = 'tablist';
    tablist.setAttribute('aria-label', 'Sample tabs');

    var panels = document.createElement('div');
    panels.className = 'tabpanels';

    for (var i = 0; i < TABS.length; i++) {
      var spec = TABS[i];
      var selected = i === 0;

      var tab = document.createElement('button');
      tab.type = 'button';
      tab.setAttribute('role', 'tab');
      tab.className = 'tab';
      tab.id = 'dl-tab-' + (i + 1);
      tab.setAttribute('data-tab-id', spec.id);
      tab.setAttribute('aria-controls', 'dl-panel-' + (i + 1));
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
      tab.tabIndex = selected ? 0 : -1;
      tab.textContent = spec.label;
      tablist.appendChild(tab);

      var panel = document.createElement('div');
      panel.setAttribute('role', 'tabpanel');
      panel.id = 'dl-panel-' + (i + 1);
      panel.setAttribute('data-tab-id', spec.id);
      panel.setAttribute('aria-labelledby', 'dl-tab-' + (i + 1));
      if (!selected) panel.hidden = true;
      panel.textContent = spec.text;
      panels.appendChild(panel);
    }

    host.appendChild(tablist);
    host.appendChild(panels);

    if (window.App && window.App.tabs) {
      window.App.tabs(tablist, panels, {
        initial: 'tab-1',
        onChange: function () { /* no-op for the gallery */ }
      });
    }
  }

  window.App.admin.designLanguage.tabsSection = { render: render };
})();
