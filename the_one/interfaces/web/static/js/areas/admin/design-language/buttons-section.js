(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // M17 F3 button vocabulary: PRIMARY (accent fill) / SECONDARY (surface +
  // hairline) / GHOST (borderless) / DANGER (soft danger fill). 32px height,
  // --radius-sm, flat fills, pinned focus form. ONE primary per region.
  // Columns: variants. Rows: size modifiers. Final row: disabled.
  // Hover/focus states are NOT forced — operator induces them live in the
  // gallery during vibe sessions so the chrome itself is testable.
  var VARIANTS = [
    { cls: 'btn-filled-primary',    label: 'Primary' },
    { cls: 'btn-outlined-primary',  label: 'Secondary' },
    { cls: 'btn-ghost',             label: 'Ghost' },
    { cls: 'btn-muted-destructive', label: 'Danger' }
  ];

  var SIZES = [
    { cls: '',       label: 'default' },
    { cls: 'btn-sm', label: 'sm' },
    { cls: 'btn-lg', label: 'lg' },
    { cls: 'btn-xl', label: 'xl' }
  ];

  function caption(text) {
    var el = document.createElement('span');
    el.style.fontFamily = 'var(--font-family-mono)';
    el.style.fontSize = 'var(--font-size-tiny)';
    el.style.color = 'var(--fg-muted)';
    el.textContent = text;
    return el;
  }

  function buttonRow(sizeCls, labelSuffix, disabled) {
    var row = document.createElement('div');
    row.className = 'design-language-button-grid';

    for (var v = 0; v < VARIANTS.length; v++) {
      var variant = VARIANTS[v];
      var cell = document.createElement('div');
      cell.style.display = 'flex';
      cell.style.alignItems = 'center';
      cell.style.gap = '8px';

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = variant.cls + (sizeCls ? ' ' + sizeCls : '');
      if (disabled) btn.disabled = true;
      btn.textContent = variant.label + ' ' + labelSuffix;
      cell.appendChild(btn);

      row.appendChild(cell);
    }
    return row;
  }

  function render(host) {
    host.appendChild(caption(
      'variants: primary (accent fill) / secondary (surface + hairline) / ' +
      'ghost / danger — 32px, radius-sm, flat fills. One primary per region.'
    ));

    for (var s = 0; s < SIZES.length; s++) {
      host.appendChild(buttonRow(SIZES[s].cls, SIZES[s].label, false));
    }

    var disabledRow = buttonRow('', 'disabled', true);
    disabledRow.style.marginTop = '12px';
    host.appendChild(disabledRow);
  }

  window.App.admin.designLanguage.buttonsSection = { render: render };
})();
