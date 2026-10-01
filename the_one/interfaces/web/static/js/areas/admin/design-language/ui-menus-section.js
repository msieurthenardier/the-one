(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.menu: label trigger, icon-only trigger, danger and disabled items,
  // start and end alignment. Menus are shown closed; open one with Enter,
  // Space or ArrowDown.
  function noop() {}

  function items() {
    return [
      { label: 'Rename', onSelect: noop },
      { label: 'Duplicate', icon: 'plus', onSelect: noop },
      { label: 'Locked action', disabled: true, onSelect: noop },
      { label: 'Delete', danger: true, onSelect: noop }
    ];
  }

  function render(host) {
    var d = App.admin.designLanguage.uiDemo;
    var ui = App.ui;

    d.demo(host, 'menu', function (pane) {
      pane.classList.add('design-language-ui-pane--menu');
      pane.appendChild(d.row([
        ui.menu({ trigger: { label: 'Actions', variant: 'secondary' }, items: items() }).el,
        ui.menu({ trigger: { label: 'Primary', variant: 'primary' }, items: items() }).el,
        ui.menu({
          trigger: { icon: 'plus', iconOnly: true, variant: 'ghost', ariaLabel: 'More actions' },
          align: 'end',
          items: items()
        }).el
      ]));
    });
  }

  window.App.admin.designLanguage.uiMenusSection = { render: render };
})();
