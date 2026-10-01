(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.button: every variant x size, with an icon, icon-only, disabled.
  var VARIANTS = ['primary', 'secondary', 'ghost', 'danger'];
  var SIZES = [null, 'sm', 'lg', 'xl'];

  function render(host) {
    var d = App.admin.designLanguage.uiDemo;
    d.demo(host, 'button', function (pane) {
      var s;
      var v;
      for (s = 0; s < SIZES.length; s++) {
        var size = SIZES[s];
        var cells = [];
        for (v = 0; v < VARIANTS.length; v++) {
          cells.push(App.ui.button({
            variant: VARIANTS[v],
            size: size || undefined,
            label: VARIANTS[v] + (size ? ' ' + size : '')
          }));
        }
        pane.appendChild(d.row(cells));
      }
      var withIcon = [];
      var iconOnly = [];
      var disabled = [];
      for (v = 0; v < VARIANTS.length; v++) {
        withIcon.push(App.ui.button({ variant: VARIANTS[v], icon: 'plus', label: 'With icon' }));
        iconOnly.push(App.ui.button({
          variant: VARIANTS[v], icon: 'plus', iconOnly: true, ariaLabel: 'Add (' + VARIANTS[v] + ')'
        }));
        disabled.push(App.ui.button({ variant: VARIANTS[v], label: 'Disabled', disabled: true }));
      }
      pane.appendChild(d.caption('with icon'));
      pane.appendChild(d.row(withIcon));
      pane.appendChild(d.caption('icon-only'));
      pane.appendChild(d.row(iconOnly));
      pane.appendChild(d.caption('disabled'));
      pane.appendChild(d.row(disabled));
    });
  }

  window.App.admin.designLanguage.uiButtonsSection = { render: render };
})();
