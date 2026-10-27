// App.studio.agentEditorController -- the agent editor's controller (M31 F2 L03,
// DD1): renderEditor (the callback bag handed to App.studio.renderAgentEditor),
// setActiveTab, Cancel, Delete, Purge, Test provider, Save/Create and the
// FastAPI error extraction. Moved verbatim out of studio.js; a factory studio
// calls once in init:
//
//   var controller = App.studio.agentEditorController.create(ctx);
//
// ctx (studio -> module): self, state, editorEl, agentData (the agent-data
// handle), formData and picker (the agent-form-data / agent-model-picker
// handles), discardOpen, writeUrl, and list() -- a CALL-TIME getter for the
// agents-list handle, because the list is created after the controller (its
// selection calls renderEditor). The controller reaches the list only for
// replaceWithAgentsRoot / replaceWithAgent / focusNear / indexOf, through the
// local wrappers below.
//
// handle (module -> studio): renderEditor(agent), setActiveTab(tab, options),
// onSelfConfigChanged(updated) (M31 F2 L10a, DD9-3), deactivateSelfConfig() (M31 F2 L10c).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var editorEl = ctx.editorEl;
    var agentData = ctx.agentData;
    var collectFormData = ctx.formData.collectFormData;
    var getFormSnapshot = ctx.formData.getFormSnapshot;
    var checkDirty = ctx.formData.checkDirty;
    var wireEditorEvents = ctx.picker.wireEditorEvents;
    var discardOpen_ = ctx.discardOpen;
    var writeUrl_ = ctx.writeUrl;
    // The per-agent Tools tab's categories: label -> tool names, from the one
    // shared table (static/js/tool-categories.js, M25 F4 L6, AC9; it replaced
    // this file's copy and the two admin/tools-*.js maps).
    var TOOL_CATEGORIES = App.toolCategories.byCategory;

    // The agents-list calls, resolved at call time (see the ctx header).
    function replaceWithAgentsRoot_() { ctx.list().replaceWithAgentsRoot(); }
    function replaceWithAgent_(agent) { ctx.list().replaceWithAgent(agent); }
    function focusAgentRowNear(index) { ctx.list().focusNear(index); }
    function visibleIndexOf(name) { return ctx.list().indexOf(name); }

    // F5 leg 03: renderEditor delegates to the agent-editor module which
    // builds the header + action cluster + tablist + three tab panels.
    // Per-tab render helpers populate the panels; the General tab is mounted
    // synchronously so existing form-field tests find their selectors
    // immediately.
    //
    // M31 F2 L06a: the editor mounts through a mount slot. The identity is (the
    // saved agent's name, create-or-edit): a new identity (another agent, create ->
    // edit, a rename, a delete) remounts the frame; the same identity (a Save
    // without a rename, a same-agent doSelect, Cancel) calls the handle's patch.
    // The slot's data is { key, token, handle, wireGen }.
    var slot = App.ui.util.mountSlot();

    function currentData_() {
      var cur = slot.current();
      return cur ? cur.data : null;
    }

    // The shell handle of the current mount (checkDirty reads it through ctx).
    function shell() {
      var d = currentData_();
      return d && d.handle ? d.handle.shell : null;
    }

    // Focus targets, re-resolved from the CURRENT mount each time they are read
    // (a rename remount and a Cancel both replace nodes).
    function editorTitleEl_() { var s = shell(); return s ? s.titleEl : null; }
    function saveBtnEl_() { var s = shell(); return s ? s.saveButton : null; }
    function cancelBtnEl_() { var s = shell(); return s ? s.cancelButton : null; }

    function setEditorError_(text) {
      var s = shell();
      if (s) s.setError(text);
    }

    function setNameError_(text) {
      var d = currentData_();
      if (d && d.handle && d.handle.general) d.handle.general.setNameError(text);
    }

    // A failed save: the server's name refusal goes on the Name field (focused, so
    // the operator lands on it), every other message in the header.
    function onSaveError_(err) {
      var fe = App.api.fieldErrors(err, ['name']);
      setNameError_(fe.fields.name || null);
      setEditorError_(fe.text || '');
      if (fe.fields.name) {
        var input = editorEl.querySelector('#studio-name');
        if (input) input.focus();
      }
    }

    // A liveness guard for an async callback: true while the mount it was taken
    // under is still the slot's current one AND no panel rebuild (patch, Cancel)
    // has replaced the DOM it reads.
    function liveGuard() {
      var d = currentData_();
      if (!d) return function () { return false; };
      var token = d.token;
      var gen = d.wireGen;
      return function () {
        var c = slot.current();
        return !!c && c.token === token && c.data.wireGen === gen;
      };
    }

    function destroyEditor() {
      slot.destroy();
    }

    // True from the start of a Save's request until its response has been handled
    // (a self-configuration refresh landing in between is left to the Save).
    var saveInFlight = false;

    // ── Self-configuration refresh (M31 F2 L10a, DD9-3) ──────────────
    // The loopback source row's name: a constant of the server (the row each
    // agent's own surface uses; self_configuration/manage.py SURFACE_ROW_NAME).
    var SELF_CONFIG_SOURCE_NAME = 'self-configuration';

    function parseSnapshot_() {
      try { return JSON.parse(state.snapshot); } catch (e) { return null; }
    }

    function idsOf_(list) { return Array.isArray(list) ? list : []; }

    // Re-derive the stored-value note: a field leaves it once the operator makes it
    // equal to the (rebased) baseline again. Runs on every input.
    function recheckStoredNote_() {
      var d = currentData_();
      if (!d || !d.noteFields || d.noteFields.length === 0 || !d.handle) return;
      var base = parseSnapshot_();
      var cur = null;
      try { cur = JSON.parse(getFormSnapshot()); } catch (e) { cur = null; }
      if (!base || !cur) return;
      var still = d.noteFields.filter(function (f) { return cur[f] !== base[f]; });
      if (still.length === d.noteFields.length) return;
      d.noteFields = still;
      d.handle.general.setStoredChangeNote(still.length ? still : null);
    }

    // Move a dirty baseline along with a self-configuration change, key by key, so
    // the unsaved edits stay the only difference: description / system_prompt take
    // their new stored value, mcp_source_ids gains or loses the surface id (kept in
    // the form's DOM order) and mcp_overrides follows the surface source's entry.
    function rebaseBaseline_(prev, updated) {
      var base = parseSnapshot_();
      if (!base) { state.snapshot = getFormSnapshot(); return; }
      var cur = JSON.parse(getFormSnapshot());
      ['description', 'system_prompt'].forEach(function (k) {
        if (typeof updated[k] === 'string' && k in base) base[k] = updated[k];
      });
      var before = idsOf_(prev && prev.mcp_source_ids);
      var after = idsOf_(updated.mcp_source_ids);
      var added = after.filter(function (id) { return before.indexOf(id) === -1; });
      var removed = before.filter(function (id) { return after.indexOf(id) === -1; });
      if ((added.length || removed.length) && Array.isArray(base.mcp_source_ids)) {
        var baseIds = base.mcp_source_ids.filter(function (id) { return removed.indexOf(id) === -1; });
        var next = [];
        idsOf_(cur.mcp_source_ids).forEach(function (id) {
          if (baseIds.indexOf(id) !== -1 || added.indexOf(id) !== -1) next.push(id);
        });
        baseIds.forEach(function (id) { if (next.indexOf(id) === -1) next.push(id); });
        base.mcp_source_ids = next;
      }
      if (added.length || removed.length) {
        var baseOv = base.mcp_overrides || {};
        var curOv = cur.mcp_overrides || {};
        var nextOv = {};
        Object.keys(curOv).forEach(function (k) {
          if (k === SELF_CONFIG_SOURCE_NAME) nextOv[k] = curOv[k];
          else if (k in baseOv) nextOv[k] = baseOv[k];
        });
        Object.keys(baseOv).forEach(function (k) {
          if (k !== SELF_CONFIG_SOURCE_NAME && !(k in nextOv)) nextOv[k] = baseOv[k];
        });
        base.mcp_overrides = Object.keys(nextOv).length > 0 ? nextOv : null;
      }
      state.snapshot = JSON.stringify(base);
    }

    // A self-configuration write (enable, disable, approval mode, approve, override,
    // dismiss, restore) changed the stored agent outside the Save flow. agent-data
    // has already replaced the list row and refreshed the MCP sources cache. The
    // open editor is patched in place, never rebuilt, so unsaved edits survive; it
    // never calls doSelect / patch / General.setAgent / MCPs.setAgent and never
    // touches selectSeq, state.dirty or _selectedAgentLoaded.
    function onSelfConfigChanged(updated) {
      var prev = self._selectedAgent;
      var sameAgent = !!prev && prev.name === updated.name;
      var d = currentData_();
      var live = self._activeSection === 'agents' && !!d && !!d.handle &&
        d.key === 'edit:' + updated.name && !saveInFlight && sameAgent;
      if (sameAgent) self._selectedAgent = updated;
      ctx.list().render();
      if (!live) return;

      var wasClean = getFormSnapshot() === state.snapshot;
      var h = d.handle;
      var baseline = parseSnapshot_();

      var conflicts = h.general.applyStored(
        { description: updated.description, system_prompt: updated.system_prompt }, baseline);
      if ((prev.description || '') !== (updated.description || '')) {
        h.shell.setSubtitle(updated.description || '');
      }
      h.mcps.setSources(self._allMcpSources, updated.name);
      h.selfConfig.setAgent(updated);

      if (wasClean) {
        state.snapshot = getFormSnapshot();
        d.noteFields = null;
        h.general.setStoredChangeNote(null);
      } else {
        rebaseBaseline_(prev, updated);
        // Fields already noted stay noted until the operator makes them clean.
        var noted = (d.noteFields || []).slice();
        conflicts.forEach(function (f) { if (noted.indexOf(f) === -1) noted.push(f); });
        d.noteFields = noted.length ? noted : null;
        h.general.setStoredChangeNote(d.noteFields);
      }
      checkDirty();
    }

    function wire_(data, isCreate, agent) {
      data.wireGen += 1;
      var token = data.token;
      var gen = data.wireGen;
      var guard = function () {
        return slot.isCurrent(token) && data.wireGen === gen;
      };
      wireEditorEvents(isCreate, agent || {
        provider_config_id: self._allProviders.length > 0 ? self._allProviders[0].id : null,
        llm_model: ''
      }, guard);
    }

    // `opts.revert` marks a Cancel (the Tools tab drops its loaded override bodies).
    function renderEditor(agent, opts) {
      var isCreate = !agent;
      var key = isCreate ? 'create' : 'edit:' + agent.name;
      var cur = currentData_();
      var bag = buildCallbacks_(isCreate);
      if (cur && cur.key === key && cur.handle && cur.handle.shell.el.parentNode === editorEl) {
        patchEditor_(cur, agent, bag, opts);
        return;
      }
      state.tabHandle = null;
      var data = { key: key, token: null, handle: null, wireGen: 0, noteFields: null };
      data.token = slot.mount(function () {
        if (data.handle) data.handle.destroy();
        data.handle = null;
        if (state.tabHandle) state.tabHandle = null;
      }, data);
      try {
        data.handle = App.studio.renderAgentEditor(editorEl, agent, self._allProviders, bag);
      } catch (err) {
        slot.release(data.token);
        throw err;
      }
      state.tabHandle = data.handle.tabs;
      // Wire field-level dirty tracking + provider-change side-effects. These run
      // AFTER the editor DOM is in place.
      wire_(data, isCreate, agent);
      // Dirty snapshot baseline; checkDirty re-derives Save, Cancel and the
      // unsaved caption from it (clean).
      state.snapshot = getFormSnapshot();
      checkDirty();
    }

    // The same-identity update (the leg's patch policy): the handle patches the
    // header, the load-error node and panels (General, Knowledge, MCPs and Tools patched, the other two rebuilt: the interim list), then the
    // picker is re-wired for the rebuilt General, the requested tab is selected if
    // it differs (a hydrate's pending tab) and the snapshot is reset.
    function patchEditor_(data, agent, bag, opts) {
      data.noteFields = null; // General's setAgent (inside patch) hides the note
      data.handle.patch(agent, self._allProviders, bag, opts);
      wire_(data, !agent, agent);
      if (self._activeTab && data.handle.tabs.selected() !== self._activeTab) {
        data.handle.tabs.select(self._activeTab);
      }
      state.snapshot = getFormSnapshot();
      checkDirty();
    }

    function buildCallbacks_(isCreate) {
      return {
        loadFailed: !isCreate && self._selectedAgentLoaded === false,
        initialTab: self._activeTab || 'general',
        onDelete: handleDeleteEditor,
        onPurge: handlePurgeHistory,
        onSave: function () { save(isCreate); },
        onCancel: function () { cancelEdit(); },
        onTabChange: function (tabId) { setActiveTab(tabId); },
        // F5 leg 05: tabs in the same agent share the form's dirty state, so
        // switching tabs does NOT lose unsaved data — no confirmation prompt.
        // The router's leave guard still fires on a list row, "New", the rail
        // and hash-route navigation to a different agent.
        onTestProvider: testProvider,
        toolCategories: TOOL_CATEGORIES,
        allTools: self._allTools,
        onChange: function () { checkDirty(); recheckStoredNote_(); },
        // F6 leg 05 — operator-state surfaces in Tools tab. Caches were
        // refreshed at editor-mount time (see selectAgent / doSelect). The
        // schema fetcher is closure-cached and survives agent changes.
        disabledTools: self._disabledTools,
        operatorConfigs: self._operatorConfigs,
        fetchToolSchema: agentData.fetchToolSchema,
        // F6 L3 — knowledge-base list + the L3-D1 load-success flag for
        // the Knowledge tab. Both are refreshed at editor-mount time (see
        // selectAgent / doSelect / doEnterCreateMode above).
        allKnowledgeBases: self._allKnowledgeBases,
        knowledgeBasesLoaded: self._knowledgeBasesLoaded === true,
        // F8 L3 — MCP source list + per-source tools fetcher for MCPs tab.
        allMcpSources: self._allMcpSources,
        fetchMcpSourceTools: agentData.fetchMcpSourceTools,
        // The studio owns the source focus (hydrate applies the URL's value to
        // both slots); the tab reads it from here, never from location.hash.
        pendingMcpAgentSourceId: self._selectedMcpAgentSourceId || self._pendingMcpAgentSourceId || null,
        // Callback so renderMcpsTab can notify studio.js when the selected
        // source changes (chip click → per-attachment editor). studio.js
        // updates _selectedMcpAgentSourceId and syncs the URL.
        onSelectedMcpSourceChange: function (sourceId) {
          self._selectedMcpAgentSourceId = sourceId;
          self._pendingMcpAgentSourceId = null;
          writeUrl_();
        },
        // M27 F1 L2 -- Rules and notes tab network calls.
        fetchRules: agentData.fetchRules,
        createRule: agentData.createRule,
        updateRule: agentData.updateRule,
        deleteRule: agentData.deleteRule,
        reorderRules: agentData.reorderRules,
        fetchNotes: agentData.fetchNotes,
        setNotesEnabled: agentData.setNotesEnabled,
        updateNote: agentData.updateNote,
        deleteNote: agentData.deleteNote,
        clearNotes: agentData.clearNotes,
        // M21 F01 L02 — Self-configuration tab network calls.
        fetchSelfConfigurationStatus: agentData.fetchSelfConfigurationStatus,
        onEnableSelfConfiguration: agentData.enableSelfConfiguration,
        onDisableSelfConfiguration: agentData.disableSelfConfiguration,
        // M21 F02 L02 — approval-mode toggle + revision queue.
        onSetSelfConfigurationApprovalMode: agentData.setSelfConfigurationApprovalMode,
        fetchSelfConfigurationRevisions: agentData.fetchSelfConfigurationRevisions,
        onApproveSelfConfigurationRevision: agentData.approveSelfConfigurationRevision,
        onDismissSelfConfigurationRevision: agentData.dismissSelfConfigurationRevision,
        // M21 F02 L03 — revision history restore.
        onRestoreSelfConfigurationRevision: agentData.restoreSelfConfigurationRevision,
        // M21 F03 L03 — external-client credential grant/list/revoke/rotate.
        onMintExternalCredential: agentData.mintExternalCredential,
        fetchExternalCredentials: agentData.fetchExternalCredentials,
        onRevokeExternalCredential: agentData.revokeExternalCredential,
        onRotateExternalCredential: agentData.rotateExternalCredential
      };
    }
    // Named hook (M31 F2 L10c): the Self-configuration tab drops its copy-once token
    // when the tab stops being the shown one (a tab switch, or the Studio area
    // deactivating). No-op without a mounted self-configuration tab.
    function deactivateSelfConfig() {
      var d = currentData_();
      if (d && d.handle && d.handle.selfConfig && d.handle.selfConfig.deactivate) {
        d.handle.selfConfig.deactivate();
      }
    }

    // setActiveTab — analogous to setActiveSection. Updates _activeTab,
    // calls the tab handle's activate (which swaps panel visibility +
    // aria-selected + roving tabindex), writes URL via _writeUrl unless
    // the caller opts out (hydrate path).
    function setActiveTab(tab, options) {
      options = options || {};
      var writeUrl = options.writeUrl !== false;
      // F8 L3: clear per-source selection when leaving the MCPs tab so the
      // URL doesn't carry a stale /{source-id} when switching to another tab.
      if (tab !== 'mcps') {
        self._selectedMcpAgentSourceId = null;
        self._pendingMcpAgentSourceId = null;
      }
      var leftSelfConfig = self._activeTab === 'self-configuration' && tab !== 'self-configuration';
      self._activeTab = tab;
      // Leaving the Self-configuration tab clears a copy-once token still showing.
      if (leftSelfConfig) deactivateSelfConfig();
      if (state.tabHandle && state.tabHandle.selected() !== tab) {
        state.tabHandle.select(tab);
      }
      if (writeUrl) writeUrl_();
    }

    // ── Action-cluster handlers ──────────────────────────────────────

    // Cancel discards in-progress edits and restores the editor to the
    // current agent's saved state. On an open agent the button only fires
    // when dirty (disabled by checkDirty otherwise), so no extra guard.
    function cancelEdit() {
      if (self._createMode) {
        // Create-form Cancel (M25 F3 L3, DD8): there is no saved state to
        // revert to. The button is enabled from first render, so this runs on
        // a pristine form as well as a dirty one, and assumes neither: the
        // studio discard teardown runs first, then a bypass go() (the user
        // already chose to discard) REPLACES the create entry with the Agents
        // root, so Back never lands on a stale create form. Focus: there is
        // no row of its own, so the list's tab stop (the nearest row), else
        // "New".
        discardOpen_();
        replaceWithAgentsRoot_();
        focusAgentRowNear(0);
        return;
      }
      if (self._selectedAgent) {
        var cancelTok = App.focusAfter.begin(cancelBtnEl_());
        renderEditor(self._selectedAgent, { revert: true });
        state.dirty = false;
        checkDirty();
        App.focusAfter.restore(cancelTok, editorTitleEl_);
      }
    }

    // Editor's Delete (General's danger zone): the library arms the button
    // (App.ui.confirm via dangerZone, "Confirm delete?") and calls this on the
    // second click with its revert function.
    function handleDeleteEditor(revertFn) {
      var name = self._selectedAgent ? self._selectedAgent.name : null;
      if (!name) return;
      // DD8 focus: the deleted row's visible index, read BEFORE the request
      // (the row is about to leave the list).
      var rowIndex = visibleIndexOf(name);
      fetch('/api/agents/' + encodeURIComponent(name), { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Delete failed'); });
        })
        .then(function () {
          App.store.invalidate('agents');
          self._selectedAgent = null;
          state.dirty = false;
          return agentData.loadAll();
        })
        .then(function () {
          // Post-delete navigation (M25 F3 L3, DD8): replace the deleted
          // agent's entry with the Agents root -- the empty detail state,
          // announced as "Agents" -- never another agent. The deleted
          // agent's editor is torn down first (vanish path). Focus goes to
          // the nearest surviving row (the next, else the previous), else
          // "New".
          discardOpen_();
          replaceWithAgentsRoot_();
          focusAgentRowNear(rowIndex);
        })
        .catch(function (err) {
          revertFn();
          App.ui.flash((err && err.message) || 'Delete failed', { error: true });
        });
    }

    // Purge chat history (M13 F2 leg 02). Mirrors handleDeleteEditor's
    // arm-then-fire (the danger zone's second action), but DELETEs the agent's chat
    // SESSIONS (not the agent) and KEEPS the agent selected — no
    // loadAll()/selectAgent/renderEmptyEditor. On success the deleted count is
    // flashed in place; on transport failure the armed button reverts and an
    // error flash shows. Reads self._selectedAgent.name (like
    // handleDeleteEditor).
    function handlePurgeHistory(revertFn) {
      var name = self._selectedAgent ? self._selectedAgent.name : null;
      if (!name) return;
      fetch('/api/agents/' + encodeURIComponent(name) + '/chat/sessions', { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Purge failed'); });
          return r.json();
        })
        .then(function (body) {
          var n = body && typeof body.deleted === 'number' ? body.deleted : 0;
          // The agent's sessions are gone (M25 F4 L1, DD4).
          App.store.invalidate('sessions');
          App.ui.flash('Purged ' + n + ' conversation' + (n === 1 ? '' : 's'));
        })
        .catch(function (err) {
          revertFn();
          App.ui.flash((err && err.message) || 'Purge failed', { error: true });
        });
    }

    // Test provider — POST /api/providers/{id}/test with empty body.
    // Reads the LIVE #studio-provider value (NOT cfg.provider_config_id)
    // so unsaved provider changes are testable.
    function testProvider() {
      var providerSelect = editorEl.querySelector('#studio-provider');
      var d = currentData_();
      var general = d && d.handle ? d.handle.general : null;
      function show(state, text) { if (general) general.setTestResult(state, text); }
      if (!providerSelect || !providerSelect.value) {
        show('danger', 'No provider selected');
        return;
      }
      var providerId = providerSelect.value;
      // M31 F2 L06a: a response for a mount (or a panel build) that has since gone
      // writes nothing. General is patched, not rebuilt, so a patch/Cancel (a new
      // wireGen) also drops a result still in flight.
      var live = liveGuard();
      show('pending', 'Testing\u2026');
      fetch('/api/providers/' + encodeURIComponent(providerId) + '/test', { method: 'POST' })
        .then(function (r) {
          return r.json().then(function (body) { return { ok: r.ok, body: body }; });
        })
        .then(function (res) {
          if (!live()) return;
          var detail = (res.body && res.body.detail) || '';
          var isOk = res.ok && res.body && res.body.status === 'ok';
          show(isOk ? 'success' : 'danger', detail || (isOk ? 'Provider test ok' : 'Provider test failed'));
          if (isOk) {
            App.ui.flash(detail || 'Provider test ok');
          } else {
            App.ui.flash(detail || 'Provider test failed', { error: true });
          }
        })
        .catch(function (err) {
          if (!live()) return;
          var msg = (err && err.message) || 'Network error';
          show('danger', msg);
          App.ui.flash(msg, { error: true });
        });
    }

    // ── Save ─────────────────────────────────────────────────────────

    // Focus after an in-place action (M25 F6 L1b, DD2): the title and the Save
    // button are re-resolved from the current mount when the focus timer fires
    // (editorTitleEl_ / saveBtnEl_, above).

    // M31 F4 L05c: a Save is refused, before any request, while an override field
    // holds a value that cannot be saved (a number that is not whole). The editor
    // error names the tool and the field; the tool's Overrides panel is opened and
    // the field focused. The field's own error is already live (App.toolConfigFields).
    function refuseBlockingOverride_(blocking) {
      setEditorError_(
        'Can’t save: ' + blocking.tool + ', ' + blocking.label + '. ' + blocking.message
      );
      var panel = blocking.control.closest('details');
      if (panel) panel.open = true;
      blocking.control.focus();
    }

    function save(isCreate) {
      // Squawk 0090 -- belt-and-braces behind the disabled Save button (a
      // keyboard/script-driven click, or a save that races the in-flight
      // fresh-agent fetch, still reaches here). Refuse rather than PUT a body
      // whose `disabled_tools` was unioned from a possibly-pre-rename cached
      // agent. The header already says why; a new error would replace that line.
      if (!isCreate && self._selectedAgentLoaded === false) return;
      setNameError_(null);
      setEditorError_('');
      var data = collectFormData();
      var blocking = ctx.formData.blockingError();
      if (blocking) {
        refuseBlockingOverride_(blocking);
        return;
      }
      var focusTok = App.focusAfter.begin(saveBtnEl_());
      // The mount this Save was started from: a response that lands after it was
      // torn down (a discard, another agent) must not render into the new one.
      var saveSlotTok = currentData_() ? currentData_().token : null;

      if (isCreate) {
        if (!data.name || !data.name.trim()) {
          setNameError_('Name is required.');
          return;
        }
        // Create turns into the saved agent's editor asynchronously (doSelect's
        // fetches): park the restore; doSelect's final mount flushes it.
        App.focusAfter.defer(focusTok, editorTitleEl_);
        // Save-create staleness (the knowledge-base create form's
        // stillOnCreate() pattern): the user may move on while the POST or
        // the list reload that follows it is in flight. This form is still
        // the open item while no teardown has run since Save (closeOpenItem
        // bumps editorGen) and the router still shows the create route.
        saveInFlight = true;
        var createGen = state.editorGen;
        var onThisForm = function () {
          var cur = App.router.current();
          return createGen === state.editorGen && !!cur && cur.route === 'agents/~new';
        };
        App.api.fetchJson('/api/agents', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        })
          .then(function (created) {
            App.store.invalidate('agents');
            // Still on the form: it is now a saved agent awaiting its route,
            // so clear its flags -- only then, since `dirty` is one flag
            // shared by every studio editor and a re-entered create form owns
            // `_createMode`.
            var stayed = onThisForm() && self._createMode;
            if (stayed) {
              state.dirty = false;
              self._createMode = false;
            }
            return agentData.loadAll().then(function () {
              // The list has the new row either way (loadAll re-rendered it).
              // Open the agent only for a user still on this form with no
              // leave decision pending: a bypass replace would otherwise pull
              // someone who moved on (another agent, the Agents root, another
              // destination) onto the new agent.
              if (!stayed || !onThisForm() || App.router.isDeciding()) {
                App.focusAfter.defer(null);
                return;
              }
              var found = null;
              for (var i = 0; i < self._agents.length; i++) {
                if (self._agents[i].name === created.name) { found = self._agents[i]; break; }
              }
              // Save-create: replace the create route's history entry with
              // the new agent's route (no new entry).
              if (found) replaceWithAgent_(found);
              showFlash('Agent created');
            });
          })
          .catch(function (err) {
            onSaveError_(err);
            App.focusAfter.defer(null);
            App.focusAfter.restore(focusTok, saveBtnEl_);
          })
          .then(function () { saveInFlight = false; });
      } else {
        var oldName = self._selectedAgent.name;
        var requestedName = (data.name || '').trim();
        if (!requestedName) {
          setNameError_('Name is required.');
          return;
        }
        // F4 L02 functional batch — rename support. If the user changed
        // the Name field on an existing agent, POST to the rename
        // endpoint FIRST so the PUT save can target the new PK. On
        // rename failure, abort and surface the error; do NOT proceed
        // with the PUT (the operator can re-try or revert the name
        // input).
        saveInFlight = true;
        var renamePromise;
        var effectiveName;
        if (requestedName !== oldName) {
          effectiveName = requestedName;
          renamePromise = App.api.fetchJson('/api/agents/' + encodeURIComponent(oldName) + '/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_name: requestedName })
          })
            .then(function (renamed) {
              App.store.invalidate('agents');
              // A rename re-points chat_sessions.agent_name (M25 F4 L1, DD4).
              App.store.invalidate('sessions');
              // ...and the connector bindings that named the agent.
              App.store.invalidate('connectors');
              // Re-bind the in-closure "currently-editing" name so the
              // subsequent PUT targets the new PK and so the area's
              // URL state serialization reflects the rename.
              self._selectedAgent = renamed;
              return renamed;
            });
        } else {
          effectiveName = oldName;
          renamePromise = Promise.resolve(null);
        }

        renamePromise
          .then(function () {
            data.name = effectiveName;
            return App.api.fetchJson('/api/agents/' + encodeURIComponent(effectiveName), {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data)
            });
          })
          .then(function (updated) {
            App.store.invalidate('agents');
            state.dirty = false;
            self._selectedAgent = updated;
            return agentData.loadAll().then(function () {
              var found = null;
              for (var i = 0; i < self._agents.length; i++) {
                if (self._agents[i].name === updated.name) { found = self._agents[i]; break; }
              }
              if (found && !slot.isCurrent(saveSlotTok)) {
                // The editor this Save came from is gone: nothing to re-render.
                showFlash('Agent saved');
              } else if (found) {
                // kb-studio-round-trip remediation FIX 2 (FINDING 7,
                // 2026-09-18): `loadAll()` repopulates `self._agents` from
                // the LIST route, which deliberately omits `kb_tool_names`
                // (L2-D5, to avoid an N+1 read on every page load) — so
                // `found` structurally cannot carry it. `updated` is the
                // PUT response, which DOES carry it (same single-agent
                // shape `GET /api/agents/{name}` returns). Merge it forward
                // rather than discarding it in favour of the list object,
                // or an attached row would regress to the unattached
                // placeholder immediately after every save.
                found.kb_tool_names = updated.kb_tool_names;
                self._selectedAgent = found;
                renderEditor(found);
                App.focusAfter.restore(focusTok, editorTitleEl_);
                showFlash('Agent saved');
                // Rewrite the URL so refresh / back-button targets the
                // new agent name (the area's URL keys on
                // _selectedAgent.name; writeUrl_ re-serializes).
                if (typeof writeUrl_ === 'function') writeUrl_();
              } else {
                // Save→delete race (F1 debrief): a concurrent DELETE removed
                // this agent between the PUT resolving and loadAll(). Without
                // this fallback the block silently no-ops, stranding a stale
                // editor for a now-gone agent. Like a delete (M25 F3 L3, DD8),
                // it lands on the Agents root, never on another agent.
                self._selectedAgent = null;
                discardOpen_();
                replaceWithAgentsRoot_();
              }
            });
          })
          .catch(function (err) {
            onSaveError_(err);
            App.focusAfter.restore(focusTok, saveBtnEl_);
          })
          .then(function () { saveInFlight = false; });
      }
    }

    // ── Helpers ──────────────────────────────────────────────────────

    var showFlash = function (msg) { App.ui.flash(msg); };

    return {
      renderEditor: renderEditor,
      setActiveTab: setActiveTab,
      deactivateSelfConfig: deactivateSelfConfig,
      destroyEditor: destroyEditor,
      onSelfConfigChanged: onSelfConfigChanged,
      shell: shell
    };
  }

  window.App.studio.agentEditorController = { create: create };
})();
