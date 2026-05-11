(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // Columns: primitive variants. Rows: size modifiers. Final row: disabled.
  // Hover/focus states are NOT forced — operator induces them live in the
  // gallery during vibe sessions so the chrome itself is testable.
  var PRIMITIVES = [
    { cls: 'btn-outlined-primary', label: 'Outlined' },
    { cls: 'btn-filled-primary',   label: 'Filled' },
    { cls: 'btn-muted-destructive', label: 'Destructive' }
  ];

  var SIZES = [
    { cls: '',         label: 'default' },
    { cls: 'btn-sm',   label: 'sm' },
    { cls: 'btn-lg',   label: 'lg' },
    { cls: 'btn-xl',   label: 'xl' }
  ];

  function render(host) {
    for (var s = 0; s < SIZES.length; s++) {
      var size = SIZES[s];
      var row = document.createElement('div');
      row.className = 'design-language-button-grid';

      for (var p = 0; p < PRIMITIVES.length; p++) {
        var prim = PRIMITIVES[p];
        var cell = document.createElement('div');
        cell.style.display = 'flex';
        cell.style.alignItems = 'center';
        cell.style.gap = '8px';

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = prim.cls + (size.cls ? ' ' + size.cls : '');
        btn.textContent = prim.label + ' ' + size.label;
        cell.appendChild(btn);

        row.appendChild(cell);
      }

      host.appendChild(row);
    }

    // Disabled-state row
    var disabledRow = document.createElement('div');
    disabledRow.className = 'design-language-button-grid';
    disabledRow.style.marginTop = '12px';

    for (var d = 0; d < PRIMITIVES.length; d++) {
      var dprim = PRIMITIVES[d];
      var dcell = document.createElement('div');
      dcell.style.display = 'flex';
      dcell.style.alignItems = 'center';
      dcell.style.gap = '8px';

      var dbtn = document.createElement('button');
      dbtn.type = 'button';
      dbtn.className = dprim.cls;
      dbtn.disabled = true;
      dbtn.textContent = dprim.label + ' disabled';
      dcell.appendChild(dbtn);

      disabledRow.appendChild(dcell);
    }
    host.appendChild(disabledRow);
  }

  window.App.admin.designLanguage.buttonsSection = { render: render };
})();
