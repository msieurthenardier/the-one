(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Map of tool name → category badge slug. The tool's Config class
  // determines its category (FilesystemConfig → filesystem, etc.); the
  // API endpoint surfaces only `name`/`description`/`enabled`/`config`,
  // not the Config class name, so the mapping is duplicated here.
  // Future flights adding tools must extend this; the L8 verification
  // sweep will fail loudly on a missing entry (defensive `unknown` badge).
  var TOOL_CATEGORIES = {
    // filesystem (9)
    read_file: 'filesystem',
    write_file: 'filesystem',
    edit_file: 'filesystem',
    delete_file: 'filesystem',
    move_file: 'filesystem',
    mkdir: 'filesystem',
    glob: 'filesystem',
    grep: 'filesystem',
    list_dir: 'filesystem',
    // execution (5)
    shell: 'execution',
    shell_session_start: 'execution',
    shell_session_send: 'execution',
    shell_session_close: 'execution',
    shell_session_list: 'execution',
    // python (1)
    python_exec: 'python',
    // web (4)
    http_request: 'web',
    fetch_url: 'web',
    download_file: 'web',
    web_search: 'web'
  };

  // F6 L6 (HAT inline fix): the admin Tools grid groups tiles under
  // per-category tabs (Filesystem / Execution / Python / Web) rather
  // than a single alphabetic list. Operator HAT scenario 1 surfaced the
  // single-list layout as a UX gap once the tool count crossed ~10.
  // Tab declaration order (also tab visual order):
  var CATEGORY_ORDER = ['filesystem', 'execution', 'python', 'web'];
  var CATEGORY_LABELS = {
    filesystem: 'Filesystem',
    execution: 'Execution',
    python: 'Python',
    web: 'Web'
  };

  // Active tab persists across grid re-renders within the area lifetime.
  // L2's populateToolGrid re-renders after every PUT toggle response;
  // without persistence the user would be bounced back to Filesystem on
  // every toggle. Default 'filesystem' (largest group; 9 tools).
  var activeCategory = 'filesystem';

  function tileHtml(t, escapeHtml, escapeAttr, inFlight) {
    var cat = TOOL_CATEGORIES[t.name] || 'unknown';
    var checkedAttr = t.enabled ? 'checked' : '';
    var disabledAttr = inFlight[t.name] ? 'disabled' : '';
    var titleText = t.enabled ? 'Enabled for all agents' : 'Disabled for all agents';
    return (
      '<div class="entity-tile tool-tile" data-testid="tool-card" ' +
           'data-name="' + escapeAttr(t.name) + '" role="listitem" tabindex="0">' +
        '<span class="entity-tile-badge admin-tool-badge admin-tool-badge--' +
          escapeAttr(cat) + '">' + escapeHtml(cat) + '</span>' +
        '<span class="entity-tile-name">' + escapeHtml(t.name) + '</span>' +
        '<span class="entity-tile-description">' + escapeHtml(t.description) + '</span>' +
        '<label class="tool-enable-switch" title="' + escapeAttr(titleText) + '">' +
          '<input type="checkbox" ' + checkedAttr + ' ' + disabledAttr + ' ' +
                 'data-testid="tool-toggle" data-name="' + escapeAttr(t.name) + '" ' +
                 'aria-label="Enable ' + escapeAttr(t.name) + '" />' +
          '<span class="tool-enable-switch-track" aria-hidden="true"></span>' +
        '</label>' +
      '</div>'
    );
  }

  function renderToolsGrid(container, toolConfigs, callbacks) {
    callbacks = callbacks || {};
    var onToggle = callbacks.onToggle || function () {};
    var inFlight = callbacks.inFlight || Object.create(null);
    var onSelectTool = callbacks.onSelectTool || function () {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;

    // Loading state — single placeholder above the (not-yet-rendered)
    // tablist. Keeps the page-header stable so the title doesn't jump.
    if (toolConfigs === null || toolConfigs === undefined) {
      container.innerHTML =
        '<div class="page-header">' +
          '<h1 class="page-title">Built-in Tools</h1>' +
        '</div>' +
        '<div class="admin-loading">Loading tools…</div>';
      return;
    }

    if (toolConfigs.length === 0) {
      container.innerHTML =
        '<div class="page-header">' +
          '<h1 class="page-title">Built-in Tools</h1>' +
        '</div>' +
        '<div class="entity-tile-grid" role="list" aria-label="Built-in tools">' +
          '<div class="empty-state">API returned no tools.</div>' +
        '</div>';
      return;
    }

    // Sort by name (alphabetic) WITHIN each tab. The category tab gives
    // operators the visual grouping; alphabetic-by-name within a tab
    // makes hunting a specific tool predictable.
    var sorted = toolConfigs.slice().sort(function (a, b) {
      return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
    });

    // === Header + tablist scaffold ====================================
    var html = '';
    html += '<div class="page-header"><h1 class="page-title">Built-in Tools</h1></div>';
    html += '<div role="tablist" class="tablist" aria-label="Tool categories">';
    for (var ti = 0; ti < CATEGORY_ORDER.length; ti++) {
      var cid = CATEGORY_ORDER[ti];
      html += '<button type="button" role="tab" class="tab" id="tools-tab-' + cid + '" ' +
        'aria-controls="tools-panel-' + cid + '" data-tab-id="' + cid + '" ' +
        'data-testid="tab-' + cid + '" aria-selected="false" tabindex="-1">' +
        escapeHtml(CATEGORY_LABELS[cid]) + '</button>';
    }
    html += '</div>';

    // === Tab panels ===================================================
    html += '<div class="tabpanels">';
    for (var pi = 0; pi < CATEGORY_ORDER.length; pi++) {
      var pcid = CATEGORY_ORDER[pi];
      var label = CATEGORY_LABELS[pcid];
      html += '<div role="tabpanel" class="tabpanel" id="tools-panel-' + pcid + '" ' +
        'data-tab-id="' + pcid + '" aria-labelledby="tools-tab-' + pcid + '" hidden>';

      // Filter to this category and emit the grid for the panel.
      var groupTiles = '';
      var groupCount = 0;
      for (var si = 0; si < sorted.length; si++) {
        var st = sorted[si];
        if ((TOOL_CATEGORIES[st.name] || 'unknown') !== pcid) continue;
        groupTiles += tileHtml(st, escapeHtml, escapeAttr, inFlight);
        groupCount++;
      }

      if (groupCount === 0) {
        // Defensive: with the current 19 tools every category is
        // populated, but a future tool-add to a new category (or
        // removing all tools from an existing one) would surface
        // this empty state rather than a blank panel.
        html += '<div class="empty-state">No tools.</div>';
      } else {
        html += '<div class="entity-tile-grid" role="list" aria-label="' +
          escapeAttr(label) + ' tools">' + groupTiles + '</div>';
      }

      html += '</div>';
    }
    html += '</div>';

    container.innerHTML = html;

    // === App.tabs wiring ==============================================
    // Restore the persisted active tab; if the persisted id has somehow
    // been clobbered to an unknown value, fall back to filesystem.
    var initialTab = CATEGORY_ORDER.indexOf(activeCategory) === -1
      ? 'filesystem'
      : activeCategory;
    var tablistEl = container.querySelector('.tablist');
    var panelsEl = container.querySelector('.tabpanels');
    if (tablistEl && panelsEl && window.App.tabs) {
      window.App.tabs(tablistEl, panelsEl, {
        initial: initialTab,
        onChange: function (tabId) {
          activeCategory = tabId;
        }
      });
    }

    // === Per-tile toggle + click + keydown wiring =====================
    // Walk every tile across all panels in one sweep — handler attaches
    // to the tile's own DOM, so hidden panels' tiles are wired and
    // ready when their tab is activated.
    var toggles = container.querySelectorAll('input[data-testid="tool-toggle"]');
    for (var j = 0; j < toggles.length; j++) {
      (function (input) {
        input.addEventListener('change', function () {
          onToggle(input.dataset.name, input.checked);
        });
      })(toggles[j]);
    }

    // Tile-level click navigates to the editor UNLESS the click originated
    // on the toggle's interactive surface (input/label/track), which keeps
    // its own native change event. Tile is keyboard-navigable via
    // tabindex="0"; Enter/Space activate the same navigation, with a bail
    // when focus is on the inner toggle input (so Space on the toggle
    // flips the checkbox natively rather than also navigating).
    var tiles = container.querySelectorAll('.tool-tile');
    for (var k = 0; k < tiles.length; k++) {
      (function (tileEl) {
        tileEl.addEventListener('click', function (e) {
          // Bail if the click was on the toggle's interactive surface.
          if (e.target.closest('.tool-enable-switch')) return;
          var name = tileEl.dataset.name;
          if (name) onSelectTool(name);
        });
        tileEl.addEventListener('keydown', function (e) {
          if (e.key !== 'Enter' && e.key !== ' ') return;
          // Don't intercept when focus is on the toggle input — the native
          // checkbox handles Space-to-flip, and Enter is a noop on
          // <input type=checkbox> by default.
          if (document.activeElement && document.activeElement.tagName === 'INPUT') return;
          e.preventDefault();
          var name = tileEl.dataset.name;
          if (name) onSelectTool(name);
        });
      })(tiles[k]);
    }
  }

  window.App.admin.renderToolsGrid = renderToolsGrid;
})();
