// App.approvals -- the client's record of changes the operator approved (M36 F2 L7, DD10).
//
// Eager (loaded before the chat socket), because the signal can arrive before Studio has ever
// initialised: the operator approves in Chats, then opens Agents for the first time. Every
// editor mount reads the record to draw its "Changed by a change you approved" notes.
//
// A change comes from two places that carry the same detail, so a de-duplication set drops the
// second: the server's `config_changed` frame (to every socket) and the applied proposal in the
// approve response (the window that clicked Approve).
//
// detail: {kind: 'agent' | 'rule' | 'routine', agent, fields: [stored field names], session_id,
//          proposal_id, at, items?: {tools|mcp_source_ids|kb_ids: [item ids]}}
//   items names which tiles moved (the proposal view's base against its changes); it is merged
//   even for a proposal id already seen, and App.approvals.itemsFor(name) reads it back.
//
//   App.approvals.record(detail)   -> false for a proposal already seen, else true: merges the
//       change into the agent's record (fields keyed by stored name; a rule or routine kind is
//       recorded under 'rules' / 'routines'), invalidates the agents store and emits
//       CONFIG_CHANGED on the document (the Studio event bus's transport) for listeners.
//   App.approvals.forAgent(name)   -> {field: {at, session_id}} (a copy; {} when none)
//   App.approvals.clear(name)      -> empties that agent's record
//   App.approvals.CONFIG_CHANGED   -> the event name
(function () {
  'use strict';
  window.App = window.App || {};

  var CONFIG_CHANGED = 'approvals-config-changed';
  var SEEN_CAP = 200;
  var KIND_KEYS = { rule: 'rules', routine: 'routines' };
  var byAgent = {};
  var itemsByAgent = {};
  var seen = [];

  function remember(id) {
    if (seen.indexOf(id) !== -1) return false;
    seen.push(id);
    if (seen.length > SEEN_CAP) seen.shift();
    return true;
  }

  // Merge {group: [item, ...]} into the agent's item record (the tile notes read it on mount).
  function mergeItems(agent, items) {
    if (!items) return;
    var rec = itemsByAgent[agent] || (itemsByAgent[agent] = {});
    Object.keys(items).forEach(function (g) {
      var mine = rec[g] || (rec[g] = {});
      (items[g] || []).forEach(function (it) { mine[it] = true; });
    });
  }

  function record(detail) {
    if (!detail || !detail.agent) return false;
    // The socket frame may arrive first with fields only: a repeat still merges its items.
    mergeItems(detail.agent, detail.items);
    if (detail.proposal_id !== undefined && detail.proposal_id !== null &&
        !remember(detail.proposal_id)) return false;
    var at = detail.at || new Date().toISOString();
    var rec = byAgent[detail.agent] || (byAgent[detail.agent] = {});
    var keys = KIND_KEYS[detail.kind] ? [KIND_KEYS[detail.kind]] : (detail.fields || []);
    keys.forEach(function (f) { rec[f] = { at: at, session_id: detail.session_id || null }; });
    try { App.store.invalidate('agents'); } catch (e) { /* the store is eager; belt and braces */ }
    var event = {
      kind: detail.kind, agent: detail.agent, fields: (detail.fields || []).slice(),
      session_id: detail.session_id || null, proposal_id: detail.proposal_id, at: at
    };
    if (window.App.studio && App.studio.eventBus) App.studio.eventBus.emit(CONFIG_CHANGED, event);
    else document.dispatchEvent(new CustomEvent(CONFIG_CHANGED, { detail: event }));
    return true;
  }

  function forAgent(name) {
    var rec = byAgent[name] || {};
    var out = {};
    Object.keys(rec).forEach(function (k) { out[k] = { at: rec[k].at, session_id: rec[k].session_id }; });
    return out;
  }

  // {group: {item: true}} the approvals changed, for the tab tiles' notes (a copy).
  function itemsFor(name) {
    var rec = itemsByAgent[name] || {};
    var out = {};
    Object.keys(rec).forEach(function (g) { out[g] = Object.assign({}, rec[g]); });
    return out;
  }

  function clear(name) { delete byAgent[name]; delete itemsByAgent[name]; }

  window.App.approvals = {
    CONFIG_CHANGED: CONFIG_CHANGED, record: record, forAgent: forAgent, itemsFor: itemsFor, clear: clear
  };
})();
