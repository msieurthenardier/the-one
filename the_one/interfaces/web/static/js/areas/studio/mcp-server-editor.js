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
// reports it through callbacks.onMounted on every mount (Reset and Forget patch in place
// since M31 F5 L08b and no longer re-mount). A destroyed mount skips its DOM writes and mount-bound callbacks but
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
  var serverInfoModule = mcpEditor.serverInfo;
  var connectionFields = mcpEditor.connectionFields;
  var sandboxFields = mcpEditor.sandboxFields;
  var envHeadersFields = mcpEditor.envHeaders;
  var connectionStatus = mcpEditor.connectionStatus;
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
    // M31 F5 L08b: the status line, its result area and Reset / Forget are built by
    // connectionStatus.create and replace this host after the markup is in place (edit
    // mode of an HTTP or stdio source). Test is the header button, added below.
    var hasConnection = !isCreate && source &&
      (source.type === 'streamable-http' || source.type === 'stdio');
    if (hasConnection) html += '<div class="mcp-connection-status-host"></div>';
    html += '</div>';

    // ── Sandbox section (stdio only) ──────────────────────────────────
    html += '<div class="mcp-sandbox-host"></div>';

    // ── Server and Tools sections (edit only, streamable-http + stdio) ──
    // DOM-built by serverInfo.create (M31 F5 L09) and placed over these hosts: the Server
    // section (identity, protocol, offers, instructions, metadata; hidden while the cache
    // has nothing to show) above Tools. The cached tools render on mount; a successful
    // Test reconciles them, Reset and Forget empty them (connectionStatus). The Test
    // result line is not here: it sits at the end of the Connection section (A8).
    if (hasConnection) {
      html += '<div class="mcp-info-host"></div>';
      html += '<div class="mcp-tools-host"></div>';
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
    // Test (B2): edit mode only, in the header cluster before Cancel, as the provider
    // editor has it. Leg 10 moves it to editorShell's actions.test (setTestState).
    // The controller's current source, replaced by the response of a Save in leg 10.
    var current = source;
    var connStatus = null;
    var api = null;
    var serverInfo = null;
    if (hasConnection) {
      serverInfo = serverInfoModule.create({ cache: (source.config && source.config._cache) || null });
      var infoHost = container.querySelector('.mcp-info-host');
      infoHost.parentNode.replaceChild(serverInfo.serverEl, infoHost);
      var toolsHost = container.querySelector('.mcp-tools-host');
      toolsHost.parentNode.replaceChild(serverInfo.toolsEl, toolsHost);
      mount.onDestroy(serverInfo.destroy);
      var testBtn = App.ui.button({
        label: 'Test', icon: 'play', variant: 'secondary', testid: 'mcp-test-connection'
      });
      var cancelEl = container.querySelector('.cancel-btn');
      cancelEl.parentNode.insertBefore(testBtn, cancelEl);
      handles.testBtn = testBtn;
      connStatus = connectionStatus.create({
        container: container, mount: mount, callbacks: callbacks, testBtn: testBtn,
        serverInfo: serverInfo,
        getSource: function () { return current; },
        // wireEditorEvents' setError and the title lookup, bound once it exists.
        setError: function (msg) { if (api) api.setError(msg); },
        titleEl: function () { return api ? api.titleEl() : null; }
      });
      var statusHost = container.querySelector('.mcp-connection-status-host');
      statusHost.parentNode.replaceChild(connStatus.el, statusHost);
    }
    api = wireEditorEvents(handles, source, mcpTypes, callbacks, mount, connStatus,
      function (fn) { checkDirtyFn = fn; });
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

  function wireEditorEvents(handles, source, mcpTypes, callbacks, mount, connStatus, bindDirty) {
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

    // ── Test (edit only) ──────────────────────────────────────────────
    var testBtn = handles.testBtn;
    var runTest = function () {};
    if (testBtn) {
      // The one entry for a Test click and the glue's auto-run after create
      // ({autoRun: true}: the Save click's user gesture is gone, so the flow must NOT
      // open the OAuth popup; there is no keyboard user behind it, so no focus token and
      // the create's parked restore stands). A defined no-op while Test is disabled or a
      // sign-in session is live.
      runTest = function (opts) {
        if (!mount.alive() || testBtn.disabled || mount.sessionActive()) return;
        var autoRun = !!(opts && opts.autoRun);
        // Leg 08a (DD6): the dirty check comes first. A clean form posts NO body, so the
        // server tests (and records) the saved server and collectFormData is not called.
        // A dirty form sends its values (the server never records a body-ful Test); a
        // form that cannot be sent (defect 9) says why in the result area and sends
        // nothing: a body-less fallback would record against the saved server.
        var formDirty = (getFormSnapshot(handles) !== snapshot) || handles.envHeaders.isDirty();
        var form = null;
        if (formDirty) {
          form = collectFormData(handles, source, true, { silent: true });
          if (form.error) { connStatus.showInvalid(form.error); return; }
        }
        connStatus.runTest(form, {
          noAutoPopup: autoRun,
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

    return {
      setBusy: function (b) {
        busy = !!b;
        handles.busy = busy;
        applyButtons();
        // Test is blocked while a Save is in flight (DD4); a running Test or a sign-in
        // session keeps it disabled on its own.
        if (testBtn && !(connStatus && connStatus.isTesting()) && !mount.sessionActive()) {
          testBtn.disabled = busy;
        }
      },
      setError: setError,
      titleEl: titleEl,
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

  // opts.silent (M31 F5 L08b, defect 9): a form that cannot be sent returns {error}
  // and writes nothing into the editor error (a Test shows it in its result area);
  // without it, the message goes to the editor error and the result is null.
  function collectFormData(handles, source, isEdit, opts) {
    var container = handles.container;
    var silent = !!(opts && opts.silent);
    /* Routes by `type` (NOT by visible-field set). A type-change
       immediately followed by Save emits the type-correct payload. */
    var errorEl = silent ? null : container.querySelector('.editor-error');
    var fail = function (message) {
      if (errorEl) errorEl.textContent = message;
      return silent ? { error: message } : null;
    };
    var fv = handles.connectionFields.values();
    var name = fv.name.trim();
    if (!name) return fail('Name is required.');
    var type = fv.type;
    if (!type) return fail('Type is required.');

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
      if (!command) return fail('Command is required for stdio servers.');
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
      if (!urlValue) return fail('URL is required for streamable-http servers.');
      config.url = urlValue;
      config.headers = {};
      handles.lastPartition = handles.envHeaders.partition(config.headers, secrets);
    } else {
      return fail('Unsupported transport type: ' + type);
    }

    return { name: name, type: type, config: config, secrets: secrets };
  }

  window.App.studio.renderMcpSourceEditor = renderMcpSourceEditor;
})();
