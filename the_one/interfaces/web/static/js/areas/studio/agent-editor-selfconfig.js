// App.studio.agentEditorSelfConfig -- the agent editor's self-configuration refresh
// (split out of agent-editor-controller.js in M33 F3 L1): patches the open editor
// in place after a self-configuration write, rebases a dirty baseline and keeps the
// "stored value changed" note honest. A factory the controller calls once:
//
//   var sc = App.studio.agentEditorSelfConfig.create(ctx);
//
// ctx (controller -> module): self, state, getFormSnapshot, checkDirty, currentData()
// (the current mount's data or null), saveInFlight() (true while a Save is
// mid-request) and list() (the agents-list handle, call-time).
// handle: parseSnapshot(), recheckStoredNote(), onSelfConfigChanged(updated).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var self = ctx.self;
    var state = ctx.state;
    var getFormSnapshot = ctx.getFormSnapshot;
    var checkDirty = ctx.checkDirty;
    var currentData_ = ctx.currentData;
    var saveInFlight = ctx.saveInFlight;

    // ── Self-configuration refresh (M31 F2 L10a, DD9-3) ──────────────

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
    // their new stored value and mcp_source_ids gains or loses the changed id (kept
    // in the form's DOM order). The surface has no tile on the Tools tab, so it is
    // never in the form's ids and has no entry in the form's mcp_overrides.
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
      // `live` = the open editor is this agent's edit mount and no Save is mid-flight.
      // It deliberately has no section term: a write that resolves while the operator is
      // on Chats or Settings patches the hidden editor in place (accepted behaviour), and
      // leaving Agents for Library destroys the editor, so `d` is null there (squawk 0232).
      var live = !!d && !!d.handle &&
        d.key === 'edit:' + updated.name && !saveInFlight() && sameAgent;
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

    return {
      parseSnapshot: parseSnapshot_,
      recheckStoredNote: recheckStoredNote_,
      onSelfConfigChanged: onSelfConfigChanged
    };
  }

  window.App.studio.agentEditorSelfConfig = { create: create };
})();
