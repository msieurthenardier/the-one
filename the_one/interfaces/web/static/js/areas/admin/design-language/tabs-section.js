(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // TABS section uses the canonical window.App.tabs(tablistEl, panelsEl, opts)
  // signature per tabs.js:38 — matches existing consumers at
  // agent-editor.js:173 and tools-grid.js:171. The helper wires keyboard nav,
  // [role="tab"]/[role="tabpanel"] ARIA, manual-vs-auto activation, etc.
  // There is NO App.tabs.wire(...) method.
  function render(host) {
    host.innerHTML =
      '<div role="tablist" class="tablist" aria-label="Sample tabs">' +
        '<button type="button" role="tab" class="tab" id="dl-tab-1" data-tab-id="tab-1" aria-controls="dl-panel-1" aria-selected="true" tabindex="0">Tab One</button>' +
        '<button type="button" role="tab" class="tab" id="dl-tab-2" data-tab-id="tab-2" aria-controls="dl-panel-2" aria-selected="false" tabindex="-1">Tab Two</button>' +
        '<button type="button" role="tab" class="tab" id="dl-tab-3" data-tab-id="tab-3" aria-controls="dl-panel-3" aria-selected="false" tabindex="-1">Tab Three</button>' +
      '</div>' +
      '<div class="tabpanels">' +
        '<div role="tabpanel" id="dl-panel-1" data-tab-id="tab-1" aria-labelledby="dl-tab-1">Panel one content. Arrow keys move focus; Enter/Space activates.</div>' +
        '<div role="tabpanel" id="dl-panel-2" data-tab-id="tab-2" aria-labelledby="dl-tab-2" hidden>Panel two content.</div>' +
        '<div role="tabpanel" id="dl-panel-3" data-tab-id="tab-3" aria-labelledby="dl-tab-3" hidden>Panel three content.</div>' +
      '</div>';

    var tablistEl = host.querySelector('[role="tablist"]');
    var panelsEl = host.querySelector('.tabpanels');
    if (tablistEl && panelsEl && window.App && window.App.tabs) {
      window.App.tabs(tablistEl, panelsEl, {
        initial: 'tab-1',
        onChange: function (id) { /* no-op for the gallery */ }
      });
    }
  }

  window.App.admin.designLanguage.tabsSection = { render: render };
})();
