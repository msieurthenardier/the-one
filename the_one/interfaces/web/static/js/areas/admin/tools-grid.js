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
  //
  // Squawk 0032: this mirror is duplicated a THIRD time in
  // studio.js's per-agent Tools tab TOOL_CATEGORIES (different shape —
  // category → [tool names], not tool name → category). Squawk 0028
  // added the Connectors bucket there; this squawk brings the admin
  // grid to parity. The two mirrors are not unified — see that squawk's
  // Corrective Action for why.
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
    // execution (6) — shell + the four PTY session tools + python_exec
    shell: 'execution',
    shell_session_start: 'execution',
    shell_session_send: 'execution',
    shell_session_close: 'execution',
    shell_session_list: 'execution',
    python_exec: 'execution',
    // web (4)
    http_request: 'web',
    fetch_url: 'web',
    download_file: 'web',
    web_search: 'web',
    // connectors (2) — Mission 23 Flight 2's platform-connector tools;
    // added by squawk 0032, mirroring squawk 0028's studio.js fix.
    send_to_platform_channel: 'connectors',
    fetch_channel_history: 'connectors'
  };

  // F6 L6 (HAT inline fix): the admin Tools grid groups tiles under
  // per-category tabs (Filesystem / Execution / Web) rather than a
  // single alphabetic list. Operator HAT scenario 1 surfaced the
  // single-list layout as a UX gap once the tool count crossed ~10.
  // Connectors (squawk 0032) appended at the end of declaration order
  // rather than interleaved, to match studio.js's tab ordering.
  // Tab declaration order (also tab visual order):
  var CATEGORY_ORDER = ['filesystem', 'execution', 'web', 'connectors'];
  var CATEGORY_LABELS = {
    filesystem: 'Filesystem',
    execution: 'Execution',
    web: 'Web',
    connectors: 'Connectors'
  };

  // Active tab persists across grid re-renders within the area lifetime.
  // L2's populateToolGrid re-renders after every PUT toggle response;
  // without persistence the user would be bounced back to Filesystem on
  // every toggle. Default 'filesystem' (largest group; 9 tools).
  var activeCategory = 'filesystem';
  // The open tool whose category was last revealed (M25 F3 L5b): opening a
  // tool (or a deep link to one) switches the tabs to its category ONCE; a
  // later re-render with the same tool open (a toggle PUT) keeps whatever tab
  // the user has chosen since.
  var revealedName = null;
  // The tabs handle of the mounted list (App.tabs' { activate, getActive }).
  var tabsHandle = null;
  // A focus target a re-render could not restore because it was disabled
  // (a toggle while its PUT is in flight); retried by the next re-render.
  var deferredFocus = null;

  // M25 F3 L5b (flight DD7): the tile keeps its card shape, but it is no
  // longer a click target. The tool NAME is the item link (a plain
  // `<a href="#settings/tools/{name}">`, routed by App.nav's link
  // interceptor through the router, so the leave guard asks once about a
  // dirty editor) and the single focusable target besides the toggle. The
  // toggle never navigates: its change event only toggles enablement. The
  // open tool's tile is marked selected (aria-current="page" on its link,
  // the selected wash on the tile).
  function tileHtml(t, escapeHtml, escapeAttr, inFlight, selectedName) {
    var cat = TOOL_CATEGORIES[t.name] || 'unknown';
    var checkedAttr = t.enabled ? 'checked' : '';
    var disabledAttr = inFlight[t.name] ? 'disabled' : '';
    var titleText = t.enabled ? 'Enabled for all agents' : 'Disabled for all agents';
    var selected = !!selectedName && selectedName === t.name;
    var href = window.App.router.href({ destination: 'settings', section: 'tools', id: t.name });
    return (
      '<div class="entity-tile tool-tile' + (selected ? ' active' : '') + '" data-testid="tool-card" ' +
           'data-name="' + escapeAttr(t.name) + '" role="listitem">' +
        '<span class="entity-tile-badge admin-tool-badge admin-tool-badge--' +
          escapeAttr(cat) + '">' + escapeHtml(cat) + '</span>' +
        '<a class="entity-tile-name tool-tile-link" href="' + escapeAttr(href) + '"' +
          (selected ? ' aria-current="page"' : '') + '>' + escapeHtml(t.name) + '</a>' +
        '<span class="entity-tile-description">' + escapeHtml(t.description) + '</span>' +
        '<label class="tool-enable-switch tool-enable-switch--corner" title="' + escapeAttr(titleText) + '">' +
          '<input type="checkbox" ' + checkedAttr + ' ' + disabledAttr + ' ' +
                 'data-testid="tool-toggle" data-name="' + escapeAttr(t.name) + '" ' +
                 'aria-label="Enable ' + escapeAttr(t.name) + '" />' +
          '<span class="tool-enable-switch-track" aria-hidden="true"></span>' +
          // F2 Leg 2 (A.12): visually-hidden state context. The title=""
          // attribute already conveys this on mouse-hover for sighted
          // users; the visually-hidden span exposes the same state text
          // to screen readers as part of the <label>'s accessible name.
          '<span class="visually-hidden">' + escapeHtml(titleText) + '</span>' +
        '</label>' +
      '</div>'
    );
  }

  // The focus key of the element focused inside `container` (a toggle, a
  // tool link or a category tab), or null.
  function focusKey(container) {
    var a = document.activeElement;
    if (!a || !container.contains(a)) return null;
    if (a.getAttribute('data-testid') === 'tool-toggle') return { kind: 'toggle', id: a.getAttribute('data-name') };
    if (a.classList && a.classList.contains('tool-tile-link')) {
      var tile = a.closest('.tool-tile');
      return tile ? { kind: 'link', id: tile.getAttribute('data-name') } : null;
    }
    if (a.getAttribute('role') === 'tab') return { kind: 'tab', id: a.getAttribute('data-tab-id') };
    return null;
  }

  function focusTarget(container, key) {
    var nodes;
    var i;
    if (key.kind === 'toggle') {
      nodes = container.querySelectorAll('input[data-testid="tool-toggle"]');
      for (i = 0; i < nodes.length; i++) if (nodes[i].getAttribute('data-name') === key.id) return nodes[i];
    } else if (key.kind === 'link') {
      nodes = container.querySelectorAll('.tool-tile');
      for (i = 0; i < nodes.length; i++) {
        if (nodes[i].getAttribute('data-name') === key.id) return nodes[i].querySelector('.tool-tile-link');
      }
    } else if (key.kind === 'tab') {
      nodes = container.querySelectorAll('[role="tab"]');
      for (i = 0; i < nodes.length; i++) if (nodes[i].getAttribute('data-tab-id') === key.id) return nodes[i];
    }
    return null;
  }

  // Renders the Built-in tools LIST (category tabs + tool tiles) into
  // `container`, the page scaffold's `.settings-list` (M25 F3 L5b: admin.js
  // owns the page header and the `.settings-item` section the tool editor
  // mounts in, so a list re-render never touches the editor).
  //   callbacks: { onToggle(name, enabled), inFlight, selectedName }
  // A focused toggle, tool link or tab keeps focus across the re-render (a
  // toggle disabled by its in-flight PUT gets it back on the next render).
  function renderToolsGrid(container, toolConfigs, callbacks) {
    callbacks = callbacks || {};
    var onToggle = callbacks.onToggle || function () {};
    var inFlight = callbacks.inFlight || Object.create(null);
    var selectedName = callbacks.selectedName || null;
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var restore = focusKey(container);
    if (!restore && deferredFocus && (!document.activeElement || document.activeElement === document.body)) {
      restore = deferredFocus;
    }
    deferredFocus = null;
    tabsHandle = null;

    // Loading state — a single placeholder (the page header is the
    // scaffold's, so nothing jumps).
    if (toolConfigs === null || toolConfigs === undefined) {
      container.innerHTML = '<div class="admin-loading">Loading tools…</div>';
      return;
    }

    if (toolConfigs.length === 0) {
      container.innerHTML = '<div class="empty-state">API returned no tools.</div>';
      return;
    }

    // Opening a tool reveals its category once (see revealedName).
    if (!selectedName) {
      revealedName = null;
    } else if (selectedName !== revealedName) {
      revealedName = selectedName;
      if (TOOL_CATEGORIES[selectedName] && CATEGORY_ORDER.indexOf(TOOL_CATEGORIES[selectedName]) !== -1) {
        activeCategory = TOOL_CATEGORIES[selectedName];
      }
    }

    // Sort by name (alphabetic) WITHIN each tab. The category tab gives
    // operators the visual grouping; alphabetic-by-name within a tab
    // makes hunting a specific tool predictable.
    var sorted = toolConfigs.slice().sort(function (a, b) {
      return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
    });

    // === Tablist ======================================================
    var html = '';
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
        groupTiles += tileHtml(st, escapeHtml, escapeAttr, inFlight, selectedName);
        groupCount++;
      }

      if (groupCount === 0) {
        // Defensive: with the current 21 tools every category is
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
      tabsHandle = window.App.tabs(tablistEl, panelsEl, {
        initial: initialTab,
        onChange: function (tabId) {
          activeCategory = tabId;
        }
      });
    }

    // === Per-toggle wiring ============================================
    // Walk every toggle across all panels in one sweep — hidden panels'
    // toggles are wired and ready when their tab is activated. The change
    // event only toggles enablement: nothing on the tile navigates (the
    // tool name link is the item link).
    var toggles = container.querySelectorAll('input[data-testid="tool-toggle"]');
    for (var j = 0; j < toggles.length; j++) {
      (function (input) {
        input.addEventListener('change', function () {
          onToggle(input.dataset.name, input.checked);
        });
      })(toggles[j]);
    }

    if (restore) {
      var target = focusTarget(container, restore);
      if (target && target.disabled) {
        deferredFocus = restore;
      } else if (target) {
        target.focus({ preventScroll: true });
      }
    }
  }

  // Mark the open tool in place (no re-render): `aria-current="page"` on its
  // link and the selected wash on its tile; every other tile is cleared.
  // Opening a tool switches the tabs to its category once (an unknown name
  // keeps the current tab).
  function setToolsSelection(container, selectedName) {
    selectedName = selectedName || null;
    var tiles = container.querySelectorAll('.tool-tile');
    for (var i = 0; i < tiles.length; i++) {
      var on = !!selectedName && tiles[i].getAttribute('data-name') === selectedName;
      tiles[i].classList.toggle('active', on);
      var link = tiles[i].querySelector('.tool-tile-link');
      if (!link) continue;
      if (on) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    if (!selectedName) {
      revealedName = null;
      return;
    }
    // No tabs yet (the list is still loading): its render reveals the tool.
    if (!tabsHandle || selectedName === revealedName) return;
    revealedName = selectedName;
    var cat = TOOL_CATEGORIES[selectedName];
    if (cat && CATEGORY_ORDER.indexOf(cat) !== -1 && tabsHandle && tabsHandle.getActive() !== cat) {
      tabsHandle.activate(cat);
    }
  }

  window.App.admin.renderToolsGrid = renderToolsGrid;
  window.App.admin.setToolsSelection = setToolsSelection;
})();
