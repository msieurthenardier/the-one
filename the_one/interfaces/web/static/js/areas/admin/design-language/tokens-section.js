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
    '--accent-glow',
    '--status-success',
    '--status-warning',
    '--status-danger'
  ];

  var RADIUS_TOKENS = [
    '--panel-radius',
    '--panel-radius-sm'
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

    // Panel radius samples
    var radiusGrid = document.createElement('div');
    radiusGrid.className = 'design-language-token-swatch-grid';
    radiusGrid.style.marginTop = '12px';

    for (var r = 0; r < RADIUS_TOKENS.length; r++) {
      var rt = RADIUS_TOKENS[r];
      var rv = rootStyle.getPropertyValue(rt).trim();

      var rcell = document.createElement('div');
      rcell.className = 'design-language-token-swatch';

      var rshape = document.createElement('div');
      rshape.className = 'design-language-token-swatch-color';
      rshape.style.background = 'var(--surface-elevated)';
      rshape.style.borderRadius = 'var(' + rt + ')';

      var rname = document.createElement('div');
      rname.className = 'design-language-token-swatch-label';
      rname.textContent = rt;

      var rval = document.createElement('div');
      rval.className = 'design-language-token-swatch-label';
      rval.textContent = rv;

      rcell.appendChild(rshape);
      rcell.appendChild(rname);
      rcell.appendChild(rval);
      radiusGrid.appendChild(rcell);
    }

    host.appendChild(radiusGrid);
  }

  window.App.admin.designLanguage.tokensSection = { render: render };
})();
