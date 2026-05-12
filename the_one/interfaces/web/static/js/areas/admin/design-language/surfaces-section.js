(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // SURFACES section samples a mixed set of brand chrome and list/tile
  // primitives. Static miniatures for app-topbar and app-picker (no event
  // bindings, no real renderTopBar invocation) so the gallery never
  // re-mounts the real chrome. The iOS-toggle sample uses the canonical
  // DOM template from tools-grid.js:67-72; the gallery-scoped
  // .design-language-toggle-sample override in admin.css strips the
  // primitive's absolute bottom-right anchoring so two states flow inline.
  function render(host) {
    host.innerHTML =
      // --- Entity tile (single) ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">entity-tile (single)</span>' +
        '<div class="entity-tile" role="listitem" tabindex="0">' +
          '<span class="entity-tile-name">Sample Tile</span>' +
          '<span class="entity-tile-description">Short description text for the tile.</span>' +
        '</div>' +
      '</div>' +

      // --- Entity tile grid ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">entity-tile-grid</span>' +
        '<div class="entity-tile-grid">' +
          '<div class="entity-tile" role="listitem" tabindex="0">' +
            '<span class="entity-tile-name">Tile One</span>' +
            '<span class="entity-tile-description">First grid tile.</span>' +
          '</div>' +
          '<div class="entity-tile active" role="listitem" tabindex="0" aria-selected="true">' +
            '<span class="entity-tile-name">Tile Two (active)</span>' +
            '<span class="entity-tile-description">Selected tile state.</span>' +
          '</div>' +
          '<div class="entity-tile" role="listitem" tabindex="0">' +
            '<span class="entity-tile-name">Tile Three</span>' +
            '<span class="entity-tile-description">Third grid tile.</span>' +
          '</div>' +
        '</div>' +
      '</div>' +

      // --- Section nav ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">section-nav</span>' +
        '<div class="section-nav" style="max-width: 220px;">' +
          '<button type="button" class="section-nav-item">Item one</button>' +
          '<button type="button" class="section-nav-item" aria-current="page">Item two (current)</button>' +
          '<button type="button" class="section-nav-item">Item three</button>' +
        '</div>' +
      '</div>' +

      // --- List items ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">list-item</span>' +
        '<div style="display: flex; flex-direction: column; gap: 4px; max-width: 320px;">' +
          '<div class="list-item">Default list item</div>' +
          '<div class="list-item active">Active list item</div>' +
          '<div class="list-item confirm-delete">' +
            '<span data-confirm-title>Confirm-delete list item</span>' +
            '<button type="button" class="list-item-delete" aria-label="delete">×</button>' +
          '</div>' +
        '</div>' +
      '</div>' +

      // --- App-picker miniature (rest + active, static) ---
      // Post-Flight-3-Leg-2: the popover affordance was retired; .app-picker-button
      // is now a flat top-bar area button. Sample shows rest vs aria-current="page".
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">app-picker-button (rest / active)</span>' +
        '<div style="display: flex; gap: 12px; align-items: center;">' +
          '<button type="button" class="app-picker-button">' +
            '<span class="app-picker-button-icon">' +
              '<svg viewBox="0 0 18 18" fill="currentColor"><circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>' +
            '</span>' +
            '<span class="app-picker-button-label">System</span>' +
          '</button>' +
          '<button type="button" class="app-picker-button" aria-current="page">' +
            '<span class="app-picker-button-icon">' +
              '<svg viewBox="0 0 18 18" fill="currentColor"><circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>' +
            '</span>' +
            '<span class="app-picker-button-label">System</span>' +
          '</button>' +
        '</div>' +
      '</div>' +

      // --- iOS-toggle sample (ON + OFF, side by side via gallery-scoped override) ---
      '<div style="display: flex; flex-direction: column; gap: 8px;">' +
        '<span style="font-family: var(--font-family-mono); font-size: var(--font-size-tiny); color: var(--fg-muted);">tool-enable-switch (iOS toggle)</span>' +
        '<div class="design-language-toggle-sample">' +
          '<label class="tool-enable-switch">' +
            '<input type="checkbox" checked aria-label="ON state sample" />' +
            '<span class="tool-enable-switch-track" aria-hidden="true"></span>' +
          '</label>' +
          '<span class="design-language-toggle-label">ON</span>' +
          '<label class="tool-enable-switch">' +
            '<input type="checkbox" aria-label="OFF state sample" />' +
            '<span class="tool-enable-switch-track" aria-hidden="true"></span>' +
          '</label>' +
          '<span class="design-language-toggle-label">OFF</span>' +
        '</div>' +
      '</div>';
  }

  window.App.admin.designLanguage.surfacesSection = { render: render };
})();
