(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};
  App.ui.util = App.ui.util || {};

  // The widget lifecycle manager (M35 F2 L5, flight DD7 and DD9). Not a control: no App.ui factory,
  // no row of its own (the `widget` row documents it). Loaded after widget.js, which it extends:
  //   App.ui.util.widgetReconcile(facts) -> {states, load, unload, capped}   (pure, below)
  //   App.ui.widget._manager   the registry the managed cards register with
  //   App.ui.widget._clock()   now() in ms (default performance.now); a test may replace it
  //   App.ui.widget._tick()    run one page tick synchronously (test-only)
  //   App.ui.widget._counts()  {observers, ticks, listeners, cards} (test-only)
  //   App.ui.widget._stale()   the stale-key set as an array (test-only)
  //
  // One decision function and events that only update facts: every event (an observer callback,
  // visibilitychange, a card's Start/Pause/Resume/Restart/stop/destroy, the tick) updates a fact
  // and calls reconcile(); apply() diffs the answer against the cards and calls their API. That
  // keeps the observer, cap, ceiling and visibility races out.
  //
  // Limits: 3 running, 8 loaded, stall 5 s, suspend over 60 s, heartbeat 5 s, record 10 s (90 s
  // when it was written hidden).

  var RUN_CAP = 3;
  var LOAD_CAP = 8;
  var STALL_MS = 5000;
  var SUSPEND_MS = 60000;
  var BEAT_MS = 5000;
  var RECORD_FRESH_MS = 10000;
  var RECORD_FRESH_HIDDEN_MS = 90000;
  var RECORD_PREFIX = 'widget-running:';

  // ---- reconcile: pure ----
  // facts = {hidden, runCap?, loadCap?, instances: [fact, ...]} with the instances in document
  // order; a fact is {id, inView, userPaused, stopped, loaded, running, startOrder, startRequested,
  // lastVisibleAt, loadedAt}. Returns {states: {id: running | paused-auto | paused-user | waiting
  // | stopped}, load: [ids to mount], unload: [ids to drop], capped: [ids in view held back]}.
  // It never mutates its input.
  function reconcile(facts) {
    facts = facts || {};
    var runCap = facts.runCap || RUN_CAP;
    var loadCap = facts.loadCap || LOAD_CAP;
    var hidden = facts.hidden === true;
    var list = facts.instances || [];
    var states = {};
    var load = [];
    var unload = [];
    var capped = [];
    var loadedCount = 0;
    var candidates = [];
    var userLoads = [];

    list.forEach(function (f, idx) {
      if (f.loaded) loadedCount += 1;
      if (f.stopped) {
        states[f.id] = 'stopped';
      } else if (f.userPaused) {
        if (f.loaded) states[f.id] = 'paused-user';
        else if (f.inView && !hidden) {
          states[f.id] = 'paused-user';
          userLoads.push(f);
        } else states[f.id] = 'waiting';
      } else if (hidden || !f.inView) {
        states[f.id] = f.loaded ? 'paused-auto' : 'waiting';
      } else {
        candidates.push({ f: f, idx: idx });
      }
    });

    function tier(c) {
      if (c.f.startRequested) return 0;
      if (c.f.running) return 1;
      return c.f.loaded ? 2 : 3;
    }
    candidates.sort(function (a, b) {
      var ta = tier(a);
      var tb = tier(b);
      if (ta !== tb) return ta - tb;
      if (ta === 1) {
        // The newest-started running widgets keep their slots; the oldest-started yields.
        var d = (b.f.startOrder || 0) - (a.f.startOrder || 0);
        if (d !== 0) return d;
      }
      return a.idx - b.idx;
    });
    var wantLoad = [];
    candidates.forEach(function (c, n) {
      if (n < runCap) {
        states[c.f.id] = 'running';
        if (!c.f.loaded) wantLoad.push(c.f);
      } else if (c.f.loaded) {
        states[c.f.id] = 'paused-auto';
      } else {
        states[c.f.id] = 'waiting';
        capped.push(c.f.id);
      }
    });
    userLoads.forEach(function (f) {
      wantLoad.push(f);
    });

    // The loaded ceiling: a new load takes a free place, else unloads an off-screen widget (the
    // paused-auto one off screen longest, then the paused-user one), else it stays waiting.
    var gone = {};
    function victim() {
      var best = null;
      var pass;
      for (pass = 0; pass < 2 && !best; pass++) {
        list.forEach(function (f) {
          if (!f.loaded || f.inView || f.stopped || gone[f.id]) return;
          if (states[f.id] !== (pass === 0 ? 'paused-auto' : 'paused-user')) return;
          if (!best || (f.lastVisibleAt || 0) < (best.lastVisibleAt || 0) ||
              ((f.lastVisibleAt || 0) === (best.lastVisibleAt || 0) && (f.loadedAt || 0) < (best.loadedAt || 0))) {
            best = f;
          }
        });
      }
      return best;
    }
    wantLoad.forEach(function (f) {
      if (loadedCount < loadCap) {
        loadedCount += 1;
        load.push(f.id);
        return;
      }
      var v = victim();
      if (v) {
        gone[v.id] = true;
        unload.push(v.id);
        states[v.id] = 'waiting';
        load.push(f.id);
      } else {
        states[f.id] = 'waiting';
        if (!f.userPaused) capped.push(f.id);
      }
    });
    return { states: states, load: load, unload: unload, capped: capped };
  }
  App.ui.util.widgetReconcile = reconcile;

  // ---- the manager ----
  var recs = []; // registration order
  var byEl = null; // Map el -> rec
  var observer = null;
  var tickTimer = 0;
  var listening = false;
  var seq = 0;
  var startSeq = 0;
  var lastTickAt = 0;
  var hidden = false;
  var reconciling = false;
  var dirty = false;
  var staleKeys = {};
  var pageId = (function () {
    var s = '';
    var i;
    for (i = 0; i < 8; i++) s += Math.floor(Math.random() * 16).toString(16);
    return s;
  })();
  var recordKey = RECORD_PREFIX + pageId;

  function clock() {
    return App.ui.widget._clock();
  }

  // ---- crash record (storage, every access guarded) ----
  function storageGet(k) {
    try {
      return window.localStorage.getItem(k);
    } catch (e) {
      return null;
    }
  }
  function storageSet(k, v) {
    try {
      window.localStorage.setItem(k, v);
    } catch (e) { /* storage unavailable: no record */ }
  }
  function storageRemove(k) {
    try {
      window.localStorage.removeItem(k);
    } catch (e) { /* ignore */ }
  }
  function storageKeys() {
    var out = [];
    try {
      var i;
      for (i = 0; i < window.localStorage.length; i++) out.push(window.localStorage.key(i));
    } catch (e) { /* ignore */ }
    return out;
  }

  // A foreign record is stale when it is older than 10 s (90 s when it was written hidden, because
  // hidden timers are throttled to about once a minute). Its keys go into the in-memory set for
  // the page's lifetime and the record is deleted. A fresh record belongs to a live tab: ignored.
  function scanRecords() {
    var now = Date.now();
    storageKeys().forEach(function (k) {
      if (typeof k !== 'string' || k.indexOf(RECORD_PREFIX) !== 0 || k === recordKey) return;
      var rec;
      try {
        rec = JSON.parse(storageGet(k));
      } catch (e) {
        return;
      }
      if (!rec || typeof rec.ts !== 'number' || !Array.isArray(rec.keys)) return;
      var limit = rec.hidden === true ? RECORD_FRESH_HIDDEN_MS : RECORD_FRESH_MS;
      if (now - rec.ts <= limit) return;
      rec.keys.forEach(function (key) {
        if (typeof key === 'string') staleKeys[key] = true;
      });
      storageRemove(k);
    });
  }
  scanRecords();

  function writeRecord() {
    var keys = [];
    var any = false;
    recs.forEach(function (r) {
      if (r.handle._facts().loaded) {
        any = true;
        if (r.handle.key) keys.push(r.handle.key);
      }
    });
    if (!any) {
      storageRemove(recordKey);
      return;
    }
    try {
      storageSet(recordKey, JSON.stringify({ keys: keys, ts: Date.now(), hidden: document.hidden === true }));
    } catch (e) { /* ignore */ }
  }

  // ---- facts and apply ----
  function sortedRecs() {
    var connected = [];
    var rest = [];
    recs.forEach(function (r) {
      if (r.handle.el.isConnected) connected.push(r);
      else rest.push(r);
    });
    connected.sort(function (a, b) {
      if (a === b) return 0;
      var p = a.handle.el.compareDocumentPosition(b.handle.el);
      if (p & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
      if (p & Node.DOCUMENT_POSITION_PRECEDING) return 1;
      return a.id - b.id;
    });
    return connected.concat(rest);
  }

  function reconcileNow() {
    if (reconciling) {
      dirty = true;
      return;
    }
    reconciling = true;
    try {
      var guard = 0;
      do {
        dirty = false;
        pass();
        guard += 1;
      } while (dirty && guard < 5);
    } finally {
      reconciling = false;
    }
  }

  function pass() {
    var order = sortedRecs();
    var byId = {};
    var facts = order.map(function (r) {
      byId[r.id] = r;
      var f = r.handle._facts();
      return {
        id: r.id,
        inView: r.inView,
        userPaused: f.userPaused,
        stopped: f.stopped,
        loaded: f.loaded,
        running: r.handle.state() === 'running',
        startOrder: r.startOrder,
        startRequested: r.startRequested,
        lastVisibleAt: r.lastVisibleAt,
        loadedAt: r.loadedAt
      };
    });
    var out = reconcile({ hidden: hidden, instances: facts });
    out.unload.forEach(function (id) {
      var r = byId[id];
      r.handle.unload();
      r.lastBeatAt = null;
    });
    order.forEach(function (r) {
      var st = out.states[r.id];
      var h = r.handle;
      var wasRunning = h.state() === 'running';
      if (st === 'running') {
        h.autoResume();
        if (!h._facts().loaded) h._mount();
        if (!wasRunning) r.startOrder = ++startSeq;
      } else if (st === 'paused-auto') {
        h.autoPause();
      } else if (st === 'paused-user') {
        if (!h._facts().loaded) h._mount();
        else if (!r.inView || hidden) h.autoPause();
        else h.autoResume();
      }
      h._setCapped(out.capped.indexOf(r.id) >= 0);
      var nowLoaded = h._facts().loaded;
      if (nowLoaded && !r.wasLoaded) r.loadedAt = ++seq;
      r.wasLoaded = nowLoaded;
      if (nowLoaded || st === 'stopped') r.startRequested = false;
    });
    writeRecord();
  }

  // ---- observer, visibility, tick ----
  function onIntersect(entries) {
    var changed = false;
    entries.forEach(function (e) {
      var r = byEl && byEl.get(e.target);
      if (!r) return; // destroyed while this callback was queued: a no-op
      r.handle._seen();
      var rb = e.rootBounds;
      var inView = e.isIntersecting && (e.intersectionRatio >= 0.25 ||
        (rb && rb.height > 0 && e.intersectionRect.height >= 0.5 * rb.height));
      inView = !!inView;
      if (inView !== r.inView) {
        r.lastVisibleAt = clock();
        r.inView = inView;
        changed = true;
      }
    });
    // Backstop: a card removed from the page without destroy() is reaped here.
    if (App.ui.widget.sweep() > 0) changed = true;
    if (changed) reconcileNow();
  }

  function onVisibility() {
    hidden = document.hidden === true;
    if (!hidden) {
      var now = clock();
      lastTickAt = now;
      recs.forEach(function (r) {
        r.lastBeatAt = r.handle._facts().loaded ? now : null;
      });
    }
    reconcileNow();
  }

  function onPageHide() {
    storageRemove(recordKey);
  }

  function tick() {
    var now = clock();
    hidden = document.hidden === true;
    if (hidden) {
      lastTickAt = now;
      writeRecord();
      return;
    }
    var gap = now - lastTickAt;
    lastTickAt = now;
    var victims = [];
    var loaded = recs.filter(function (r) {
      return r.handle._facts().loaded;
    });
    if (gap > SUSPEND_MS) {
      // A suspend and resume, not a freeze: reset and stop nothing.
      recs.forEach(function (r) {
        r.lastBeatAt = r.handle._facts().loaded ? now : null;
      });
    } else if (gap >= STALL_MS) {
      victims = loaded;
    } else {
      loaded.forEach(function (r) {
        if (r.lastBeatAt !== null && now - r.lastBeatAt >= BEAT_MS) victims.push(r);
      });
    }
    victims.slice().forEach(function (r) {
      r.lastBeatAt = null;
      r.handle.stop('hung');
    });
    if (victims.length) reconcileNow();
    else writeRecord();
  }

  function install() {
    if (listening) return;
    listening = true;
    hidden = document.hidden === true;
    byEl = new Map();
    lastTickAt = clock();
    if (typeof window.IntersectionObserver === 'function') {
      var thresholds = [];
      var i;
      for (i = 0; i <= 20; i++) thresholds.push(i / 20);
      observer = new window.IntersectionObserver(onIntersect, { threshold: thresholds });
    }
    tickTimer = window.setInterval(tick, 1000);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', onPageHide);
  }

  function release() {
    if (!listening) return;
    listening = false;
    if (observer) {
      observer.disconnect();
      observer = null;
    }
    window.clearInterval(tickTimer);
    tickTimer = 0;
    document.removeEventListener('visibilitychange', onVisibility);
    window.removeEventListener('pagehide', onPageHide);
    byEl = null;
    storageRemove(recordKey);
  }

  // register(handle, setLink): hands the card its link {notify(type)} through setLink before the
  // first reconcile. Event types from the card: mount, loaded, beat, pause, resume, start,
  // restart, stop, escape, destroy.
  function register(handle, setLink) {
    install();
    var r = {
      id: ++seq,
      handle: handle,
      inView: !observer, // without IntersectionObserver every card counts as in view
      startRequested: false,
      startOrder: 0,
      lastVisibleAt: 0,
      loadedAt: 0,
      wasLoaded: false,
      lastBeatAt: null,
      gone: false
    };
    recs.push(r);
    byEl.set(handle.el, r);
    var link = {
      notify: function (type) {
        if (r.gone) return;
        if (type === 'destroy') {
          r.gone = true;
          recs.splice(recs.indexOf(r), 1);
          if (byEl) {
            if (observer) observer.unobserve(handle.el);
            byEl.delete(handle.el);
          }
          if (!recs.length) release();
          else reconcileNow();
          return;
        }
        if (type === 'mount' || type === 'escape') {
          r.lastBeatAt = null;
        } else if (type === 'loaded') {
          r.lastBeatAt = clock();
          return;
        } else if (type === 'beat') {
          r.lastBeatAt = clock();
          return;
        } else if (type === 'start' || type === 'restart') {
          if (type === 'start' && handle.key) delete staleKeys[handle.key];
          r.startRequested = true;
          r.lastBeatAt = null;
        } else if (type === 'stop') {
          r.lastBeatAt = null;
        }
        if (type !== 'mount') reconcileNow();
      }
    };
    setLink(link);
    handle._seen();
    if (handle.key && staleKeys[handle.key] === true) handle.stop('hung-last');
    if (observer) observer.observe(handle.el);
    reconcileNow();
  }

  App.ui.widget._manager = { register: register, reconcile: reconcile };
  App.ui.widget._clock = function () {
    return window.performance.now();
  };
  App.ui.widget._tick = tick;
  App.ui.widget._counts = function () {
    return {
      observers: observer ? 1 : 0,
      ticks: tickTimer ? 1 : 0,
      listeners: listening ? 2 : 0,
      cards: recs.length
    };
  };
  App.ui.widget._stale = function () {
    return Object.keys(staleKeys).sort();
  };
  App.ui.widget._pageId = function () {
    return pageId;
  };
})();
