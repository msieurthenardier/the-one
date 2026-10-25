// App.studio.renderMcpSourceEditor — MCP source editor (M07 F1 L6;
// relocated from admin → studio post-F2 retrofit).
//
// Mirrors provider-editor.js structural shape:
//   <div class="editor-header"> … </div>
//   <div class="editor-section">Connection</div>          (name, type, transport-fields)
//   <div class="editor-section">Environment variables /
//                               Headers</div>             (the key-value table, DOM-built)
//   <div class="editor-section danger-zone"> … </div>     (edit only)
//
// The env and headers rows live in mcp-env-headers.js (M31 F5 L07): a key-value table
// with Key / Value / Sensitive columns. Sensitive=true rows route to `secrets[key]`;
// sensitive=false rows route to `config.env[key]` (stdio) or `config.headers[key]`
// (streamable-http). The per-key __MASKED__ round trip (a stored secret whose value is
// untouched sends the sentinel) is the module's partition(); this file only calls it.
//
// callbacks: { onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange,
//              onListStale, onMounted }
// Returns a controller {destroy, setBusy, setError, runTest} (M31 F5 L03) and
// reports it through callbacks.onMounted on every mount, Reset's re-mount
// included. A destroyed mount skips its DOM writes and mount-bound callbacks but
// still invalidates the store and calls onListStale for a server change that
// already happened (mcp-editor-lifecycle.js).
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
  var renderToolsListHtml = mcpEditor.serverInfo.renderToolsListHtml;
  var renderServerInfoSection = mcpEditor.serverInfo.renderServerInfoSection;
  var cacheHasServerInfo = mcpEditor.serverInfo.cacheHasServerInfo;
  var syncServerInfoSection = mcpEditor.serverInfo.syncServerInfoSection;
  var connectionFields = mcpEditor.connectionFields;
  var sandboxFields = mcpEditor.sandboxFields;
  var envHeadersFields = mcpEditor.envHeaders;
  var renderConnectionActions = mcpEditor.connectionStatus.renderConnectionActions;
  var wireResetButton = mcpEditor.connectionStatus.wireResetButton;
  var syncResetButtonVisibility = mcpEditor.connectionStatus.syncResetButtonVisibility;
  var handleTestConnection = mcpEditor.connectionStatus.handleTestConnection;
  var createMount = mcpEditor.lifecycle.createMount;

  // ── Public entry point ──────────────────────────────────────────────

  function renderMcpSourceEditor(container, source, mcpTypes, callbacks) {
    callbacks = callbacks || {};
    var mount = createMount();
    var handles = mount.handles;
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
    // The fields are DOM-built by connectionFields (M31 F5 L06); a host holds their place.
    html += '<div class="mcp-connection-host"></div>';
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
    html += '<div class="mcp-sandbox-host"></div>';

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
    // Sits below Tools for streamable-http (F9 L1 reorder); for stdio there is no
    // Tools section, so it lands right after Sandbox. DOM-built by envHeaders
    // (M31 F5 L07); a host holds its place.
    html += '<div class="mcp-env-headers-host"></div>';

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

    handles.container = container;
    // The late-bound dirty trampoline: checkDirty is defined in wireEditorEvents.
    var checkDirtyFn = null;
    function dirtyTrampoline() { if (checkDirtyFn) checkDirtyFn(); }
    var sandbox = sandboxFields.create({ source: source, onChange: dirtyTrampoline });
    var envHeaders = envHeadersFields.create({
      source: source, type: type, onChange: dirtyTrampoline
    });
    var connection = connectionFields.create({
      source: source, mcpTypes: mcpTypes, onChange: dirtyTrampoline,
      onTypeChange: function (t) {
        sandbox.setType(t);
        envHeaders.setType(t);
      }
    });
    var connHost = container.querySelector('.mcp-connection-host');
    connHost.parentNode.replaceChild(connection.el, connHost);
    var sandboxHost = container.querySelector('.mcp-sandbox-host');
    sandboxHost.parentNode.replaceChild(sandbox.el, sandboxHost);
    var envHost = container.querySelector('.mcp-env-headers-host');
    envHost.parentNode.replaceChild(envHeaders.el, envHost);
    handles.connectionFields = connection;
    handles.sandboxFields = sandbox;
    handles.envHeaders = envHeaders;
    sandbox.setType(type);
    mount.onDestroy(connection.destroy);
    mount.onDestroy(sandbox.destroy);
    mount.onDestroy(envHeaders.destroy);
    handles.testBtn = container.querySelector('[data-testid="mcp-test-connection"]');
    var api = wireEditorEvents(handles, source, mcpTypes, callbacks, mount, function (fn) {
      checkDirtyFn = fn;
    });
    var controller = {
      destroy: mount.destroy, setBusy: api.setBusy, setError: api.setError, runTest: api.runTest
    };
    if (callbacks.onMounted) callbacks.onMounted(controller);
    return controller;
  }

  // ── Form snapshot + dirty tracking ──────────────────────────────────

  // The fields' snapshot. The env and headers rows are not in it: the module keeps
  // its own baseline and reports through isDirty() (M31 F5 L07).
  function getFormSnapshot(handles) {
    return JSON.stringify({
      connection: handles.connectionFields.values(),
      sandbox: handles.sandboxFields.values()
    });
  }

  // ── Event wiring ────────────────────────────────────────────────────

  function wireEditorEvents(handles, source, mcpTypes, callbacks, mount, bindDirty) {
    var container = handles.container;
    var isEdit = !!source;
    var snapshot = getFormSnapshot(handles);
    var dirty = false;
    var busy = false;

    // Every dirty report goes through here: the header's unsaved caption
    // (M25 F3 DD2, a stable span in the markup) follows the same value that
    // feeds studio's `dirty` through onDirtyChange.
    function reportDirty(d) {
      var unsavedEl = container.querySelector('.editor-unsaved');
      if (unsavedEl) unsavedEl.textContent = d ? 'Unsaved changes' : '';
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(d);
    }

    // Save and Cancel follow the dirty flag and the controller's busy flag.
    // Edit mode only: the create form's Cancel (abandon, DD8) stays enabled.
    function applyButtons() {
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = busy || !dirty;
      if (cancelBtn) cancelBtn.disabled = busy || (isEdit && !dirty);
    }

    function checkDirty() {
      dirty = (getFormSnapshot(handles) !== snapshot) || handles.envHeaders.isDirty();
      applyButtons();
      reportDirty(dirty);
    }

    bindDirty(checkDirty);

    // The fields' snapshot is retaken; the env and headers rows keep their own baseline
    // (revert() and remaskAfterSave() have already settled it), so an edit made to a row
    // while a Save was in flight stays dirty.
    function recaptureSnapshot() {
      snapshot = getFormSnapshot(handles);
      dirty = handles.envHeaders.isDirty();
      applyButtons();
      reportDirty(dirty);
    }

    function setError(msg) {
      var el = container.querySelector('.editor-error');
      if (el) el.textContent = msg || '';
    }

    // The mount reports its initial clean state once.
    if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);

    // ── Field listeners ───────────────────────────────────────────────
    // None here: connectionFields, sandboxFields and envHeaders report their own
    // changes through the trampoline (onChange).

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
        if (!mount.alive()) return;
        if (isEdit) {
          var cancelTok = App.focusAfter.begin(cancelBtn);
          revertEditorToSource(handles, source, callbacks);
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
        if (!mount.alive()) return;
        setError('');
        var payload = collectFormData(handles, source, isEdit);
        if (!payload) return;
        // What this click sent per row, for the re-mask and the post-Save baseline.
        var submitted = handles.lastPartition;
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
            // A Save that lands after destroy still saved on the server: the
            // list follows, the dead editor is not touched.
            if (!mount.alive()) { if (callbacks.onListStale) callbacks.onListStale(); return; }
            window.App.showFlash(container, isEdit ? 'MCP Server saved' : 'MCP Server created');
            // Create mounts the saved editor asynchronously (the orchestrator's
            // `ready` promise): park the restore for its mount to flush.
            if (!isEdit) App.focusAfter.defer(saveTok, titleEl);
            if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, !isEdit);
            if (isEdit) {
              // Edit→edit (M31 F5 L07): re-mask the secrets the server now holds, then
              // retake the fields' snapshot; the form stays dirty only for an edit made
              // while the PUT was in flight.
              handles.envHeaders.remaskAfterSave(submitted, updated);
              recaptureSnapshot();
              // Squawk 0126: the title follows the saved row (a rename).
              var t2 = titleEl();
              if (t2 && updated && updated.name) t2.textContent = updated.name;
              App.focusAfter.restore(saveTok, titleEl);
            }
          })
          .catch(function (err) {
            if (!mount.alive()) return;
            setError(err.message || String(err));
            App.focusAfter.defer(null);
            App.focusAfter.restore(saveTok, saveBtn);
          });
      });
    }

    // ── Test Connection (edit only, streamable-http only) ─────────────
    var testBtn = handles.testBtn;
    var runTest = function () {};
    if (testBtn) {
      // F9 L1 (vibing follow-up): after a successful /test/connect (Phase A
      // ok OR Phase 2 ok after OAuth popup), refetch the source so the
      // OAuth-state-dependent UI (the Reset button) reflects the post-flow
      // truth, by targeted DOM mutation that keeps in-flight edits intact.
      function onTestConnectSuccess() {
        // handleTestConnection invalidated 'mcp-sources' just before calling
        // this (the connect rewrote config._cache): the list reloads.
        if (callbacks.onListStale) callbacks.onListStale();
        if (!mount.alive()) return;
        fetch('/api/mcp-sources/' + encodeURIComponent(source.id))
          .then(function (r) { return r && r.ok ? r.json() : null; })
          .then(function (refreshed) {
            if (!refreshed || !mount.alive()) return;
            source.oauth_active = !!refreshed.oauth_active;
            syncResetButtonVisibility(container, source, mcpTypes, callbacks, mount);
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
      // The one entry for a Test click and the glue's auto-run after create
      // ({autoRun: true}: the Save click's user gesture is gone, so
      // handleTestConnection must NOT open the OAuth popup; there is no keyboard
      // user behind it, so no focus token and the create's parked restore stands).
      // A defined no-op while Test is disabled or a sign-in session is live.
      runTest = function (opts) {
        if (!mount.alive() || testBtn.disabled || mount.sessionActive()) return;
        var autoRun = !!(opts && opts.autoRun);
        // Leg 08a (DD6): the dirty check comes first. A clean form posts NO body, so
        // the server tests (and records) the saved server and collectFormData, which
        // validates and writes .editor-error, is not called at all. A dirty form
        // sends its values, as before; validation failures give null form data, so
        // that Test falls back to the persisted state. The server never records a
        // body-ful Test as the saved server's last check.
        var formDirty = (getFormSnapshot(handles) !== snapshot) || handles.envHeaders.isDirty();
        var formData = formDirty ? collectFormData(handles, source, true) : null;
        handleTestConnection(source.id, container, testBtn, formData,
          onTestConnectSuccess, {
            noAutoPopup: autoRun, mount: mount,
            // Fired once for an error / auth_required outcome (an ok goes through
            // onTestConnectSuccess, which calls it): the list's record changed.
            onListStale: callbacks.onListStale,
            focusTok: autoRun ? null : App.focusAfter.begin(testBtn)
          });
      };
      testBtn.addEventListener('click', function () { runTest({}); });
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
            // A late Delete drops the row but never closes the open item.
            if (!mount.alive()) { if (callbacks.onListStale) callbacks.onListStale(); return; }
            window.App.showFlash(container, 'MCP Server deleted');
            if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
          })
          .catch(function (err) {
            if (!mount.alive()) return;
            revertFn();
            window.App.showFlash(container, 'Error: ' + err.message, true);
          });
      }
      deleteBtn.addEventListener('click', function () {
        window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
      });
    }

    // ── Reset connection (edit only): clears tokens + DCR + tools cache
    // server-side and re-mounts from the response (connection-status.js).
    if (isEdit) {
      wireResetButton(container, source, mcpTypes, callbacks, mount);
    }

    return {
      setBusy: function (b) { busy = !!b; applyButtons(); },
      setError: setError,
      runTest: function (opts) { runTest(opts); }
    };
  }

  // ── Cancel-revert ────────────────────────────────────────────────────

  function revertEditorToSource(handles, source, callbacks) {
    /* In edit mode, revert the form: the fields to the source object (until leg 10
       gives them a baseline of their own), the env and headers rows to their module
       baseline (the last saved rows). */
    if (!source) return;

    // 1. Fields: written through their handles, silently (the caller recaptures the
    //    snapshot); setValues also shows the rows for the stored type.
    handles.connectionFields.setValues(source);
    handles.sandboxFields.setValues(source);
    handles.sandboxFields.setType(source.type || '');

    // 2. The env and headers rows: the label follows the stored type, then the rows go
    //    back to the module's baseline (the last saved rows).
    handles.envHeaders.setType(source.type || '');
    handles.envHeaders.revert();
  }

  // ── Payload assembly ────────────────────────────────────────────────

  function collectFormData(handles, source, isEdit) {
    var container = handles.container;
    /* Routes by `type` (NOT by visible-field set). A type-change
       immediately followed by Save emits the type-correct payload. */
    var errorEl = container.querySelector('.editor-error');
    var fv = handles.connectionFields.values();
    var name = fv.name.trim();
    if (!name) {
      if (errorEl) errorEl.textContent = 'Name is required.';
      return null;
    }
    var type = fv.type;
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
      var runtimeValue = fv.runtime;
      var command = '';
      var prependArgs = [];
      if (runtimeValue === STDIO_CUSTOM_SENTINEL) {
        command = fv.command.trim();
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
      var cwd = fv.cwd.trim();
      if (cwd) config.cwd = cwd;
      var argsList = prependArgs.concat(fv.args);
      if (argsList.length > 0) config.args = argsList;
      config.env = {};
      handles.lastPartition = handles.envHeaders.partition(config.env, secrets);
      // F3 L5b: sandbox profile (stdio only). Always-emit precedent
      // matches config.env above: empty defaults are written explicitly,
      // not omitted. The L1b API validator accepts the default shape.
      var sv = handles.sandboxFields.values();
      config.sandbox = { network_allowed: sv.networkAllowed, writable_paths: sv.writablePaths };
    } else if (type === 'streamable-http') {
      var urlValue = fv.url.trim();
      if (!urlValue) {
        if (errorEl) errorEl.textContent = 'URL is required for streamable-http servers.';
        return null;
      }
      config.url = urlValue;
      config.headers = {};
      handles.lastPartition = handles.envHeaders.partition(config.headers, secrets);
    } else {
      if (errorEl) errorEl.textContent = 'Unsupported transport type: ' + type;
      return null;
    }

    return { name: name, type: type, config: config, secrets: secrets };
  }

  window.App.studio.renderMcpSourceEditor = renderMcpSourceEditor;
})();
