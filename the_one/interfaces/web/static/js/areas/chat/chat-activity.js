// App.chat.activity -- the Chats list's per-row activity state (M31 F6 L10b).
//
// Pure client bookkeeping over the sessions rows' two server fields: `busy` (a
// turn is running on the session: web or connector) and `turn_seq` ("{boot}:{n}",
// n = turns finished since the server started). A row shows:
//   'working'  while busy (the open chat too);
//   'new'      when it is idle, is not the open chat and its n is above the n this
//              window last "saw" (a new reply landed while the operator was elsewhere);
//   null       otherwise.
// Rules (leg 10b, design cycle 2):
//   * The first observe() sets every row's baseline silently ("baselined"); a socket
//     reconnect does NOT re-baseline, so a reply that landed during the gap lights.
//   * A row first seen after baselining has seen 0, so its first finished turn lights.
//   * The open chat never accumulates debt: observe() sets seen = latest for it.
//   * `latest` keeps the larger n per id within an epoch, so a stale REST refetch never
//     lowers it. A changed boot id (server restart) re-baselines everything silently.
//   * Nothing persists: a reload re-baselines; each tab keeps its own `seen`.
//
// API: var a = App.chat.activity.create();
//   a.observe(rows, openId)        -> void  (call before stateFor, every list render)
//   a.stateFor(row, openId)        -> 'working' | 'new' | null
//   a.parse(turn_seq)              -> {epoch, n} | null
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function parse(seq) {
    if (typeof seq !== 'string') return null;
    var i = seq.lastIndexOf(':');
    if (i <= 0) return null;
    var n = parseInt(seq.slice(i + 1), 10);
    if (isNaN(n) || n < 0) return null;
    return { epoch: seq.slice(0, i), n: n };
  }

  function create() {
    var epoch = null;
    var latest = {};
    var seen = {};
    var baselined = false;

    function observe(rows, openId) {
      var list = Array.isArray(rows) ? rows : [];
      var i;
      var p;
      // A changed epoch is a server restart: drop every counter and baseline again.
      for (i = 0; i < list.length; i++) {
        p = list[i] ? parse(list[i].turn_seq) : null;
        if (p && epoch !== null && p.epoch !== epoch) {
          latest = {};
          seen = {};
          baselined = false;
          epoch = p.epoch;
          break;
        }
        if (p && epoch === null) epoch = p.epoch;
      }
      for (i = 0; i < list.length; i++) {
        p = list[i] ? parse(list[i].turn_seq) : null;
        if (!p || p.epoch !== epoch) continue;
        var id = list[i].id;
        if (!Object.prototype.hasOwnProperty.call(latest, id) || p.n > latest[id]) latest[id] = p.n;
      }
      if (!baselined) {
        for (var id2 in latest) {
          if (Object.prototype.hasOwnProperty.call(latest, id2)) seen[id2] = latest[id2];
        }
        baselined = true;
      }
      if (openId !== null && openId !== undefined && Object.prototype.hasOwnProperty.call(latest, openId)) {
        seen[openId] = latest[openId];
      }
    }

    function stateFor(row, openId) {
      if (!row) return null;
      if (row.busy) return 'working';
      if (row.id === openId) return null;
      if (!Object.prototype.hasOwnProperty.call(latest, row.id)) return null;
      var s = Object.prototype.hasOwnProperty.call(seen, row.id) ? seen[row.id] : 0;
      return latest[row.id] > s ? 'new' : null;
    }

    return { observe: observe, stateFor: stateFor, parse: parse };
  }

  window.App.chat.activity = { create: create, parse: parse };
})();
