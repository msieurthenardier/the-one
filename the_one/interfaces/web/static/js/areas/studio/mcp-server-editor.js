// App.studio.renderMcpSourceEditor — MCP source editor (M07 F1 L6;
// relocated from admin → studio post-F2 retrofit; rebuilt on the control library in
// M31 F5 L10).
//
// One controller per mount, built from App.ui.editorShell, App.ui.section and
// App.ui.dangerZone (no HTML string anywhere):
//   editorShell   breadcrumb "Library / MCP servers", the title, the subtitle
//                 ("{type label} · {command or URL}", testid mcp-editor-subtitle), the
//                 unsaved caption, Cancel, Save, Test (edit mode of a stdio or
//                 streamable-http source only) and the editor error (role=alert)
//   section       Connection (the fields, then the status line), the env and headers,
//                 Sandbox, Server, Tools (B1's order; each module keeps its own
//                 visibility rule), then the dangerZone (edit mode)
// The env and headers rows live in mcp-env-headers.js: Sensitive=true rows route to
// `secrets[key]`, the others to `config.env[key]` (stdio) or `config.headers[key]`
// (streamable-http). The per-key __MASKED__ round trip is the module's partition() and
// remaskAfterSave(); this file only calls them.
//
// callbacks: { onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange,
//              onListStale, onMounted }
// Returns a controller {destroy, setBusy, setError, runTest} and reports it through
// callbacks.onMounted on every mount. A destroyed mount skips its DOM writes and
// mount-bound callbacks but still invalidates the store and calls onListStale for a
// server change that already happened (mcp-editor-lifecycle.js).
//
// The save model (DD4):
//   * Save and Create go through App.api.fetchJson and are busy (shell.setBusy) until the
//     response; a create stays busy until the glue's remount replaces the editor.
//   * `current` is the last SAVED row, replaced from an edit Save's response BEFORE the
//     env and headers re-mask. Cancel reverts to it, the status line and the server
//     info read it, and the fields' dirty baseline is baselineFrom(current).
//   * The fields stay editable during a Save. If none was edited meanwhile, the saved row
//     is written back through setValues (which normalises); otherwise the DOM is left as
//     the operator has it and the edited field stays dirty.
//   * Field errors (A2) go on the field, the rest on the editor error, per Flight 4 DD3.
//   * Test's disabled state and label have ONE writer, syncTestHold(), through the
//     shell's setTestState; the shell ORs busy into it.
// onListStale (M25 F3 L4a) fires after each 'mcp-sources' invalidation that is not a save
// or delete: a connect success (a Test, the auto-run after create, Phase 2 after sign-in)
// and Reset connection. Both rewrite config._cache server-side, so the Library list's tool
// count is stale; the caller reloads the list.
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

  var WAITING_LABEL = 'Waiting for sign-in…';
  // The connection fields in DOM order (the first error takes focus).
  var FIELD_ORDER = ['name', 'type', 'runtime', 'command', 'cwd', 'args', 'url'];
  // The names a server 422 `loc` can pick (the runtime row has no server field).
  var SERVER_FIELDS = ['name', 'type', 'command', 'url', 'cwd', 'args'];

  function cacheOf(source) {
    return (source && source.config && source.config._cache) || null;
  }

  // ── Public entry point ──────────────────────────────────────────────

  function renderMcpSourceEditor(container, source, mcpTypes, callbacks) {
    callbacks = callbacks || {};
    var mount = createMount();
    var handles = mount.handles;
    var isCreate = !source;
    var type = isCreate ? '' : (source.type || '');
    // The controller's current source: the last SAVED row (replaced by an edit Save).
    var current = source;
    var hasConnection = !isCreate && (type === 'streamable-http' || type === 'stdio');
    var snapshot = '';
    var saving = false;
    var connStatus = null;
    var serverInfo = null;
    var shell = null;
    var danger = null;
    var dirtyFn = function () { checkDirty(); };
    // The key a GleepGlorp fill and an approval's follow address this editor by.
    var openKey = isCreate ? 'create' : 'edit:' + source.id;
    var idleWaiters = [];
    var fillApi = null;

    // ── The modules ─────────────────────────────────────────────────────
    var sandbox = sandboxFields.create({ source: source, onChange: dirtyFn });
    var envHeaders = envHeadersFields.create({ source: source, type: type, onChange: dirtyFn });
    var connection = connectionFields.create({
      source: source, mcpTypes: mcpTypes, onChange: dirtyFn,
      onTypeChange: function (t) {
        sandbox.setType(t);
        envHeaders.setType(t);
        // The table was rebuilt: its note is drawn again (it follows the rows, which stay).
        if (fillApi) fillApi.redraw();
      }
    });
    handles.container = container;
    handles.connectionFields = connection;
    handles.sandboxFields = sandbox;
    handles.envHeaders = envHeaders;
    sandbox.setType(type);
    mount.onDestroy(connection.destroy);
    mount.onDestroy(sandbox.destroy);
    mount.onDestroy(envHeaders.destroy);

    // ── The subtitle (A4, defect 12) ────────────────────────────────────
    function typeLabel(t) {
      for (var i = 0; i < (mcpTypes || []).length; i++) {
        if (mcpTypes[i].value === t) return mcpTypes[i].label;
      }
      return t || '';
    }
    // "{type label} · {command or URL}"; the label alone without a detail; a type with no
    // label (a legacy row) falls back to the raw type.
    function subtitleFor(src) {
      if (!src) return '';
      var t = src.type || '';
      var cfg = src.config || {};
      var detail = t === 'stdio' ? cfg.command : (t === 'streamable-http' ? cfg.url : '');
      var label = typeLabel(t);
      return detail ? (label + ' · ' + detail) : label;
    }
    function titleFor(src) { return (src && src.name) || 'MCP server'; }

    // ── The shell ───────────────────────────────────────────────────────
    // Created first, with the Test click a late-bound closure: connectionStatus needs the
    // shell's Test button, and the shell needs runTest.
    shell = App.ui.editorShell({
      breadcrumb: {
        label: 'Library', href: App.router.href({ destination: 'library' }),
        trail: ' / MCP servers'
      },
      title: isCreate ? 'New MCP server' : titleFor(source),
      subtitle: isCreate ? undefined : subtitleFor(source),
      subtitleTestid: 'mcp-editor-subtitle',
      errorRole: 'alert',
      actions: {
        // Cancel on the create form abandons creation (DD8), so it is enabled from the
        // first render; in edit mode it reverts and is enabled only while dirty.
        cancel: { testid: 'cancel-mcp-source-btn', onClick: performCancel, enabledWhenClean: isCreate },
        save: { label: isCreate ? 'Create' : 'Save', testid: 'save-mcp-source-btn', onClick: performSave },
        test: hasConnection ? { testid: 'mcp-test-connection', onClick: function () { runTest({}); } } : undefined
      }
    });

    // ── The Test hold: the ONE writer of Test's state ───────────────────
    function syncTestHold() {
      if (!mount.alive() || !shell.testButton) return;
      var session = mount.sessionActive();
      var hold = (connStatus && connStatus.isTesting()) || session;
      shell.setTestState(hold ? { disabled: true, label: session ? WAITING_LABEL : null } : null);
    }
    mount.onSessionChange(syncTestHold);

    // ── Server info and the status line (edit mode, stdio or HTTP) ──────
    if (hasConnection) {
      serverInfo = serverInfoModule.create({ cache: cacheOf(source) });
      mount.onDestroy(serverInfo.destroy);
      connStatus = connectionStatus.create({
        container: container, mount: mount, callbacks: callbacks, testBtn: shell.testButton,
        serverInfo: serverInfo,
        getSource: function () { return current; },
        setError: function (msg) { if (mount.alive()) shell.setError(msg); },
        titleEl: function () { return shell.titleEl; },
        onTestHoldChange: syncTestHold
      });
    }

    // ── The sections, in B1's order ─────────────────────────────────────
    var connectionSection = App.ui.section({
      title: 'Connection', children: [connection.el, connStatus && connStatus.el]
    });
    var frag = document.createDocumentFragment();
    frag.appendChild(shell.el);
    frag.appendChild(connectionSection.el);
    frag.appendChild(envHeaders.el);
    frag.appendChild(sandbox.el);
    if (serverInfo) {
      frag.appendChild(serverInfo.serverEl);
      frag.appendChild(serverInfo.toolsEl);
    }
    if (!isCreate) {
      danger = App.ui.dangerZone({
        action: {
          label: 'Delete MCP server', testid: 'delete-mcp-source-btn',
          dataset: { name: source.name || '' },
          onConfirm: function (revert) { performDelete(revert); }
        }
      });
      frag.appendChild(danger.el);
    }
    container.replaceChildren(frag);

    // ── Dirty tracking ──────────────────────────────────────────────────
    function baselineSnapshot() {
      return JSON.stringify({
        connection: connection.baselineFrom(current), sandbox: sandbox.baselineFrom(current)
      });
    }
    function valuesSnapshot() {
      return JSON.stringify({ connection: connection.values(), sandbox: sandbox.values() });
    }
    function isDirty() {
      return valuesSnapshot() !== snapshot || envHeaders.isDirty();
    }
    function reportDirty(d) {
      shell.setDirty(d);
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(d);
    }
    function checkDirty() {
      if (!mount.alive()) return;
      reportDirty(isDirty());
    }
    snapshot = baselineSnapshot();
    shell.setDirty(false);
    // The mount reports its initial clean state once.
    if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);

    // Focus after an in-place action (M25 F6 L1b, DD2): the title is re-resolved when the
    // focus timer fires (a create's restore resolves the NEW mount's title: the editor's one h1).
    function titleNow() { return container.querySelector('h1'); }

    // ── Cancel ──────────────────────────────────────────────────────────
    // Edit mode reverts in place to the last SAVED row (defect 3); create mode hands over
    // to onCancel (the orchestrator discards and returns to the section root).
    function performCancel() {
      if (!mount.alive()) return;
      if (isCreate) {
        if (callbacks.onCancel) callbacks.onCancel();
        return;
      }
      var cancelTok = App.focusAfter.begin(shell.cancelButton);
      clearNotes();
      applySaved(current);
      envHeaders.setType(current.type || '');
      envHeaders.revert();
      connection.clearErrors();
      shell.setError('');
      snapshot = baselineSnapshot();
      reportDirty(isDirty());
      App.focusAfter.restore(cancelTok, shell.titleEl);
    }

    // The fields and the types shown for a saved row (setValues fires no events).
    function applySaved(src) {
      connection.setValues(src);
      sandbox.setValues(src);
      sandbox.setType(src.type || '');
    }

    // ── Save ────────────────────────────────────────────────────────────
    function showFieldErrors(fields) {
      var first = null;
      FIELD_ORDER.forEach(function (name) {
        if (fields[name]) {
          connection.setError(name, fields[name]);
          if (!first) first = name;
        }
      });
      return first;
    }

    // The one writer of the Save-in-flight state: the shell's busy state (Save, Cancel,
    // Test) and the danger-zone Delete follow it together, so Delete cannot be armed and
    // confirmed while a Save is in flight. Focus is never on Delete when it goes busy (the
    // Save click holds it), and the Save restore path re-places it afterwards.
    function setSaving(b) {
      saving = !!b;
      shell.setBusy(!!b);
      if (danger) danger.button.disabled = !!b;
      if (!b && idleWaiters.length) {
        var list = idleWaiters;
        idleWaiters = [];
        list.forEach(function (fn) { fn(); });
      }
    }

    // The quiet notes a fill or an approval's follow left: gone after Cancel and Save.
    function removeFollowNote() {
      var old = container.querySelectorAll('[data-testid="mcp-approved-change-note"]');
      for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    }
    function clearNotes() {
      if (fillApi) fillApi.clear();
      removeFollowNote();
    }

    function performSave() {
      if (!mount.alive() || saving) return;
      shell.setError('');
      connection.clearErrors();
      var form = collectFormData();
      if (form.error) {
        var firstBad = showFieldErrors(form.fields);
        if (firstBad) connection.focus(firstBad);
        return;
      }
      var body = JSON.stringify(form.payload);
      // What this click sent per row, for the re-mask; and the fields as they were sent.
      var submitted = handles.lastPartition;
      var submittedValues = valuesSnapshot();
      var saveTok = App.focusAfter.begin(shell.saveButton);
      setSaving(true); // a second click cannot send a second request (defect 5)
      var request = {
        headers: { 'Content-Type': 'application/json' },
        body: body
      };
      if (isCreate) {
        request.method = 'POST';
        App.api.fetchJson('/api/mcp-sources', request).then(function (created) {
          // The Library list shows the source (DD9). Invalidated BEFORE onSaveSuccess,
          // whose router sync names the new item.
          App.store.invalidate('mcp-sources');
          // A Save that lands after destroy still saved on the server: the list follows,
          // the dead editor is not touched.
          if (!mount.alive()) { if (callbacks.onListStale) callbacks.onListStale(); return; }
          App.ui.flash('MCP server created');
          // Create mounts the saved editor asynchronously: park the restore for its mount
          // to flush, and STAY busy until that remount replaces this editor (the connector
          // rule).
          App.focusAfter.defer(saveTok, titleNow);
          // The callback is last, and its failure is not a save failure: the record was
          // created. A throw leaves no remount coming, so un-busy (as the edit path does).
          try {
            if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(created, true);
          } catch (e) {
            if (window.console && console.error) console.error('onSaveSuccess failed', e);
            if (mount.alive()) setSaving(false);
          }
        }).catch(function (err) { onSaveError(err, saveTok); });
      } else {
        request.method = 'PUT';
        App.api.fetchJson('/api/mcp-sources/' + encodeURIComponent(source.id), request)
          .then(function (updated) {
            App.store.invalidate('mcp-sources');
            if (!mount.alive()) { if (callbacks.onListStale) callbacks.onListStale(); return; }
            App.ui.flash('MCP server saved');
            // The saved row, BEFORE the re-mask, so every getSource() reader sees it
            // (defect 3).
            current = updated;
            clearNotes();
            // Re-mask the secrets the server now holds; the rows keep their own baseline.
            envHeaders.remaskAfterSave(submitted, updated);
            // No field edited during the request: write the saved row back (it
            // normalises). Otherwise leave the DOM as the operator has it; the baseline
            // moves either way.
            if (valuesSnapshot() === submittedValues) applySaved(updated);
            snapshot = baselineSnapshot();
            // Squawk 0126: the title follows the saved row (a rename); so does the subtitle.
            shell.setTitle(titleFor(updated));
            shell.setSubtitle(subtitleFor(updated));
            if (danger) danger.button.dataset.name = updated.name || '';
            // A URL or type change drops last_check and auth_posture server-side.
            if (serverInfo) serverInfo.update(cacheOf(updated));
            if (connStatus) connStatus.render();
            var d = isDirty();
            reportDirty(d);
            setSaving(false);
            syncTestHold();
            App.focusAfter.restore(saveTok, shell.titleEl);
            // The callback is last, and its failure is not a save failure.
            try {
              if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, false);
            } catch (e) {
              if (window.console && console.error) console.error('onSaveSuccess failed', e);
            }
            // The glue marks the editor clean on save: say so again for an edit made
            // meanwhile.
            if (d && mount.alive() && callbacks.onDirtyChange) callbacks.onDirtyChange(true);
          })
          .catch(function (err) { onSaveError(err, saveTok); });
      }
    }

    function onSaveError(err, saveTok) {
      if (!mount.alive()) return;
      var fe = App.api.fieldErrors(err, SERVER_FIELDS);
      var fields = {};
      Object.keys(fe.fields).forEach(function (name) {
        var target = name;
        if (name === 'command' && connection.values().runtime !== STDIO_CUSTOM_SENTINEL) {
          target = 'runtime';
        }
        fields[target] = fe.fields[name];
      });
      var firstBad = showFieldErrors(fields);
      shell.setError(fe.text || '');
      setSaving(false);
      App.focusAfter.defer(null);
      if (firstBad) connection.focus(firstBad);
      else App.focusAfter.restore(saveTok, shell.saveButton);
    }

    // ── Test (edit only) ────────────────────────────────────────────────
    // The one entry for a Test click and the glue's auto-run after create ({autoRun:
    // true}: the Save click's user gesture is gone, so the flow must NOT open the OAuth
    // popup; there is no keyboard user behind it, so no focus token and the create's
    // parked restore stands). A quiet no-op without a Test button (create mode, a legacy
    // type), while Test is disabled, or while a sign-in session is live.
    function runTest(opts) {
      var btn = shell.testButton;
      if (!connStatus || !btn || !mount.alive() || btn.disabled || mount.sessionActive()) return;
      var autoRun = !!(opts && opts.autoRun);
      // Leg 08a (DD6): the dirty check comes first. A clean form posts NO body, so the
      // server tests (and records) the saved server and collectFormData is not called. A
      // dirty form sends its values (the server never records a body-ful Test); a form
      // that cannot be sent (defect 9) says why in the result area and sends nothing.
      var form = null;
      if (isDirty()) {
        form = collectFormData();
        if (form.error) { connStatus.showInvalid(form.error); return; }
        form = form.payload;
      }
      connStatus.runTest(form, {
        noAutoPopup: autoRun,
        focusTok: autoRun ? null : App.focusAfter.begin(btn)
      });
    }

    // ── Delete (edit only) ──────────────────────────────────────────────
    function performDelete(revert) {
      if (saving) { revert(); return; } // the button is disabled while saving; belt and braces
      var deleteTok = App.focusAfter.begin(danger.button);
      App.api.fetchJson('/api/mcp-sources/' + encodeURIComponent(source.id), { method: 'DELETE' })
        .then(function () {
          App.store.invalidate('mcp-sources');
          App.store.invalidate('agents');
          // A late Delete drops the row but never closes the open item.
          if (!mount.alive()) { if (callbacks.onListStale) callbacks.onListStale(); return; }
          App.ui.flash('MCP server deleted');
          if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
        })
        .catch(function (err) {
          if (!mount.alive()) return;
          revert();
          shell.setError((err && err.message) || String(err));
          App.focusAfter.restore(deleteTok, danger.button);
        });
    }

    // ── Payload assembly ────────────────────────────────────────────────
    // Validates on the handles and never writes the DOM. Returns {payload}, or {error,
    // fields}: `fields` maps a field to its A2 sentence and `error` is the first one (a
    // Test shows it in its result area; Save puts each on its field).
    function collectFormData() {
      /* Routes by `type` (NOT by visible-field set). A type-change immediately followed
         by Save emits the type-correct payload. */
      var fields = {};
      var firstMessage = null;
      function bad(field, message) {
        if (!fields[field]) fields[field] = message;
        if (!firstMessage) firstMessage = message;
      }
      var fv = connection.values();
      var name = fv.name.trim();
      if (!name) bad('name', 'Enter a name.');
      var kind = fv.type;
      if (!kind) bad('type', 'Choose how it connects.');

      var config = {};
      var secrets = {};

      if (kind === 'stdio') {
        // F9 L2 vibing: command source is the dropdown selection. For all canonical
        // runtime literals except `npx -y` and `pipx run` the dropdown value IS
        // `config.command` verbatim. For `npx -y` we split into `command=npx,
        // args=[-y, ...userArgs]`; for `pipx run` into `command=pipx, args=[run,
        // ...userArgs]` so the saved JSON stays transparent and the spawn layer does not
        // try to exec a 2-token string as a single binary. For Custom… the free-text
        // input feeds `config.command` directly (operator owns resolution).
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
          bad(runtimeValue === STDIO_CUSTOM_SENTINEL ? 'command' : 'runtime',
            'Choose or enter a command.');
        }
        config.command = command;
        var cwd = fv.cwd.trim();
        if (cwd) config.cwd = cwd;
        var argsList = prependArgs.concat(fv.args);
        if (argsList.length > 0) config.args = argsList;
        config.env = {};
        // F3 L5b: sandbox profile (stdio only). Always-emit precedent matches config.env:
        // empty defaults are written explicitly, not omitted.
        var sv = sandbox.values();
        config.sandbox = { network_allowed: sv.networkAllowed, writable_paths: sv.writablePaths };
      } else if (kind === 'streamable-http') {
        var urlValue = fv.url.trim();
        if (!urlValue) bad('url', "Enter the server's URL.");
        config.url = urlValue;
        config.headers = {};
      } else if (kind) {
        bad('type', 'Unsupported transport type: ' + kind + '.');
      }

      if (firstMessage) return { error: firstMessage, fields: fields };
      handles.lastPartition = envHeaders.partition(
        kind === 'stdio' ? config.env : config.headers, secrets);
      return { payload: { name: name, type: kind, config: config, secrets: secrets } };
    }

    var controller = {
      destroy: mount.destroy,
      // The glue un-busies a create whose remount could not open the new record.
      setBusy: function (b) {
        if (!mount.alive()) return;
        setSaving(b);
      },
      setError: function (msg) { if (mount.alive()) shell.setError(msg); },
      runTest: runTest,

      // ── The handles of a GleepGlorp fill and of an approval's follow (M36 F4 L4b) ──
      // Every setter is silent (no Save, no Test, no popup, no request); the caller runs
      // checkDirty() once it has written.
      key: openKey,
      isCreate: isCreate,
      id: isCreate ? null : source.id,
      el: container,
      alive: function () { return mount.alive(); },
      // The type list loaded: an empty list is a failed fetch, and the editor cannot be filled.
      ready: function () { return mount.alive() && (mcpTypes || []).length > 0; },
      saving: function () { return saving; },
      onIdle: function (fn) { if (!saving) fn(); else idleWaiters.push(fn); },
      checkDirty: checkDirty,
      values: function () { return { connection: connection.values(), rows: envHeaders.values() }; },
      baseline: function () { return JSON.parse(snapshot); },
      storedCommand: connection.storedCommand,
      rowKind: envHeaders.rowKind,
      rowState: envHeaders.rowState,
      // Create forms only: the type, the sections it shows and the table it labels. The rows
      // the operator typed stay.
      setType: function (t) {
        if (!mount.alive() || !isCreate) return;
        connection.selectType(t);
        sandbox.setType(t);
        envHeaders.setType(t);
      },
      // 'name', 'url' and 'cwd' take a string; 'command' takes {command, args} (stored form).
      setField: function (field, value) {
        if (!mount.alive()) return;
        if (field === 'command') connection.setCommand(value.command, value.args);
        else connection.setField(field, value);
      },
      // entries: [{key, value}], merged by key; an empty value is the Sensitive handoff.
      setRows: function (entries) { if (mount.alive()) envHeaders.setRows(entries); },
      placeNote: function (field, note) { return connection.placeNote(field, note); },
      placeTableNote: function (note) { return envHeaders.placeTableNote(note); },
      // An approved change for this server: a clean field takes it, a dirty field keeps the
      // operator's value and its baseline moves; rows go per key.
      rebase: function (src) {
        if (!mount.alive() || isCreate || !src) return;
        var cfg = src.config || {};
        var oldBase = JSON.parse(snapshot).connection;
        var live = connection.values();
        function clean(keys) {
          return keys.every(function (k) {
            return JSON.stringify(live[k]) === JSON.stringify(oldBase[k]);
          });
        }
        if (clean(['name'])) connection.setField('name', src.name);
        if (clean(['cwd'])) connection.setField('cwd', cfg.cwd || '');
        if (clean(['url'])) connection.setField('url', cfg.url || '');
        if (src.type === 'stdio' && clean(['runtime', 'command', 'args'])) {
          connection.setCommand(cfg.command || '', cfg.args || []);
        }
        current = src;
        snapshot = baselineSnapshot();
        envHeaders.rebaseTo(mcpEditor.shared.rowsFromSource(src, src.type));
        shell.setTitle(titleFor(src));
        shell.setSubtitle(subtitleFor(src));
        if (danger) danger.button.dataset.name = src.name || '';
        if (serverInfo) serverInfo.update(cacheOf(src));
        if (connStatus) connStatus.render();
        checkDirty();
      },
      // The follow note: one line under the editor's header, replacing the last one.
      placeFollowNote: function (note) {
        removeFollowNote();
        shell.el.parentNode.insertBefore(note, shell.el.nextSibling);
      }
    };
    fillApi = App.studio.mcpEditorFill.create(controller);
    mount.onDestroy(fillApi.destroy);
    controller.fill = fillApi;
    if (callbacks.onMounted) callbacks.onMounted(controller);
    return controller;
  }

  window.App.studio.renderMcpSourceEditor = renderMcpSourceEditor;
})();
