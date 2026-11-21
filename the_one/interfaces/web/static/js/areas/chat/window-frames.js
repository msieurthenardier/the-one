// App.chat.windowFrames -- the effects of the window-wide frames, shared by every chat
// instance's socket (M36 F3 L3, DD3). The Chats socket and the GleepGlorp drawer's socket both
// receive `sessions_changed`, `config_changed` and `gleepglorp_changed` (the server pushes them
// to every socket), so the global effects of each frame run once however many sockets are open;
// each instance's socket then does its own per-instance reaction (its session list, its drafts,
// a joined GleepGlorp chat's re-join).
//
//   App.chat.windowFrames.handle(data)       the global effects of `config_changed` and
//       `gleepglorp_changed`; true when the frame was one of them (the caller returns after its
//       own per-instance reaction), false for any other frame.
//   App.chat.windowFrames.sessionsChanged(rows)  true when the mapped session rows differ from
//       the `sessions` store's current value (the caller primes the store only then; the prime
//       stays in socket.js, where the sessions_changed branch reads it).
//
// De-duplication:
//   config_changed             App.approvals.record (it de-duplicates by proposal id);
//   gleepglorp_changed         App.gleepglorp.prime only when the settings differ from the
//                              client's copy (stable JSON compare);
//   notes-only gleepglorp_changed  the `gleepglorp-notes-changed` event at most once per 50 ms.
// App.gleepglorp.prime's own contract is unchanged (the Settings page Save still notifies).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var NOTES_WINDOW_MS = 50;
  var lastNotesAt = -Infinity;

  // JSON with sorted keys, so two objects with the same content compare equal.
  function stable(v) {
    if (v === null || typeof v !== 'object') return JSON.stringify(v);
    if (Array.isArray(v)) return '[' + v.map(stable).join(',') + ']';
    return '{' + Object.keys(v).sort().map(function (k) {
      return JSON.stringify(k) + ':' + stable(v[k]);
    }).join(',') + '}';
  }

  function sessionsChanged(rows) {
    var peeked = App.store.peek('sessions');
    if (!peeked.loaded || !Array.isArray(peeked.value)) return true;
    return stable(rows) !== stable(peeked.value);
  }

  function handle(data) {
    if (!data) return false;
    if (data.type === 'config_changed') {
      // An approved GleepGlorp change reached the stored configuration (any window, any state):
      // the editors, list and drawer follow it (M36 F2 L7).
      App.approvals.record(data);
      return true;
    }
    if (data.type === 'gleepglorp_changed') {
      if (!data.settings) {
        // A notes-only push (a delete or Clear all in Settings > GleepGlorp): it only tells an
        // open Memory list to reload. Two sockets deliver it in separate tasks.
        var now = (window.performance && performance.now) ? performance.now() : Date.now();
        if (now - lastNotesAt >= NOTES_WINDOW_MS) {
          lastNotesAt = now;
          window.dispatchEvent(new Event('gleepglorp-notes-changed'));
        }
        return true;
      }
      var cur = App.gleepglorp.peek().value;
      if (!cur || stable(cur) !== stable(data.settings)) App.gleepglorp.prime(data.settings);
      return true;
    }
    return false;
  }

  window.App.chat.windowFrames = { handle: handle, sessionsChanged: sessionsChanged };
})();
