(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.checkbox (unchecked, checked, indeterminate, disabled) and
  // App.ui.toggle (off, on, disabled).
  function render(host) {
    var d = App.admin.designLanguage.uiDemo;
    var ui = App.ui;

    d.demo(host, 'checkbox', function (pane) {
      pane.appendChild(ui.checkbox({ label: 'Unchecked' }).el);
      pane.appendChild(ui.checkbox({ label: 'Checked', checked: true }).el);
      pane.appendChild(ui.checkbox({ label: 'Indeterminate', indeterminate: true }).el);
      pane.appendChild(ui.checkbox({ label: 'With a hint', hint: 'Hint under the label.' }).el);
      pane.appendChild(ui.checkbox({ label: 'Disabled', disabled: true }).el);
      pane.appendChild(ui.checkbox({ label: 'Disabled checked', checked: true, disabled: true }).el);
    });
    d.demo(host, 'toggle', function (pane) {
      pane.appendChild(ui.toggle({ label: 'Off' }).el);
      pane.appendChild(ui.toggle({ label: 'On', checked: true }).el);
      pane.appendChild(ui.toggle({ label: 'With a hint', hint: 'Hint under the label.' }).el);
      pane.appendChild(ui.toggle({ label: 'Disabled', disabled: true }).el);
      pane.appendChild(ui.toggle({ label: 'Disabled on', checked: true, disabled: true }).el);
    });
  }

  window.App.admin.designLanguage.uiChoicesSection = { render: render };
})();
