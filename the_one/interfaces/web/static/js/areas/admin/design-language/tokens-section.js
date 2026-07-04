(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // Color tokens sampled by the gallery. Order/grouping documents the brand
  // surface palette → border ladder → foreground ladder → accent family →
  // status family. Hex labels are pulled live from getComputedStyle so token
  // changes in tokens.css reflect automatically.
  var COLOR_TOKENS = [
    '--bg',
    '--surface',
    '--surface-elevated',
    '--border',
    '--border-hover',
    '--border-strong',
    '--fg',
    '--fg-secondary',
    '--fg-muted',
    '--accent',
    '--accent-api',
    '--status-success',
    '--status-warning',
    '--status-danger'
  ];

  // v3 geometry + elevation scales (M17 F2): spacing ladder, radius scale,
  // and the two-shadow system. (The --panel-radius* compat aliases were
  // retired in Flight 3 — all consumer refs migrated onto --radius-*/--space-*
  // and the alias definitions deleted; the gallery shows the canonical names.)
  var SPACE_TOKENS = [
    '--space-1',
    '--space-2',
    '--space-3',
    '--space-4',
    '--space-5',
    '--space-6',
    '--space-7',
    '--space-8'
  ];

  var RADIUS_TOKENS = [
    '--radius-sm',
    '--radius-md',
    '--radius-lg'
  ];

  var SHADOW_TOKENS = [
    '--shadow-popover',
    '--shadow-modal'
  ];

  function render(host) {
    var grid = document.createElement('div');
    grid.className = 'design-language-token-swatch-grid';

    var rootStyle = window.getComputedStyle(document.documentElement);

    for (var i = 0; i < COLOR_TOKENS.length; i++) {
      var token = COLOR_TOKENS[i];
      var value = rootStyle.getPropertyValue(token).trim();

      var cell = document.createElement('div');
      cell.className = 'design-language-token-swatch';

      var color = document.createElement('div');
      color.className = 'design-language-token-swatch-color';
      color.style.background = 'var(' + token + ')';

      var name = document.createElement('div');
      name.className = 'design-language-token-swatch-label';
      name.textContent = token;

      var resolved = document.createElement('div');
      resolved.className = 'design-language-token-swatch-label';
      resolved.textContent = value;

      cell.appendChild(color);
      cell.appendChild(name);
      cell.appendChild(resolved);
      grid.appendChild(cell);
    }

    host.appendChild(grid);

    // Shared cell builder for the geometry/elevation rows below: a sample
    // element + token-name label + resolved-value label, matching the
    // color-swatch cell shape.
    function makeSwatchCell(token, sample) {
      var cell = document.createElement('div');
      cell.className = 'design-language-token-swatch';

      var name = document.createElement('div');
      name.className = 'design-language-token-swatch-label';
      name.textContent = token;

      var resolved = document.createElement('div');
      resolved.className = 'design-language-token-swatch-label';
      resolved.textContent = rootStyle.getPropertyValue(token).trim();

      cell.appendChild(sample);
      cell.appendChild(name);
      cell.appendChild(resolved);
      return cell;
    }

    // Spacing scale — each sample is a bar exactly var(--space-N) wide.
    var spaceGrid = document.createElement('div');
    spaceGrid.className = 'design-language-token-swatch-grid';
    spaceGrid.style.marginTop = '12px';

    for (var s = 0; s < SPACE_TOKENS.length; s++) {
      var st = SPACE_TOKENS[s];
      var bar = document.createElement('div');
      bar.style.width = 'var(' + st + ')';
      bar.style.height = '12px';
      bar.style.background = 'var(--border-strong)';
      bar.style.borderRadius = '2px';
      spaceGrid.appendChild(makeSwatchCell(st, bar));
    }

    host.appendChild(spaceGrid);

    // Radius scale samples
    var radiusGrid = document.createElement('div');
    radiusGrid.className = 'design-language-token-swatch-grid';
    radiusGrid.style.marginTop = '12px';

    for (var r = 0; r < RADIUS_TOKENS.length; r++) {
      var rt = RADIUS_TOKENS[r];
      var rshape = document.createElement('div');
      rshape.className = 'design-language-token-swatch-color';
      rshape.style.background = 'var(--surface-elevated)';
      rshape.style.border = '1px solid var(--border)';
      rshape.style.borderRadius = 'var(' + rt + ')';
      radiusGrid.appendChild(makeSwatchCell(rt, rshape));
    }

    host.appendChild(radiusGrid);

    // Two-shadow system — popover + modal elevation on a plain surface.
    var shadowGrid = document.createElement('div');
    shadowGrid.className = 'design-language-token-swatch-grid';
    shadowGrid.style.marginTop = '12px';

    for (var h = 0; h < SHADOW_TOKENS.length; h++) {
      var ht = SHADOW_TOKENS[h];
      var hshape = document.createElement('div');
      hshape.className = 'design-language-token-swatch-color';
      hshape.style.background = 'var(--surface)';
      hshape.style.border = '1px solid var(--border)';
      hshape.style.borderRadius = 'var(--radius-md)';
      hshape.style.boxShadow = 'var(' + ht + ')';
      shadowGrid.appendChild(makeSwatchCell(ht, hshape));
    }

    host.appendChild(shadowGrid);
  }

  window.App.admin.designLanguage.tokensSection = { render: render };
})();
