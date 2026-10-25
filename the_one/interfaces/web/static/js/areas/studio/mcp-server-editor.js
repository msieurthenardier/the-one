// App.studio.renderMcpSourceEditor — MCP source editor (M07 F1 L6;
// relocated from admin → studio post-F2 retrofit).
//
// Mirrors provider-editor.js structural shape:
//   <div class="editor-header"> … </div>
//   <div class="editor-section">Connection</div>          (name, type, transport-fields)
//   <div class="editor-section">Environment Variables /
//                               Custom Headers</div>      (unified kv table)
//   <div class="editor-section danger-zone"> … </div>     (edit only)
//
// Per-row UI shape (option c): unified kv table with key / value / sensitive
// checkbox / eye / remove columns. The label swaps "Environment Variables"
// (stdio) ↔ "Custom Headers" (streamable-http) on type change. Sensitive=true
// rows route to `secrets[key]`; sensitive=false rows route to `config.env[key]`
// (stdio) or `config.headers[key]` (streamable-http).
//
// Per-key __MASKED__ round-trip: each kv row captures `_originalMasked` at
// mount via data-original-masked attribute. At save time, if value ===
// _originalMasked AND sensitive=true, payload sends '__MASKED__' for that key
// and the L3 endpoint preserves the stored secret.
//
// callbacks: { onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange,
//              onListStale }
// M25 F3 L4b (DD2): Back (`onBack`) is retired. The header carries the
// breadcrumb "Library / MCP servers" ("Library" a link to `#library`, the group plain text)
// and the unsaved caption, whose text follows every onDirtyChange report.
// onListStale (M25 F3 L4a) fires after each 'mcp-sources' invalidation that
// is not a save or delete: a connect success (the manual Refresh, the
// auto-run after create, Phase 2 after sign-in) and Reset connection. Both
// rewrite config._cache server-side, so the Library list's tool count is
// stale; the caller reloads the list.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var mcpEditor = window.App.studio.mcpEditor;
  var STDIO_CUSTOM_SENTINEL = mcpEditor.shared.STDIO_CUSTOM_SENTINEL;
  var deriveStdioRuntimeSelection = mcpEditor.shared.deriveStdioRuntimeSelection;
  var renderToolsListHtml = mcpEditor.serverInfo.renderToolsListHtml;
  var renderServerInfoSection = mcpEditor.serverInfo.renderServerInfoSection;
  var cacheHasServerInfo = mcpEditor.serverInfo.cacheHasServerInfo;
  var syncServerInfoSection = mcpEditor.serverInfo.syncServerInfoSection;
  var renderConnectionFields = mcpEditor.connectionFields.renderConnectionFields;
  var mountChipListEditors = mcpEditor.connectionFields.mountChipListEditors;
  var wireChipLists = mcpEditor.connectionFields.wireChipLists;
  var applyStdioRuntimeSelection = mcpEditor.connectionFields.applyStdioRuntimeSelection;
  var applyTransportVisibility = mcpEditor.connectionFields.applyTransportVisibility;
  var renderSandboxSection = mcpEditor.sandboxFields.renderSandboxSection;
  var collectExistingKvRows = mcpEditor.envHeaders.collectExistingKvRows;
  var renderKvTable = mcpEditor.envHeaders.renderKvTable;
  var renderKvRow = mcpEditor.envHeaders.renderKvRow;
  var updateKvHeadVisibility = mcpEditor.envHeaders.updateKvHeadVisibility;
  var partitionKvRows = mcpEditor.envHeaders.partitionKvRows;
  var renderConnectionActions = mcpEditor.connectionStatus.renderConnectionActions;
  var wireResetButton = mcpEditor.connectionStatus.wireResetButton;
  var syncResetButtonVisibility = mcpEditor.connectionStatus.syncResetButtonVisibility;
  var handleTestConnection = mcpEditor.connectionStatus.handleTestConnection;

  // ── Public entry point ──────────────────────────────────────────────

  function renderMcpSourceEditor(container, source, mcpTypes, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !source;
    var name = isCreate ? 'New MCP Server' : (source.name || '');
    var type = isCreate ? '' : (source.type || '');

    // ── Header ─────────────────────────────────────────────────────────
    var html = '';
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h1 class="editor-title" tabindex="-1">' + escapeHtml(name) + '</h1>';
    if (!isCreate) {
      var summary = '';
      if (source.config) {
        if (type === 'stdio' && source.config.command) summary = source.config.command;
        else if (type === 'streamable-http' && source.config.url) summary = source.config.url;
      }
      var subtitleParts = [escapeHtml(type)];
      if (summary) subtitleParts.push(escapeHtml(summary));
      html += '<p class="editor-subtitle">' + subtitleParts.join(' · ') + '</p>';
    }
    html += '</div>';

    // Action cluster. M25 F3 L4b (DD2): Back is retired (the breadcrumb's
    // group link closes the item); the cluster opens with the stable unsaved
    // caption, whose text wireEditorEvents' reportDirty sets or clears.
    // Cancel on the create form abandons creation (DD8), so it is enabled
    // from first render, clean or dirty (the M25 F3 behavior-gate fix); in
    // edit mode it reverts, and stays disabled while there is nothing to
    // revert.
    html += '<div class="form-actions">';
    html += '<span class="editor-unsaved" role="status" data-testid="editor-unsaved"></span>';
    html += '<button type="button" class="btn-outlined-primary cancel-btn" data-testid="cancel-mcp-source-btn"' + (isCreate ? '' : ' disabled') + '>Cancel</button>';
    html += '<button type="button" class="btn-filled-primary save-btn" data-testid="save-mcp-source-btn" disabled>' + (isCreate ? 'Create' : 'Save') + '</button>';
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // ── Connection section ────────────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Connection</div>';
    html += renderConnectionFields(source, mcpTypes);
    // F9 L1: Refresh-connection button (renamed from "Test connection")
    // lives at the bottom of the Connection section in edit-mode for
    // streamable-http sources. The result panel renders into the Tools
    // section below. The data-testid hook stays "mcp-test-connection"
    // so existing browser-test selectors keep working — it's an
    // implementation handle, not a label.
    //
    // F9 L1 (vibing follow-up): Reset connection button paired with
    // Refresh in the same row. Reset is reversible (just re-OAuth) — it
    // belongs next to Refresh as a secondary connection action, not in
    // Danger Zone. Visible only when the source carries OAuth state
    // (gated by `hasOAuthState`); hidden for stdio and unauth'd
    // streamable-http. Uses the same `btn-outlined-primary` cosmetic as
    // Refresh so the pair reads as grouped connection controls.
    //
    // F9 L1 (vibing polish): "Last updated" label lives inside the
    // same flex row as Refresh/Reset, pushed to the far end via
    // `margin-left: auto`. Low-emphasis (--fg-secondary, body-sm) so it
    // reads as informational, not actionable. Hidden until a successful
    // refresh seeds source.config._cache.last_updated. Placed AFTER the
    // buttons in source order so syncResetButtonVisibility can insert
    // Reset between Refresh and the label without re-shuffling.
    // F9 L2 D1: Refresh-connection button now renders for BOTH streamable-http
    // AND stdio sources. Stdio's backend dispatch (api.py /test/connect) is a
    // straight transient-client lifecycle — no OAuth, no popup. The Reset
    // button is gated by hasOAuthState() which already returns false for stdio,
    // so the existing OAuth-state-dependent UI hides itself for stdio without
    // additional changes here.
    html += renderConnectionActions(source);
    html += '</div>';

    // ── Sandbox section (stdio only) ──────────────────────────────────
    html += renderSandboxSection(source, type);

    // ── Tools section (edit only, streamable-http + stdio) ────────────
    // Populated by handleTestConnection after a successful refresh. Empty
    // state until first refresh runs. Verbose tool descriptions (e.g.
    // Cloudflare API MCP) get a collapsible <details> per tool so the
    // section stays scannable.
    //
    // F9 L1: Tools section moved ABOVE the Custom Headers section per
    // operator feedback — connection diagnostics belong nearer the
    // Connection block, headers are configuration that lives further down.
    //
    // F9 L1 (vibing): if the backend persisted a tools cache to
    // source.config._cache after a previous successful refresh, render
    // it on initial mount so the operator sees the tools list without
    // having to click Refresh first. Cache is updated server-side on
    // every successful /test/connect.
    //
    // F9 L1 (vibing polish): the "Last updated" timestamp moved up to
    // the connection-actions row (next to Refresh/Reset) so it sits
    // visually with the controls that drive its value. The label is
    // rendered above; this section now contains only the connection
    // status banner + the tool list.
    //
    // F9 L2 D1: Tools section renders for stdio sources too so the
    // post-test render path (capability flags + collapsible schemas)
    // shares the same code path with streamable-http.
    if (!isCreate && source && (source.type === 'streamable-http' || source.type === 'stdio')) {
      var cache = (source.config && source.config._cache) || null;
      // F4 L3 (M08): Server section — surfaces server-declared identity
      // (serverInfo: title / name / version / websiteUrl / icons), the
      // negotiated protocol version, the server's free-form instructions
      // prose, declared capabilities, and any `_meta` extras. Rendered
      // above Tools when any of these are available in the cache.
      if (cacheHasServerInfo(cache)) {
        html += renderServerInfoSection(cache);
      }
      html += '<div class="editor-section mcp-tools-section">';
      html += '<div class="section-title">Tools</div>';
      if (cache && Array.isArray(cache.tools)) {
        // F4 L7 (M08): LED + "Connected." moved up to the connection-actions
        // row. The status banner here keeps the tool-count line + the
        // `mcp-test-status` data-testid that browser tests assert against.
        var statusInner = (
          'Server exposes <strong>' + cache.tools.length + '</strong> tool' +
          (cache.tools.length === 1 ? '' : 's') + '.'
        );
        html += '<div class="mcp-tools-status" data-testid="mcp-test-status">' + statusInner + '</div>';
        html += '<div class="mcp-tools-list" data-testid="mcp-tools-list">' +
                renderToolsListHtml(cache.tools) +
                '</div>';
      } else {
        html += '<div class="mcp-tools-status" data-testid="mcp-test-status">';
        html += 'Click <strong>Refresh connection</strong> above to discover the tools this server exposes.';
        html += '</div>';
        html += '<div class="mcp-tools-list" data-testid="mcp-tools-list" hidden></div>';
      }
      html += '</div>';
    }

    // ── Environment / Headers section ─────────────────────────────────
    // Sits below Tools for streamable-http (F9 L1 reorder); for stdio
    // there is no Tools section, so it lands right after Sandbox as before.
    var kvLabel = (type === 'streamable-http') ? 'Custom Headers' : 'Environment Variables';
    html += '<div class="editor-section">';
    html += '<div class="section-title kv-section-title" ' +
            'data-stdio-label="Environment Variables" ' +
            'data-streamable-http-label="Custom Headers">' +
            escapeHtml(kvLabel) + '</div>';
    html += renderKvTable(source, type);
    html += '</div>';

    // ── Danger Zone (edit only) ───────────────────────────────────────
    // F9 L1 (vibing follow-up): the "Reset connection" button moved out
    // of Danger Zone and now sits next to Refresh in the Connection
    // block — it's a reversible operation (re-OAuth on next Refresh),
    // not a destructive one. Danger Zone now contains only Delete.
    if (!isCreate) {
      html += '<div class="editor-section danger-zone">';
      html += '<div class="section-title danger-zone-title">Danger Zone</div>';
      // F9 L1 (vibing polish): trash icon to the LEFT of the label,
      // mirroring the Refresh button's icon-then-text pattern and the
      // per-row Custom Headers trash glyph. The icon sits OUTSIDE the
      // `data-confirm-title` span so App.confirmDelete only swaps the
      // label text on arm; the glyph persists through the confirm flow.
      html += '<button type="button" class="btn-muted-destructive delete-btn mcp-delete-btn" data-testid="delete-mcp-source-btn" data-name="' + escapeAttr(source.name || '') + '">' +
              window.App.icon('trash') +
              '<span data-confirm-title>Delete MCP Server</span>' +
              '</button>';
      html += '</div>';
    }

    container.innerHTML = html;

    // The breadcrumb (M25 F3 DD2): "Library / MCP servers", inserted with DOM
    // APIs after the markup is in place (this editor is string-built), as the
    // first child of .editor-header-text, in edit and create modes. Its "Library"
    // segment links to `#library` (DD3; the group is plain text): with
    // Back retired it is the visible way to close the item. studio.js routes
    // the click (the router's guard asks once about a dirty editor) and
    // focuses the item's row after the close (DD8).
    var headerText = container.querySelector('.editor-header-text');
    var crumb = document.createElement('div');
    crumb.className = 'editor-breadcrumb';
    var crumbLink = document.createElement('a');
    crumbLink.className = 'editor-breadcrumb-link';
    crumbLink.setAttribute('href', window.App.router.href({ destination: 'library' }));
    crumbLink.setAttribute('data-testid', 'editor-breadcrumb-link');
    crumbLink.textContent = 'Library';
    crumb.appendChild(crumbLink);
    crumb.appendChild(document.createTextNode(' / MCP servers'));
    headerText.insertBefore(crumb, headerText.firstChild);

    mountChipListEditors(container, source);
    wireEditorEvents(container, source, mcpTypes, callbacks);
  }

  // ── Form snapshot + dirty tracking ──────────────────────────────────

  function getFormSnapshot(container) {
    /* Three explicit walks (avoid the flat data[dataset.field] = value
       collision since multiple kv rows share data-field="kv-key" etc.). */
    var helpers = window.App.adminFormHelpers;
    var staticData = {};
    // F3 L5b: sandbox-network-allowed is a checkbox; the loop below reads
    // el.checked for type === 'checkbox' and el.value otherwise.
    // F9 L2 vibing: `command-runtime` is the new dropdown driving the
    // stdio command field. It needs to be in the dirty-tracking snapshot
    // so changing the dropdown alone (e.g. uvx → npx -y without typing in
    // the Custom field) marks the form dirty.
    var staticFields = ['name', 'type', 'command', 'command-runtime', 'cwd', 'url',
                        'sandbox-network-allowed'];
    for (var i = 0; i < staticFields.length; i++) {
      var el = container.querySelector('[data-field="' + staticFields[i] + '"]:not(.chip-list-editor)');
      if (el && el.type === 'checkbox') {
        staticData[staticFields[i]] = !!el.checked;
      } else {
        staticData[staticFields[i]] = el ? el.value : '';
      }
    }

    var chips = { args: [], 'sandbox-writable-paths': [] };
    if (helpers && helpers.readChipListValue) {
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      if (argsHost) chips.args = helpers.readChipListValue(argsHost);
      var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      if (sandboxPathsHost) chips['sandbox-writable-paths'] = helpers.readChipListValue(sandboxPathsHost);
    }

    var kvRows = [];
    var rowEls = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row');
    for (var j = 0; j < rowEls.length; j++) {
      var row = rowEls[j];
      var keyEl = row.querySelector('.kv-key-input');
      var valueEl = row.querySelector('.kv-value-input');
      var sensEl = row.querySelector('.kv-sensitive-checkbox');
      kvRows.push({
        key: keyEl ? keyEl.value : '',
        value: valueEl ? valueEl.value : '',
        sensitive: sensEl ? !!sensEl.checked : false
      });
    }

    return JSON.stringify({ static: staticData, chips: chips, kvRows: kvRows });
  }

  // ── Event wiring ────────────────────────────────────────────────────

  function wireEditorEvents(container, source, mcpTypes, callbacks) {
    var isEdit = !!source;
    var snapshot = getFormSnapshot(container);
    var dirty = false;
    var nextRowIdx = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row').length;

    // Every dirty report goes through here: the header's unsaved caption
    // (M25 F3 DD2, a stable span in the markup) follows the same value that
    // feeds studio's `dirty` through onDirtyChange.
    function reportDirty(d) {
      var unsavedEl = container.querySelector('.editor-unsaved');
      if (unsavedEl) unsavedEl.textContent = d ? 'Unsaved changes' : '';
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(d);
    }

    function checkDirty() {
      var current = getFormSnapshot(container);
      dirty = (current !== snapshot);
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = !dirty;
      // Edit mode only: the create form's Cancel (abandon, DD8) stays enabled.
      if (cancelBtn) cancelBtn.disabled = isEdit && !dirty;
      reportDirty(dirty);
    }

    function recaptureSnapshot() {
      snapshot = getFormSnapshot(container);
      dirty = false;
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = true;
      if (cancelBtn) cancelBtn.disabled = isEdit;
      reportDirty(false);
    }

    // ── Static field listeners ────────────────────────────────────────
    function attachStaticListeners() {
      var inputs = container.querySelectorAll('.editor-section .field-input:not(.kv-key-input):not(.kv-value-input), .editor-section .field-select');
      for (var i = 0; i < inputs.length; i++) {
        // Skip chip-list elements (handled via wireChipLists).
        if (inputs[i].classList.contains('chip-list-editor')) continue;
        if (inputs[i].classList.contains('chip-list-input')) continue;
        inputs[i].addEventListener('input', checkDirty);
        inputs[i].addEventListener('change', checkDirty);
      }
    }
    attachStaticListeners();

    // Chip-list onChange bridges
    wireChipLists(container, checkDirty);

    // ── Type-change handler ───────────────────────────────────────────
    var typeSelect = container.querySelector('[data-field="type"]');
    var runtimeSelect = container.querySelector('[data-field="command-runtime"]');
    if (typeSelect) {
      typeSelect.addEventListener('change', function () {
        applyTransportVisibility(container, typeSelect.value);
        // F9 L2 vibing: applyTransportVisibility blindly toggles the
        // `is-hidden` class on every `.mcp-stdio-only` row based on the
        // selected transport. The Custom-command row is also gated by
        // the runtime dropdown's state (Custom… vs canonical literal),
        // so a transport-switch into stdio would otherwise reveal the
        // Custom row even when the dropdown is on `uvx`. Re-sync here.
        if (typeSelect.value === 'stdio' && runtimeSelect) {
          applyStdioRuntimeSelection(container, runtimeSelect.value);
        }
        // checkDirty already wired via static listener above.
      });
    }

    // ── F9 L2 vibing: stdio command-runtime dropdown change handler ──
    // Toggles the Custom-command free-text row visibility + swaps the
    // helper-text under the args chip-list. checkDirty is already wired
    // via attachStaticListeners (the dropdown carries .field-select), so
    // we don't re-wire that here.
    if (runtimeSelect) {
      runtimeSelect.addEventListener('change', function () {
        applyStdioRuntimeSelection(container, runtimeSelect.value);
      });
    }

    // ── kv table delegated events + Add-row button ────────────────────
    mcpEditor.envHeaders.wire(container, checkDirty);


    // ── Cancel ────────────────────────────────────────────────────────
    // Edit mode reverts in place; create mode hands over to onCancel (the
    // orchestrator discards and returns to the section root). The create
    // form's Cancel is enabled from first render, so onCancel runs on a
    // pristine form as well as a dirty one.
    var cancelBtn = container.querySelector('.cancel-btn');
    // Focus after an in-place action (M25 F6 L1b, DD2): the title is re-resolved
    // when the focus timer fires.
    function titleEl() { return container.querySelector('.editor-title'); }
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        if (isEdit) {
          var cancelTok = App.focusAfter.begin(cancelBtn);
          revertEditorToSource(container, source, callbacks);
          // Re-bind delegated/static listeners that depend on snapshot/dirty
          // tracking — note: kv table itself was rebuilt; the table's
          // delegated listeners are still attached to the same .mcp-kv-table
          // element (we did innerHTML on the section, NOT replaceChild on
          // the table) — but to be safe, re-acquire references.
          // Actually we replace the tbody contents in-place.
          recaptureSnapshot();
          App.focusAfter.restore(cancelTok, titleEl);
        } else if (callbacks.onCancel) {
          callbacks.onCancel();
        }
      });
    }

    // ── Save ──────────────────────────────────────────────────────────
    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        var errorEl = container.querySelector('.editor-error');
        if (errorEl) errorEl.textContent = '';
        var payload = collectFormData(container, source, isEdit);
        if (!payload) return;
        var saveTok = App.focusAfter.begin(saveBtn);
        var url = isEdit ? '/api/mcp-sources/' + encodeURIComponent(source.id) : '/api/mcp-sources';
        var method = isEdit ? 'PUT' : 'POST';
        fetch(url, {
          method: method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
          .then(function (r) {
            if (!r.ok) {
              // F9 L2 vibing: read body as text first, then try JSON. A
              // proper FastAPI error response is JSON {detail: ...}; a
              // catastrophic 5xx (handler raised before our envelope) is
              // HTML and would choke r.json() with "Unexpected token <".
              return r.text().then(function (body) {
                var detail;
                try {
                  var parsed = JSON.parse(body);
                  detail = parsed && parsed.detail;
                } catch (_) {
                  // Non-JSON body — fall through to status-based message.
                }
                if (Array.isArray(detail)) {
                  // Pydantic ValidationError shape
                  detail = detail.map(function (d) {
                    var loc = (d.loc || []).join('.');
                    return loc ? (loc + ': ' + d.msg) : d.msg;
                  }).join(' | ');
                }
                if (!detail) {
                  var snippet = (body || '').trim().slice(0, 500);
                  detail = 'Server error ' + r.status + ' ' + r.statusText +
                           (snippet ? ': ' + snippet : '');
                }
                throw new Error(detail || (isEdit ? 'Save failed' : 'Create failed'));
              });
            }
            return r.json();
          })
          .then(function (updated) {
            // The Library list shows the source (DD9). Invalidated BEFORE
            // onSaveSuccess, whose router sync names the new item.
            App.store.invalidate('mcp-sources');
            window.App.showFlash(container, isEdit ? 'MCP Server saved' : 'MCP Server created');
            // Create mounts the saved editor asynchronously (the orchestrator's
            // `ready` promise): park the restore for its mount to flush.
            if (!isEdit) App.focusAfter.defer(saveTok, titleEl);
            if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, !isEdit);
            if (isEdit) {
              // Edit→edit: refresh snapshot from the masked response so
              // subsequent typing dirties from the post-save baseline.
              snapshot = getFormSnapshot(container);
              dirty = false;
              if (saveBtn) saveBtn.disabled = true;
              var c2 = container.querySelector('.cancel-btn');
              if (c2) c2.disabled = true;
              reportDirty(false);
              // Squawk 0126: the title follows the saved row (a rename).
              var t2 = titleEl();
              if (t2 && updated && updated.name) t2.textContent = updated.name;
              App.focusAfter.restore(saveTok, titleEl);
            }
          })
          .catch(function (err) {
            if (errorEl) errorEl.textContent = err.message || String(err);
            App.focusAfter.defer(null);
            App.focusAfter.restore(saveTok, saveBtn);
          });
      });
    }

    // ── Test Connection (edit only, streamable-http only) ─────────────
    var testBtn = container.querySelector('[data-testid="mcp-test-connection"]');
    if (testBtn) {
      // F9 L1 (vibing follow-up): after a successful /test/connect (Phase A
      // ok OR Phase 2 ok after OAuth popup), refetch the source so any
      // OAuth-state-dependent UI (currently: the Reset button) reflects
      // the post-flow truth. Without this, a fresh OAuth grant via the
      // popup leaves source.oauth_active stale at the value captured on
      // editor mount, hiding the Reset button until the operator
      // reloads. Targeted DOM mutation keeps in-flight form edits intact
      // (a full re-render would clobber dirty form state).
      function onTestConnectSuccess() {
        // handleTestConnection invalidated 'mcp-sources' just before calling
        // this (the connect rewrote config._cache): the list reloads.
        if (callbacks.onListStale) callbacks.onListStale();
        fetch('/api/mcp-sources/' + encodeURIComponent(source.id))
          .then(function (r) { return r && r.ok ? r.json() : null; })
          .then(function (refreshed) {
            if (!refreshed) return;
            source.oauth_active = !!refreshed.oauth_active;
            syncResetButtonVisibility(container, source, mcpTypes, callbacks);
            // Squawk 0102: the refresh just rewrote config._cache server-side
            // (serverInfo, capabilities, instructions, ...) — repaint the
            // Server section from it. source.config._cache is deliberately
            // NOT overwritten in memory: hasOAuthState's cache-presence
            // fallback reads it, so syncing it would change Reset-button
            // visibility on later refreshes (outside this squawk's scope).
            syncServerInfoSection(container,
              (refreshed.config && refreshed.config._cache) || null);
          })
          .catch(function () { /* best-effort; UI stays consistent on next mount */ });
      }
      testBtn.addEventListener('click', function () {
        // F8 L4: pass a no-op error-clearer so collectFormData's
        // validation messages don't accidentally show up in the editor's
        // generic .editor-error div for the Test path; if validation
        // fails (missing name / type / url), the form data is null and
        // we fall through to the no-payload path which uses persisted
        // state — same behavior as before.
        var formData = collectFormData(container, source, true);
        // F9 L1 (vibing follow-up): the auto-run-after-create path
        // (studio.js onSaveSuccess) sets dataset.autoRun on the button
        // before dispatching click() — signal to handleTestConnection
        // that it must NOT open the OAuth popup automatically (the
        // user-gesture context from Save is no longer fresh). Cleared
        // after read so subsequent manual clicks behave normally.
        var autoRun = testBtn.dataset.autoRun === '1';
        if (autoRun) delete testBtn.dataset.autoRun;
        // The auto-run has no keyboard user behind it: no token, so it does not
        // supersede the create's parked focus restore.
        handleTestConnection(source.id, container, testBtn, formData,
          onTestConnectSuccess, {
            noAutoPopup: autoRun,
            focusTok: autoRun ? null : App.focusAfter.begin(testBtn)
          });
      });
    }

    // ── Delete (edit only) ────────────────────────────────────────────
    var deleteBtn = container.querySelector('.delete-btn');
    if (deleteBtn && isEdit) {
      function doDelete(btn, revertFn) {
        fetch('/api/mcp-sources/' + encodeURIComponent(source.id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error((e && e.detail) || 'Delete failed'); });
            App.store.invalidate('mcp-sources');
            App.store.invalidate('agents');
            window.App.showFlash(container, 'MCP Server deleted');
            if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
          })
          .catch(function (err) {
            revertFn();
            window.App.showFlash(container, 'Error: ' + err.message, true);
          });
      }
      deleteBtn.addEventListener('click', function () {
        // L6: NO agent-usage pre-gate (F4 lands per-agent attachments).
        // Bare confirmDelete two-step.
        window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
      });
    }

    // ── Reset connection (edit only, streamable-http with OAuth state) ─
    // F9 L1 (vibing): clears tokens + DCR + tools cache server-side and
    // re-renders the editor from the response shape so the Tools section
    // collapses to empty-state and the button itself hides (no more
    // OAuth state to reset). On error, surfaces via showFlash.
    if (isEdit) {
      wireResetButton(container, source, mcpTypes, callbacks);
    }
  }
  // ── Cancel-revert: rebuild kv-table + chip-lists from source ────────

  function revertEditorToSource(container, source, callbacks) {
    /* In edit mode, revert the form to the source object. Static fields
       restore via a value-loop; the kv-table rebuilds from source (its
       row count can change during edit); chip-list editors re-mount
       fresh. */
    if (!source) return;

    // 1. Static fields
    // F9 L2 vibing: derive the command-runtime dropdown value + the
    // free-text Custom… field's value from the saved (command, args)
    // pair. `command` (free-text) is only populated when the saved
    // command falls into Custom… — for the canonical runtimes the
    // Custom row is hidden and its value is empty.
    var savedCmd = (source.config && source.config.command) || '';
    var savedArgs = (source.config && source.config.args) || [];
    var sel = deriveStdioRuntimeSelection(savedCmd, savedArgs);
    var staticMap = {
      'name': source.name || '',
      'type': source.type || '',
      'command-runtime': sel.dropdownValue || '',
      'command': sel.customCommand || '',
      'cwd': (source.config && source.config.cwd) || '',
      'url': (source.config && source.config.url) || ''
    };
    Object.keys(staticMap).forEach(function (key) {
      var el = container.querySelector('[data-field="' + key + '"]:not(.chip-list-editor)');
      if (el) el.value = staticMap[key];
    });
    // Sync the Custom-row visibility + helper-text to the restored
    // dropdown selection.
    applyStdioRuntimeSelection(container, sel.dropdownValue || '');
    // F3 L5b: sandbox-network-allowed is a checkbox — its display state
    // is controlled by .checked, not .value. Pulled out of the loop above
    // so el.value = ... doesn't no-op the visible checked state.
    var sandboxNetEl = container.querySelector('[data-field="sandbox-network-allowed"]:not(.chip-list-editor)');
    if (sandboxNetEl) {
      sandboxNetEl.checked = !!(source.config && source.config.sandbox && source.config.sandbox.network_allowed === true);
    }

    // 2. Visibility
    applyTransportVisibility(container, source.type || '');

    // 3. KV table — rebuild tbody contents
    var tbody = container.querySelector('.mcp-kv-table tbody');
    if (tbody) {
      var rows = collectExistingKvRows(source, source.type || '');
      var html = '';
      for (var i = 0; i < rows.length; i++) {
        html += renderKvRow(rows[i], i);
      }
      tbody.innerHTML = html;
      updateKvHeadVisibility(container);
    }

    // 4. Chip-list editors — re-mount fresh
    var helpers = window.App.adminFormHelpers;
    if (helpers && helpers.renderChipListEditor) {
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      if (argsHost && argsHost.parentNode) {
        var wrapper = document.createElement('div');
        // F9 L2 vibing: use sel.displayArgs so the operator's chip-list
        // shows only their own args — the implicit `-y` for `npx -y` and
        // the implicit `run` for `pipx run` (option (b) split) stay in
        // the saved JSON but never surface as editable chips the
        // operator could accidentally remove.
        wrapper.innerHTML = helpers.renderChipListEditor('args', sel.displayArgs || [], null, { controlId: 'mf-args' });
        var newArgs = wrapper.firstChild;
        argsHost.parentNode.replaceChild(newArgs, argsHost);
        if (helpers.wireChipListEditor) {
          helpers.wireChipListEditor(newArgs, function () {
            // Note: this onChange fires before we have a recaptured snapshot;
            // the orchestrator's wireEditorEvents runs once per render and
            // captures dirty-tracking via its own checkDirty closure. After
            // a Cancel revert, we recaptureSnapshot externally.
          });
        }
      }
      // F3 L5b: sandbox writable_paths chip-list re-mount.
      var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      if (sandboxPathsHost && sandboxPathsHost.parentNode) {
        var wrapper3 = document.createElement('div');
        wrapper3.innerHTML = helpers.renderChipListEditor('sandbox-writable-paths',
          (source.config && source.config.sandbox && source.config.sandbox.writable_paths) || [],
          null, { controlId: 'mf-sandbox-writable-paths' });
        var newSandboxPaths = wrapper3.firstChild;
        sandboxPathsHost.parentNode.replaceChild(newSandboxPaths, sandboxPathsHost);
        if (helpers.wireChipListEditor) {
          helpers.wireChipListEditor(newSandboxPaths, function () { /* dirty-tracking handled externally */ });
        }
      }
    }
  }

  // ── Payload assembly ────────────────────────────────────────────────

  function collectFormData(container, source, isEdit) {
    /* Routes by `type` (NOT by visible-field set). A type-change
       immediately followed by Save emits the type-correct payload. */
    var errorEl = container.querySelector('.editor-error');
    var nameEl = container.querySelector('[data-field="name"]');
    var name = nameEl ? nameEl.value.trim() : '';
    if (!name) {
      if (errorEl) errorEl.textContent = 'Name is required.';
      return null;
    }
    var typeEl = container.querySelector('[data-field="type"]');
    var type = typeEl ? typeEl.value : '';
    if (!type) {
      if (errorEl) errorEl.textContent = 'Type is required.';
      return null;
    }

    var config = {};
    var secrets = {};

    if (type === 'stdio') {
      // F9 L2 vibing: command source is the dropdown selection. For all
      // canonical runtime literals except `npx -y` and `pipx run` the
      // dropdown value IS `config.command` verbatim. For `npx -y` we
      // split into `command=npx, args=[-y, ...userArgs]`; for `pipx run`
      // we split into `command=pipx, args=[run, ...userArgs]` (option
      // (b)) so the saved JSON stays transparent — and so the spawn
      // layer doesn't try to exec a 2-token string as a single binary
      // and FileNotFoundError. For Custom… the free-text input feeds
      // `config.command` directly (operator owns resolution).
      var runtimeEl = container.querySelector('[data-field="command-runtime"]');
      var runtimeValue = runtimeEl ? runtimeEl.value : '';
      var command = '';
      var prependArgs = [];
      if (runtimeValue === STDIO_CUSTOM_SENTINEL) {
        var customEl = container.querySelector('[data-field="command"]');
        command = customEl ? customEl.value.trim() : '';
      } else if (runtimeValue === 'npx -y') {
        command = 'npx';
        prependArgs = ['-y'];
      } else if (runtimeValue === 'pipx run') {
        command = 'pipx';
        prependArgs = ['run'];
      } else if (runtimeValue) {
        command = runtimeValue;
      }
      if (!command) {
        if (errorEl) errorEl.textContent = 'Command is required for stdio servers.';
        return null;
      }
      config.command = command;
      var cwdEl = container.querySelector('[data-field="cwd"]');
      var cwd = cwdEl ? cwdEl.value.trim() : '';
      if (cwd) config.cwd = cwd;
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      var helpers = window.App.adminFormHelpers;
      var userArgsList = (argsHost && helpers && helpers.readChipListValue) ? helpers.readChipListValue(argsHost) : [];
      var argsList = prependArgs.concat(userArgsList);
      if (argsList.length > 0) config.args = argsList;
      config.env = {};
      partitionKvRows(container, config.env, secrets);
      // F3 L5b: sandbox profile (stdio only). Always-emit precedent
      // matches config.env above: empty defaults are written explicitly,
      // not omitted. The L1b API validator accepts the default shape.
      var sandboxNetEl = container.querySelector('[data-field="sandbox-network-allowed"]');
      var networkAllowed = !!(sandboxNetEl && sandboxNetEl.checked);
      var sandboxPathsList = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      var writablePaths = (sandboxPathsList && helpers && helpers.readChipListValue) ? helpers.readChipListValue(sandboxPathsList) : [];
      config.sandbox = { network_allowed: networkAllowed, writable_paths: writablePaths };
    } else if (type === 'streamable-http') {
      var urlEl = container.querySelector('[data-field="url"]');
      var urlValue = urlEl ? urlEl.value.trim() : '';
      if (!urlValue) {
        if (errorEl) errorEl.textContent = 'URL is required for streamable-http servers.';
        return null;
      }
      config.url = urlValue;
      config.headers = {};
      partitionKvRows(container, config.headers, secrets);
    } else {
      if (errorEl) errorEl.textContent = 'Unsupported transport type: ' + type;
      return null;
    }

    return { name: name, type: type, config: config, secrets: secrets };
  }

  window.App.studio.renderMcpSourceEditor = renderMcpSourceEditor;
})();
