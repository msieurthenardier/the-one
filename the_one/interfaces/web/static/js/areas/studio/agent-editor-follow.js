// App.studio.agentEditorFollow -- the agent editor follows a change the operator approved in
// a GleepGlorp chat (M36 F2 L7, flight DD10). A factory the controller calls once:
//
//   var follow = App.studio.agentEditorFollow.create(ctx);
//
// ctx (controller -> module): self, state, editorEl, getFormSnapshot, checkDirty,
// currentData() (the current mount's data or null), saveInFlight(), list() (the agents-list
// handle, call-time), parseSnapshot() and picker (the model picker handle).
// handle: afterMount() (draws the notes, called after every mount and patch), clear(name),
// onEvent(detail).
//
// The signal is App.approvals' CONFIG_CHANGED event (the document is the transport, and has no
// `off`), so the listener is registered once per page and calls the newest handle.
//
// The central apply (applyAgent): per touched field group, the editor is clean or dirty by
// comparing the form with its baseline. A clean group takes the stored value and is rebased; a
// dirty group keeps the operator's value, the baseline moves to the stored value and the panel
// note ("The stored {label} changed...") is shown. L8 adds TAB_GROUPS (tools, MCP attach, KB
// attach: decided per item), the rule and routine lists (reload + a list note) and
// ctx.refreshMcpSources (the MCP sources cache, refreshed before an MCP apply).
//
// The notes (board option A): each control that holds an approved value shows a caption under
// it, drawn from the App.approvals record at every mount, so the full re-patch on Agents
// activation never wipes them.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var NOTE_TESTID = 'agent-approved-change-note';

  // A field group: the stored field names it covers (the form's data-field names) and the control
  // the note sits under. The provider and model are one group: dirty if either key is.
  var GROUPS = [
    { id: 'description', keys: ['description'], noteKey: 'description' },
    { id: 'model', keys: ['provider_config_id', 'llm_model'], noteKey: 'llm_model' },
    { id: 'system_prompt', keys: ['system_prompt'], noteKey: 'system_prompt' },
    { id: 'max_iterations', keys: ['max_iterations'], noteKey: 'max_iterations' },
    { id: 'retention', keys: ['chat_history_retention_days'], noteKey: 'chat_history_retention_days' },
    { id: 'rich_visuals', keys: ['rich_visuals'], noteKey: 'rich_visuals' }
  ];

  // The tab groups (L8): a set of switches on another tab, each item its own tile or row. `handle`
  // is the editor handle's tab (the Tools tab's built-in rows, the MCP tiles, the Knowledge rows);
  // the tab handle gives followMap / followMapFor / followSet / followPlace (see tools-tab.js).
  var TAB_GROUPS = [
    { id: 'tools', keys: ['enabled_tools', 'disabled_tools'], handle: 'tools' },
    { id: 'mcp_source_ids', keys: ['mcp_source_ids'], handle: 'mcps' },
    { id: 'kb_ids', keys: ['kb_ids'], handle: 'knowledge' }
  ];

  // The items an approval changed, per agent and group: {agent: {group: {item: true}}}. The
  // record only carries field names, so the apply notes which items moved; it outlives a tab
  // rebuild (the notes are redrawn from it at every mount) and goes with clear(name).
  var changedItems = {};

  var activeHandle = null;
  var registered = false;

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function parse_(s) { try { return JSON.parse(s); } catch (e) { return null; } }

  // The two "operator changed it" tests (module scope since M36 F3 L6: the form fill reads them
  // too): a field group differs from its baseline in any of its keys; a tab item differs from the
  // baseline's switch.
  function dirtyGroup_(g, cur, base) {
    return g.keys.some(function (k) { return !same(cur[k], base[k]); });
  }

  function tabItemDirty_(curMap, baseMap, item) {
    return curMap[item] !== baseMap[item];
  }

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var editorEl = ctx.editorEl;
    var getFormSnapshot = ctx.getFormSnapshot;
    var checkDirty = ctx.checkDirty;
    var currentData_ = ctx.currentData;

    // `live` = the open editor is this agent's edit mount and no Save is mid-flight. No
    // section term: a hidden editor is patched too (the next activation re-patches and the
    // notes come back from the record).
    function liveFor_(name) {
      var d = currentData_();
      return d && d.handle && d.key === 'edit:' + name && !ctx.saveInFlight() ? d : null;
    }

    // ── The notes (board option A) ───────────────────────────────────

    function removeNotes_() {
      var old = editorEl.querySelectorAll('[data-testid="' + NOTE_TESTID + '"]');
      for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    }

    function buildNote_(noteKey, hit, item) {
      return App.gleepglorpFollow.buildNote(hit,
        { testid: 'agent-approved-change-note', field: noteKey, item: item });
    }

    // Draw the notes for the open agent from the record: every mount, patch and live apply.
    function drawNotes_() {
      var d = currentData_();
      removeNotes_();
      if (!d || !d.handle || !/^edit:/.test(d.key)) return;
      var rec = App.approvals.forAgent(d.key.slice(5));
      GROUPS.forEach(function (g) {
        var hit = null;
        g.keys.forEach(function (k) {
          if (rec[k] && (!hit || rec[k].at > hit.at)) hit = rec[k];
        });
        if (!hit) return;
        // The General tab owns its layout: it puts the note directly under the control.
        d.handle.general.placeNote(g.noteKey, buildNote_(g.noteKey, hit));
      });
      var name = d.key.slice(5);
      // Tile items: the approval record's (a return-path open has no live diff), plus an open
      // editor's own live diff.
      var items = Object.assign({}, App.approvals.itemsFor(name));
      var live = changedItems[name] || {};
      Object.keys(live).forEach(function (g) { items[g] = Object.assign({}, items[g], live[g]); });
      TAB_GROUPS.forEach(function (g) {
        var th = d.handle[g.handle];
        var hit = null;
        g.keys.forEach(function (k) {
          if (rec[k] && (!hit || rec[k].at > hit.at)) hit = rec[k];
        });
        if (!th || !hit) return;
        var mine = items[g.id] || {};
        Object.keys(mine).forEach(function (item) {
          th.followPlace(item, buildNote_(g.id, hit, item));
        });
      });
      // A rule or routine list: one note at the top of its list.
      [['rules', d.handle.rules], ['routines', d.handle.routines]].forEach(function (pair) {
        if (rec[pair[0]] && pair[1] && pair[1].placeNote) {
          pair[1].placeNote(buildNote_(pair[0], rec[pair[0]]));
        }
      });
    }

    // ── The central apply for the General fields ─────────────────────

    function writeClean_(general, g, updated) {
      if (g.id === 'model') {
        general.setModel(updated.provider_config_id, updated.llm_model);
      } else {
        g.keys.forEach(function (k) { general.setField(k, updated[k]); });
      }
    }

    // The model list refetches for the new provider with the stored model pending; the
    // baseline is rebased from the DOM now (the pending option is already selected) and
    // again once the list lands, unless the operator changed the pair meanwhile.
    function followModel_(d, updated, gen) {
      var group = GROUPS[1];
      var rebased = parse_(getFormSnapshot());
      var p = ctx.picker.fetchModelsForProvider(updated.provider_config_id);
      if (!p || typeof p.then !== 'function') return;
      p.then(function () {
        var now = currentData_();
        if (now !== d || d.wireGen !== gen) return;
        var cur = parse_(getFormSnapshot());
        var base = parse_(state.snapshot);
        if (!cur || !base) return;
        if (group.keys.some(function (k) { return !same(cur[k], rebased[k]); })) return;
        group.keys.forEach(function (k) { base[k] = cur[k]; });
        state.snapshot = JSON.stringify(base);
        checkDirty();
      });
    }

    // A tab group, item by item: an item the operator has not touched takes the stored value; an
    // item they changed keeps their choice. The baseline takes the stored value for every item
    // (written, read back from the form, then the kept choices are put back).
    function applyTabGroup_(d, g, updated, base) {
      var th = d.handle[g.handle];
      var curMap = th && th.followMap();
      if (!curMap) return;
      var baseMap = th.followMapFor(base);
      var newMap = th.followMapFor(updated);
      var finalMap = {};
      var mine = ((changedItems[updated.name] || (changedItems[updated.name] = {}))[g.id] ||
        (changedItems[updated.name][g.id] = {}));
      Object.keys(curMap).forEach(function (item) {
        var dirty = tabItemDirty_(curMap, baseMap, item);
        finalMap[item] = dirty ? curMap[item] : newMap[item];
        if (newMap[item] !== baseMap[item]) {
          mine[item] = true;
        }
      });
      var names = updated.kb_tool_names || {};
      th.followSet(newMap, g.id === 'kb_ids' ? names : null);
      var snap = parse_(getFormSnapshot());
      if (snap) g.keys.forEach(function (k) { if (k in snap) base[k] = snap[k]; });
      th.followSet(finalMap, g.id === 'kb_ids' ? names : null);
    }

    function applyAgent_(d, updated, fields) {
      var h = d.handle;
      var general = h.general;
      var cur = parse_(getFormSnapshot());
      var base = parse_(state.snapshot);
      if (!cur || !base) return;
      var touched = GROUPS.filter(function (g) {
        return g.keys.some(function (k) { return fields.indexOf(k) !== -1; });
      });
      var noted = [];
      var cleaned = [];
      touched.forEach(function (g) {
        if (dirtyGroup_(g, cur, base)) {
          // The operator's text stays; the baseline moves to the stored value.
          if (g.id === 'model') {
            base.provider_config_id = updated.provider_config_id;
            base.llm_model = updated.llm_model;
          } else {
            g.keys.forEach(function (k) {
              general.setField(k, updated[k]);
              base[k] = parse_(getFormSnapshot())[k];
              general.setField(k, cur[k]);
            });
          }
          noted.push(g.noteKey);
        } else {
          writeClean_(general, g, updated);
          cleaned.push(g);
        }
      });
      if (fields.indexOf('description') !== -1) h.shell.setSubtitle(updated.description || '');
      TAB_GROUPS.forEach(function (g) {
        if (g.keys.some(function (k) { return fields.indexOf(k) !== -1; })) {
          applyTabGroup_(d, g, updated, base);
        }
      });
      var after = parse_(getFormSnapshot());
      cleaned.forEach(function (g) { g.keys.forEach(function (k) { base[k] = after[k]; }); });
      state.snapshot = JSON.stringify(base);
      if (noted.length) {
        var all = (d.noteFields || []).slice();
        noted.forEach(function (f) { if (all.indexOf(f) === -1) all.push(f); });
        d.noteFields = all;
        general.setStoredChangeNote(all);
      }
      var gen = d.wireGen;
      if (cleaned.some(function (g) { return g.id === 'model'; })) followModel_(d, updated, gen);
      checkDirty();
      drawNotes_();
    }

    function adoptFresh_(updated) {
      if (self._selectedAgent && self._selectedAgent.name === updated.name) {
        self._selectedAgent = updated;
      }
      for (var i = 0; i < (self._agents || []).length; i++) {
        if (self._agents[i].name === updated.name) { self._agents[i] = updated; break; }
      }
      ctx.list().render();
    }

    function liveApply_(detail) {
      var name = detail.agent;
      if (!liveFor_(name)) return;
      var fields = detail.fields || [];
      // An MCP server attached from another window may not be in the cached list yet.
      var sources = fields.indexOf('mcp_source_ids') !== -1 && ctx.refreshMcpSources ?
        ctx.refreshMcpSources() : Promise.resolve();
      Promise.all([ctx.fetchAgent(name), sources]).then(function (res) {
        var updated = res[0];
        var d = liveFor_(name);
        if (!d) return;
        adoptFresh_(updated);
        if (fields.indexOf('mcp_source_ids') !== -1 && d.handle.mcps) {
          d.handle.mcps.setSources(self._allMcpSources, name);
        }
        applyAgent_(d, updated, fields);
      }, function () { /* the next activation re-patches */ });
    }

    // A rule or routine approved: its list reloads (an open form or inline edit is kept) and the
    // list's note is drawn from the record.
    function liveList_(detail) {
      var d = liveFor_(detail.agent);
      if (!d) return;
      var list = detail.kind === 'rule' ? d.handle.rules : d.handle.routines;
      drawNotes_();
      if (list && list.reload) list.reload();
    }

    function onEvent(detail) {
      if (!detail || !detail.agent) return;
      var cur = App.router.current && App.router.current();
      if (cur && cur.destination === 'agents') {
        App.store.get('agents', { force: true }).catch(function () { /* the next load retries */ });
      }
      if (detail.kind === 'agent') liveApply_(detail);
      else if (detail.kind === 'rule' || detail.kind === 'routine') liveList_(detail);
    }

    function clear(name) {
      if (name) { App.approvals.clear(name); delete changedItems[name]; }
    }

    var handle = { afterMount: drawNotes_, clear: clear, onEvent: onEvent };
    activeHandle = handle;
    if (!registered) {
      registered = true;
      document.addEventListener(App.approvals.CONFIG_CHANGED, function (e) {
        if (activeHandle) activeHandle.onEvent(e.detail);
      });
    }
    return handle;
  }

  window.App.studio.agentEditorFollow = {
    create: create,
    GROUPS: GROUPS,
    TAB_GROUPS: TAB_GROUPS,
    dirtyGroup: dirtyGroup_,
    tabItemDirty: tabItemDirty_
  };
})();
