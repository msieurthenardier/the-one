(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.badge (every kind, taken from App.ui.badge.KINDS so demo and
  // library cannot drift) and App.ui.emptyState (with and without action).
  function render(host) {
    var d = App.admin.designLanguage.uiDemo;
    var ui = App.ui;

    d.demo(host, 'badge', function (pane) {
      var cells = [ui.badge({ text: 'neutral' })];
      var kinds = ui.badge.KINDS;
      for (var i = 0; i < kinds.length; i++) {
        cells.push(ui.badge({ text: kinds[i], kind: kinds[i] }));
      }
      pane.appendChild(d.row(cells));
    });
    d.demo(host, 'emptyState', function (pane) {
      pane.appendChild(ui.emptyState({
        title: 'Nothing here yet', body: 'Items you add will show up in this list.'
      }));
      pane.appendChild(ui.emptyState({
        title: 'No agents', body: 'Create an agent to get started.', icon: 'plus',
        action: ui.button({ variant: 'primary', label: 'Create agent' })
      }));
      pane.appendChild(ui.emptyState({ title: 'Title only', headingLevel: 4 }));
    });
  }

  window.App.admin.designLanguage.uiFeedbackSection = { render: render };
})();
