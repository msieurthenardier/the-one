// App.gleepglorpDrawerFill -- the drawer's applier for GleepGlorp form fills (M36 F3 L6, flight
// DD7). The drawer instance that sent a turn applies the `fill_requested` that turn produced;
// every other instance only draws its receipt.
//
//   var fill = App.gleepglorpDrawerFill.create({ instance: function () { return chatInstance; } });
//   fill.enqueue(view, sessionId)   a fill_requested for this window's turn (the instance's
//                                   `onFillRequested` config hook)
//   fill.fillNow(view)              the receipt's Fill now: Promise<{busy}|...> (a claim refused
//                                   because another window is applying it resolves {busy: true})
//   fill.isApplying(id)             this window has the fill queued or running (the receipts'
//                                   `fillHooks.isApplying`)
//
// A per-window queue: fills run strictly one at a time, in id order. For each: claim (a refused
// claim skips the fill silently), the Chats check, the open-dialog check, navigation to the
// editor, the wait for it to settle, the write (App.studio.agentEditorFill.apply) and the
// outcome. Nothing is stored by a fill: the values arrive as unsaved edits, and only the
// operator's Save stores them. Focus never moves (the router's `opener` is the drawer's
// composer, and a create form opened for a fill does not focus its name field).
(function () {
  'use strict';
  window.App = window.App || {};

  var CLAIM = '/api/gleepglorp/fills/';

  function postJson(url, body) {
    return App.api.fetchJson(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  }

  function composerInput() {
    return document.querySelector('[data-testid="gg-chat-input"]');
  }

  function create(opts) {
    var instance = opts.instance;
    var queue = [];
    var running = false;
    var applying = Object.create(null); // fill id -> true while queued or running here

    function receipts() {
      var inst = instance();
      return inst && inst.fillReceipts ? inst.fillReceipts : null;
    }

    function refresh() {
      var r = receipts();
      if (r) r.refresh();
    }

    // ── One fill ─────────────────────────────────────────────────────

    function report(id, claim, status, kept, reason) {
      return postJson(CLAIM + id + '/outcome', {
        claim: claim, status: status, kept: kept || [], reason: reason || null
      });
    }

    function agentExists(name) {
      return App.store.get('agents', { force: true }).then(function (list) {
        return (list || []).some(function (a) { return a.name === name; });
      }, function () { return true; }); // unknown: do not call it gone
    }

    function routeFor(view) {
      return view.action === 'create'
        ? { destination: 'agents', create: true }
        : { destination: 'agents', id: view.agent_name };
    }

    // Open the editor the fill targets and wait for it. Resolves null when ready, or the reason
    // the fill could not go on ('stay' or 'editor_unavailable').
    function open(view) {
      var isCreate = view.action === 'create';
      var key = isCreate ? 'create' : 'edit:' + view.agent_name;
      var mod = App.studio.agentEditorFill;
      if (mod.isOpen(key)) {
        mod.selectGeneral();
        return mod.whenSettled(key).then(function (ok) { return ok ? null : 'editor_unavailable'; });
      }
      var list = App.studio.agentsList;
      if (isCreate) list.suppressNextCreateFocus();
      // The flag is one-shot and always cleared when this navigation ends (a Stay, an open form
      // or a superseded navigation never leak it to the next New agent).
      function clearFlag() { list.clearCreateFocusSuppression(); }
      return App.router.go(App.router.href(routeFor(view)), { opener: composerInput() })
        .then(function (went) {
          if (!went) { clearFlag(); return 'stay'; }
          return mod.whenSettled(key).then(function (ok) {
            clearFlag();
            return ok ? null : 'editor_unavailable';
          });
        }, function () { clearFlag(); return 'editor_unavailable'; });
    }

    function process(view, claim) {
      var id = view.id;
      var cur = App.router.current();
      if (!cur || cur.destination === 'chats') {
        return report(id, claim, 'not_filled', [], 'in_chats');
      }
      if (App.ui.modal.anyOpen() || App.router.isDeciding()) {
        return report(id, claim, 'not_filled', [], 'stay');
      }
      var isChange = view.action !== 'create';
      if (isChange && view.target_gone) return report(id, claim, 'not_filled', [], 'target_gone');
      var existing = isChange ? agentExists(view.agent_name) : Promise.resolve(true);
      return existing.then(function (exists) {
        if (!exists) return report(id, claim, 'not_filled', [], 'target_gone');
        return open(view).then(function (problem) {
          if (problem === 'editor_unavailable' && isChange) {
            // The agent may have gone while the editor was opening.
            return agentExists(view.agent_name).then(function (still) {
              return report(id, claim, 'not_filled', [], still ? 'editor_unavailable' : 'target_gone');
            });
          }
          if (problem) return report(id, claim, 'not_filled', [], problem);
          return App.studio.agentEditorFill.apply(view).then(function (res) {
            if (res.unavailable) return report(id, claim, 'not_filled', [], 'editor_unavailable');
            if (res.kept.length) return report(id, claim, 'partly_filled', res.kept, null);
            return report(id, claim, 'filled', [], null);
          });
        });
      });
    }

    function run(item) {
      var id = item.view.id;
      return postJson(CLAIM + id + '/claim', {}).then(function (res) {
        return process(res.fill, res.claim);
      }, function (err) {
        // Refused: replaced, final or claimed elsewhere. Skipped silently (Fill now on an
        // `applying` fill says so on the receipt).
        if (err && err.status === 409) {
          var st = err.detail && err.detail.status;
          return { busy: st === 'applying' };
        }
        return { failed: true };
      });
    }

    // ── The queue ────────────────────────────────────────────────────

    function drain() {
      if (running || !queue.length) return;
      running = true;
      queue.sort(function (a, b) { return a.view.id - b.view.id; });
      var item = queue.shift();
      var done = function (result) {
        delete applying[item.view.id];
        running = false;
        refresh();
        item.resolve(result || {});
        drain();
      };
      var step;
      try {
        step = run(item);
      } catch (err) {
        done({ failed: true });
        return;
      }
      step.then(done, function () { done({ failed: true }); });
    }

    function add(view, manual) {
      if (applying[view.id]) return Promise.resolve({});
      applying[view.id] = true;
      refresh();
      return new Promise(function (resolve) {
        queue.push({ view: view, manual: manual, resolve: resolve });
        // One microtask later, so fills delivered in the same turn are sorted by id first.
        Promise.resolve().then(drain);
      });
    }

    return {
      enqueue: function (view) { add(view, false); },
      fillNow: function (view) { return add(view, true); },
      isApplying: function (id) { return !!applying[id]; }
    };
  }

  window.App.gleepglorpDrawerFill = { create: create };
})();
