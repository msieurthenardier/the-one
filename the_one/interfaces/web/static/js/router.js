// App.router - the destination router (M25 F2 L3, flight DD1-DD4, DD7, DD12).
//
// Four destinations (Chats, Agents, Library, Settings) sit over the three
// existing area modules (chat, studio, admin) through an ALIAS TABLE:
//
//   destination   area     route                         area-level sub
//   chats         chat     chats[/{sessionId}]           [sessions/{id}]
//   agents        studio   agents[/{name}[/{tab}[/..]]]  agents[/...]
//   library       studio   library/knowledge[/{kbId}]    knowledge[/{kbId}]
//                          library/mcp[/~new|/{id}]      mcp-sources[/new|/{id}]
//                          library/connectors            connectors
//   settings      admin    settings/general              general
//                          settings/providers[/~new|/{id}] providers[/new|/{id}]
//                          settings/tools[/{name}]       tools[/{name}]
//                          settings/knowledge-indexing   knowledge
//                          settings/design-language      design-language  (dev mode)
//
// The areas keep speaking their own subs (hydrateState / serializeState); the
// router maps in both directions. `~new` is the reserved create segment (an
// agent named "new" is a legal name); on OUTPUT any id segment that starts with
// `~` is written as `%7E...` so no name or id can collide with it.
//
// Two URL primitives (DD4):
//   go(route, {replace, bypassGuard, opener}) -> Promise<boolean>   user INTENT: runs the
//       leave guard, writes the URL (push or replace), hydrates the target.
//       true = navigated, false = the user stayed.
//   sync(areaId, sub)   area-internal canonicalisation: always replaceState,
//       never guards, never hydrates; dropped when it would move the user.
//
// Commit sequence (go() and traversal; pinned by test_router_core.py):
//   1. resolve the target (redirect / alias)
//   2. guard, unless bypassed (concurrent requests join the pending decision)
//   3. write the URL (push or replace; a traversal is already there)
//   4. commit `current` and lastRoute(destination)
//   5. shell bits (aside, labels, top-bar current)
//   6. mountArea - panel lifecycle; activates only when the AREA MODULE changes
//   7. hydrateState(sub, {fresh})  - fresh: true for traversal/boot/typed, false for go()
//   8. sync(area, serializeState()) - post-hydrate canonicalisation
//
// History: every write stamps history.state = {seq}; a replace keeps the seq.
// popstate is the single authoritative traversal event (proved in Chromium and
// WebKit by test_router_popstate_engines.py); the hashchange that follows a
// popstate for the same URL is dropped. Stay after a traversal reverts with
// history.go(-delta) from the LIVE seq delta, or re-pushes when the arrival
// entry has a null state (a typed URL only: in-app `#` links are intercepted by
// App.nav and routed through go(), so they never arrive as a null-state entry;
// one duplicate entry, accepted).
//
// Leave guard: App.nav (nav.js) runs on EVERY go() (unless bypassGuard) and on
// every traversal, through the synchronous adapter in runGuard().
(function () {
  'use strict';
  window.App = window.App || {};

  // ── Tables ──────────────────────────────────────────────────────────────

  var DESTINATIONS = [
    { id: 'chats', label: 'Chats', area: 'chat', iconKey: 'chat', root: 'chats', sidebar: true },
    { id: 'agents', label: 'Agents', area: 'studio', iconKey: 'studio', root: 'agents', sidebar: false },
    { id: 'library', label: 'Library', area: 'studio', iconKey: 'database', root: 'library/knowledge', sidebar: true },
    { id: 'settings', label: 'Settings', area: 'admin', iconKey: 'admin', root: 'settings/general', sidebar: true }
  ];

  // Section rows for the destinations that have sections. `route` is the
  // route's second segment, `sub` the area module's section id. `create`
  // marks the sections whose area-level `new` is the route's reserved `~new`.
  var SECTIONS = [
    { dest: 'library', area: 'studio', route: 'knowledge', sub: 'knowledge', create: false },
    { dest: 'library', area: 'studio', route: 'mcp', sub: 'mcp-sources', create: true },
    { dest: 'library', area: 'studio', route: 'connectors', sub: 'connectors', create: false },
    { dest: 'settings', area: 'admin', route: 'general', sub: 'general', create: false },
    { dest: 'settings', area: 'admin', route: 'providers', sub: 'providers', create: true },
    { dest: 'settings', area: 'admin', route: 'tools', sub: 'tools', create: false },
    { dest: 'settings', area: 'admin', route: 'knowledge-indexing', sub: 'knowledge', create: false },
    { dest: 'settings', area: 'admin', route: 'design-language', sub: 'design-language', create: false, dev: true }
  ];

  var RESERVED_NEW = '~new';
  var BRAND = 'GleepGlorp AI';

  function destById(id) {
    for (var i = 0; i < DESTINATIONS.length; i++) if (DESTINATIONS[i].id === id) return DESTINATIONS[i];
    return null;
  }

  // ── Segments and encoding ───────────────────────────────────────────────

  function stripHash(h) { return String(h || '').replace(/^#/, ''); }

  function splitRoute(raw) {
    var out = [];
    var parts = String(raw || '').split('/');
    for (var i = 0; i < parts.length; i++) if (parts[i] !== '') out.push(parts[i]);
    return out;
  }

  // One owner of encodeURIComponent for route output. A leading `~` is also
  // escaped (`%7E`) because encodeURIComponent leaves `~` alone and it would
  // otherwise collide with the reserved `~new` create segment.
  function enc(value) {
    var s = encodeURIComponent(String(value));
    return s.charAt(0) === '~' ? '%7E' + s.slice(1) : s;
  }

  function dec(segment) {
    try { return decodeURIComponent(segment); } catch (e) { return segment; }
  }

  // Already-encoded segment pass-through on output: only the leading `~` is
  // rewritten. (serializeState's segments come out of encodeURIComponent.)
  function escapeEncoded(segment) {
    return segment.charAt(0) === '~' ? '%7E' + segment.slice(1) : segment;
  }

  // Compare two routes segment by segment after decoding, so `%20` vs a space
  // or a browser's own re-encoding never reads as a different route.
  function normRoute(route) {
    var segs = splitRoute(stripHash(route));
    for (var i = 0; i < segs.length; i++) segs[i] = enc(dec(segs[i]));
    return segs.join('/');
  }

  function sameRoute(a, b) { return normRoute(a) === normRoute(b); }

  // ── Route builder / parser (DD1) ────────────────────────────────────────

  // href({destination, section, id, tab, sub, create}) -> '#route'
  //   chats:    id = session id
  //   agents:   id = agent name, tab, sub (the MCP source id on the mcps tab)
  //   library / settings: section, id, or create:true for the `~new` segment
  function href(spec) {
    spec = spec || {};
    var segs = [spec.destination];
    if (spec.destination === 'chats') {
      if (spec.id != null) segs.push(enc(spec.id));
    } else if (spec.destination === 'agents') {
      if (spec.id != null) {
        segs.push(enc(spec.id));
        if (spec.tab != null) {
          segs.push(enc(spec.tab));
          if (spec.sub != null) segs.push(enc(spec.sub));
        }
      }
    } else {
      if (spec.section != null) {
        segs.push(spec.section);
        if (spec.create) segs.push(RESERVED_NEW);
        else if (spec.id != null) segs.push(enc(spec.id));
      }
    }
    return '#' + segs.join('/');
  }

  // parse(hash) -> {destination, section?, id?, tab?, sub?, create?} | null.
  // The inverse of href(); ids come back decoded.
  function parse(hash) {
    var segs = splitRoute(stripHash(hash));
    if (!segs.length || !destById(segs[0])) return null;
    var out = { destination: segs[0] };
    if (segs[0] === 'chats') {
      if (segs[1] != null) out.id = dec(segs[1]);
    } else if (segs[0] === 'agents') {
      if (segs[1] != null) out.id = dec(segs[1]);
      if (segs[2] != null) out.tab = dec(segs[2]);
      if (segs[3] != null) out.sub = dec(segs.slice(3).join('/'));
    } else {
      if (segs[1] != null) out.section = segs[1];
      if (segs[2] === RESERVED_NEW) out.create = true;
      else if (segs[2] != null) out.id = dec(segs[2]);
    }
    return out;
  }

  // ── Alias mapping: route <-> (area, sub) ────────────────────────────────

  function devMode() {
    return !!(window.App && window.App.config && window.App.config.dev_mode);
  }

  // area-level (area, sub) -> route string (no '#'), or null when unmapped.
  function areaSubToRoute(areaId, sub) {
    var segs = splitRoute(sub);
    var rest;
    var i;
    if (areaId === 'chat') {
      if (!segs.length) return 'chats';
      if (segs[0] === 'sessions') {
        return segs.length > 1 ? 'chats/' + escapeEncoded(segs[1]) : 'chats';
      }
      return null;
    }
    if (areaId === 'studio') {
      if (!segs.length) return null;
      if (segs[0] === 'agents') {
        rest = segs.slice(1);
        for (i = 0; i < rest.length; i++) rest[i] = escapeEncoded(rest[i]);
        return ['agents'].concat(rest).join('/');
      }
    }
    for (i = 0; i < SECTIONS.length; i++) {
      var s = SECTIONS[i];
      if (s.area !== areaId || segs[0] !== s.sub) continue;
      rest = segs.slice(1);
      var out = [s.dest, s.route];
      for (var j = 0; j < rest.length; j++) {
        out.push(j === 0 && s.create && rest[j] === 'new' ? RESERVED_NEW : escapeEncoded(rest[j]));
      }
      return out.join('/');
    }
    return null;
  }

  function rootOf(destId) {
    var d = destById(destId);
    return d ? d.root : null;
  }

  // Resolve an input hash or route to a target. Handles legacy hashes
  // (#chat, #studio/..., #admin/...) per the DD2 redirect table.
  //   -> {kind:'route', route, destination, area, sub, redirected}
  //    | {kind:'element'} | {kind:'unknown'} | {kind:'empty'}
  function resolve(input) {
    var raw = stripHash(input);
    var segs = splitRoute(raw);
    if (!segs.length) return { kind: 'empty' };
    var head = segs[0];
    var redirected = false;
    var route = null;

    if (head === 'chat' || head === 'studio' || head === 'admin') {
      redirected = true;
      var sub = segs.slice(1).join('/');
      if (head === 'studio' && (sub === '' || sub === 'tools')) route = 'agents';
      else if (head === 'admin' && (sub === '' || sub === 'system')) route = 'settings/general';
      else route = areaSubToRoute(head, sub);
      // Unknown sub of a known legacy area: the area's own default, as the
      // old areas defaulted (chat -> chat, studio -> agents).
      if (route == null && head === 'chat') route = 'chats';
      if (route == null && head === 'studio') route = 'agents';
      if (route == null) return unknownOrElement(raw);
      segs = splitRoute(route);
      head = segs[0];
    }

    var dest = destById(head);
    if (!dest) return unknownOrElement(raw);

    if (head === 'chats') {
      route = segs.length > 1 ? 'chats/' + segs[1] : 'chats';
      return mk(route, dest, segs.length > 1 ? 'sessions/' + segs[1] : null,
        redirected || segs.length > 2);
    }
    if (head === 'agents') {
      if (segs[1] === RESERVED_NEW) {
        // Agent create is Flight 3's; `#agents/~new` redirects to the root.
        return mk('agents', dest, 'agents', true);
      }
      route = segs.join('/');
      return mk(route, dest, route, redirected);
    }
    // library / settings: a bare destination redirects to its root section.
    if (segs.length === 1) {
      var rootTarget = resolve(dest.root);
      rootTarget.redirected = true;
      return rootTarget;
    }
    var row = null;
    for (var i = 0; i < SECTIONS.length; i++) {
      if (SECTIONS[i].dest === head && SECTIONS[i].route === segs[1]) { row = SECTIONS[i]; break; }
    }
    if (!row || (row.dev && !devMode())) return unknownOrElement(raw);
    var rest = segs.slice(2);
    var subParts = [row.sub];
    for (var k = 0; k < rest.length; k++) {
      subParts.push(k === 0 && row.create && rest[k] === RESERVED_NEW ? 'new' : rest[k]);
    }
    return mk(segs.join('/'), dest, subParts.join('/'), redirected);
  }

  function mk(route, dest, sub, redirected) {
    return {
      kind: 'route', route: route, destination: dest.id, area: dest.area, sub: sub,
      redirected: !!redirected
    };
  }

  function unknownOrElement(raw) {
    var id = dec(raw);
    var el = id ? document.getElementById(id) : null;
    return el ? { kind: 'element' } : { kind: 'unknown' };
  }

  // ── State ───────────────────────────────────────────────────────────────

  var host = null;            // {mountArea(areaId, destId), getArea(areaId)} from app.js
  var started = false;
  var current = null;         // {route, destination, area, sub}
  var lastRoutes = {};        // destination -> last route visited
  var curSeq = 0;             // seq of the history entry the router is on
  var deciding = null;        // {target, arrived, replace, waiters[]}
  var lastPopHash = null;     // the hash a popstate last handled (hashchange de-dupe)

  function seqOf(state) {
    return state && typeof state.seq === 'number' ? state.seq : null;
  }

  function writeUrl(route, replace) {
    var url = '#' + route;
    if (replace) {
      history.replaceState({ seq: curSeq }, '', url);
    } else {
      curSeq += 1;
      history.pushState({ seq: curSeq }, '', url);
    }
  }

  function hashMatchesCurrent() {
    if (!current) return false;
    var h = location.hash;
    if (sameRoute(h, current.route)) return true;
    // An element-id fragment (the skip link's #main-content) is not a route:
    // treat the URL as unchanged so it never drops later syncs.
    return resolve(h).kind === 'element';
  }

  function dialogOpen() {
    return !!(window.App.confirmDialog && typeof window.App.confirmDialog.isOpen === 'function' &&
      window.App.confirmDialog.isOpen());
  }

  // ── Shell bits (step 5) ─────────────────────────────────────────────────

  var commitHooks = [];

  // onCommit(fn) -> unsubscribe. fn(destinationId) runs on every committed
  // route (shell step 5), including boot.
  function onCommit(fn) {
    commitHooks.push(fn);
    return function unsubscribe() {
      var idx = commitHooks.indexOf(fn);
      if (idx !== -1) commitHooks.splice(idx, 1);
    };
  }

  // ── Route announcer + document title (WCAG 4.1.3 / 2.4.2) ───────────────

  var SECTION_LABELS = {
    knowledge: 'Knowledge', mcp: 'MCP servers', connectors: 'Connectors', general: 'General',
    providers: 'Providers', tools: 'Tools', 'knowledge-indexing': 'Knowledge indexing',
    'design-language': 'Design language'
  };
  var lastAnnounceKey = null; // destination/section/item of the last committed route

  // {parts, key} for a route. Only human-readable item names are spoken: an
  // agent name, a tool name, or "New"; opaque ids (sessions, providers, KBs)
  // are left out, but still make a different key (a different item).
  function describeRoute(route) {
    var p = parse(route);
    if (!p) return null;
    var parts = [destById(p.destination).label];
    if (p.section) parts.push(SECTION_LABELS[p.section] || p.section);
    var item = null;
    if (p.create) item = 'New';
    else if (p.destination === 'agents' && p.id) item = p.id;
    else if (p.section === 'tools' && p.id) item = p.id;
    if (item) {
      if (item.length > 30) item = item.slice(0, 29) + '\u2026';
      parts.push(item);
    }
    return { parts: parts, key: [p.destination, p.section || '', p.create ? '~new' : (p.id || '')].join('/') };
  }

  function applyTitle(route) {
    var d = describeRoute(route);
    document.title = (d ? d.parts.join(' \u2014 ') + ' \u00b7 ' : '') + BRAND;
  }

  function ensureAnnouncer() {
    var el = document.getElementById('route-announcer');
    if (!el) {
      el = document.createElement('div');
      el.id = 'route-announcer';
      el.className = 'visually-hidden';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.setAttribute('data-testid', 'route-announcer');
      document.body.appendChild(el);
    }
    return el;
  }

  // One polite live region (role=status), created empty at boot (start()) so
  // assistive tech has registered it before the first message, kept in the DOM.
  // Announces only a commit that changes destination/section/item; boot (first)
  // only records the key. Focus is never moved (DD5 owns the Continue focus).
  function announce(route, first) {
    var d = describeRoute(route);
    if (!d) return;
    var changed = d.key !== lastAnnounceKey;
    lastAnnounceKey = d.key;
    if (first || !changed) return;
    var el = ensureAnnouncer();
    el.textContent = d.parts.join(' \u2014 ');
  }

  function applyShell(destId) {
    var dest = destById(destId);
    var aside = document.getElementById('app-sidebar');
    if (aside) {
      aside.hidden = !dest.sidebar;
      aside.setAttribute('aria-label', dest.label);
    }
    // Commit subscribers (the rail): notified with the destination id, after
    // current/lastRoute are updated, so a subscriber reads lastRoute(dest).
    for (var i = 0; i < commitHooks.length; i++) {
      try { commitHooks[i](destId); } catch (err) { /* a subscriber must never break a commit */ }
    }
  }

  // ── Commit (steps 4-8) ──────────────────────────────────────────────────

  // `fresh` is the hydrate ORIGIN: true for a traversal (Back/Forward, a typed
  // hash) and for boot -- the target may name an item that no longer exists, so
  // the area must resolve it against a FRESH fetch; false for an intent go()
  // (a click on a row/tile), where the cached list is what the user just saw
  // and nothing is refetched.
  function commit(target, fresh, first) {
    // 4. current + lastRoute BEFORE hydrate, so syncs fired while hydrating
    //    are kept (the destination rule sees the new destination).
    current = { route: target.route, destination: target.destination, area: target.area, sub: target.sub };
    lastRoutes[target.destination] = target.route;
    // 5. shell bits
    applyShell(target.destination);
    applyTitle(target.route);
    announce(target.route, !!first);
    // 6. mountArea (panel lifecycle only; the module-change rule lives there)
    host.mountArea(target.area, target.destination);
    // 7. hydrate
    var area = host.getArea(target.area);
    if (area && typeof area.hydrateState === 'function') area.hydrateState(target.sub, { fresh: !!fresh });
    // 8. post-hydrate canonicalisation (default sub-routes, retained state).
    //    An area with nothing to serialise (chat before a join) leaves the URL.
    if (area && typeof area.serializeState === 'function') {
      var serialized = area.serializeState();
      if (serialized) sync(target.area, serialized);
    }
  }

  // ── Decisions: guard, join, settle ──────────────────────────────────────

  // The leave guard is App.nav (nav.js), adapted here WITHOUT losing the
  // synchronous fast path: when nothing is dirty the decision settles in the
  // same tick (the commit-sequence tests pin this), so this must never be
  // promisified for the clean case. A decision is Stay when a NON-router
  // App.nav dialog is pending (it never joins: Continue would run both
  // actions) or any other confirm dialog is open. Router-to-router joins are
  // `deciding`'s job alone.
  function runGuard() {
    var d = deciding;
    var nav = window.App.nav;
    // An already-open dialog (or a pending non-router decision) is in charge:
    // Stay on every entry path, clean or not (both checks are synchronous).
    if (dialogOpen() || (nav && nav.isPending())) { settle(false); return; }
    if (!nav || !nav.isDirty()) { settle(true); return; }
    nav.confirmLeave({ router: true, opener: d.opener || null, target: d.target.route }).then(
      function (ok) { if (deciding === d) settle(ok); },
      function () { if (deciding === d) settle(false); }
    );
  }

  function settle(ok) {
    var d = deciding;
    if (!d) return;
    deciding = null;
    if (ok) applyDecision(d);
    else revertDecision(d);
    for (var i = 0; i < d.waiters.length; i++) d.waiters[i](ok);
  }

  function applyDecision(d) {
    var t = d.target;
    if (d.arrived) {
      // The URL already moved (traversal). Adopt its entry's seq, stamping a
      // null state; rewrite the URL when a redirect or a joined go() changed
      // the target. Never push.
      var seq = seqOf(history.state);
      // A null state is a browser-initiated entry (a typed URL; in-app link
      // clicks are intercepted by App.nav): it sits directly after the entry
      // the router is on.
      if (seq == null) { seq = curSeq + 1; }
      curSeq = seq;
      if (!sameRoute(location.hash, t.route) || seqOf(history.state) == null) {
        history.replaceState({ seq: curSeq }, '', '#' + t.route);
      }
    } else {
      var replace = d.replace || !current || sameRoute(t.route, current.route);
      writeUrl(t.route, replace);
    }
    commit(t, !!d.arrived);
  }

  function revertDecision(d) {
    if (!d.arrived || !current) return; // a go() wrote nothing
    var live = seqOf(history.state);
    if (live == null) {
      // Null state (a typed URL; link clicks never arrive this way): no delta to travel. Re-push the
      // stayed route - one duplicate entry, documented.
      curSeq += 1;
      history.pushState({ seq: curSeq }, '', '#' + current.route);
    } else if (live === curSeq) {
      history.replaceState({ seq: curSeq }, '', '#' + current.route);
    } else {
      history.go(-(live - curSeq));
    }
  }

  function beginDecision(target, opts, arrived) {
    deciding = {
      target: target, arrived: !!arrived, replace: !!(opts && opts.replace),
      opener: (opts && opts.opener) || null, waiters: []
    };
    return deciding;
  }

  // ── go ──────────────────────────────────────────────────────────────────

  function go(input, opts) {
    opts = opts || {};
    var target = resolve(input);
    if (target.kind !== 'route' || !started) return Promise.resolve(false);
    return new Promise(function (resolvePromise) {
      if (deciding) {
        // Join the pending decision; the latest target wins.
        deciding.target = target;
        deciding.replace = !!opts.replace;
        if (opts.opener) deciding.opener = opts.opener;
        deciding.waiters.push(resolvePromise);
        return;
      }
      if (opts.bypassGuard) {
        applyDecision({ target: target, arrived: false, replace: !!opts.replace, waiters: [] });
        resolvePromise(true);
        return;
      }
      var d = beginDecision(target, opts, false);
      d.waiters.push(resolvePromise);
      runGuard();
    });
  }

  // ── sync ────────────────────────────────────────────────────────────────

  // Area-internal canonicalisation. Dropped when: the mapped destination is not
  // the current one; a decision is pending; or location.hash is not the
  // router's current URL (ignoring element-id fragments).
  function sync(areaId, sub) {
    if (!started || !current) return false;
    if (deciding) return false;
    var route = areaSubToRoute(areaId, sub);
    if (route == null) return false;
    var parsed = resolve(route);
    if (parsed.kind !== 'route' || parsed.destination !== current.destination) return false;
    if (!hashMatchesCurrent()) return false;
    var oldRoute = current.route;
    current = { route: parsed.route, destination: parsed.destination, area: parsed.area, sub: parsed.sub };
    lastRoutes[parsed.destination] = parsed.route;
    // Canonicalisation may name the item: retitle and record the key, never announce.
    applyTitle(parsed.route);
    var dd = describeRoute(parsed.route);
    if (dd) lastAnnounceKey = dd.key;
    if (!sameRoute(location.hash, parsed.route)) {
      // An element-id fragment (skip link) with an unchanged route is left in
      // place; any real change replaces it.
      var elementOnly = resolve(location.hash).kind === 'element' && sameRoute(oldRoute, parsed.route);
      if (!elementOnly) writeUrl(parsed.route, true);
    }
    return true;
  }

  // ── Traversal ───────────────────────────────────────────────────────────

  function rewriteInPlace(route) {
    var seq = seqOf(history.state);
    if (seq == null) { seq = curSeq + 1; }
    history.replaceState({ seq: seq }, '', '#' + route);
  }

  function handleArrival() {
    if (!started) return;
    var r = resolve(location.hash);
    if (r.kind === 'element') return; // never routed
    if (r.kind === 'unknown' || r.kind === 'empty') {
      // After boot: restore the current route (replace). A pending decision
      // owns the URL, so leave it alone.
      if (!deciding && current) rewriteInPlace(current.route);
      return;
    }
    if (r.redirected) rewriteInPlace(r.route); // before any further check; keeps/stamps seq
    if (!deciding && current && sameRoute(r.route, current.route)) {
      // Our own Stay revert, or a return from an element-id fragment: no-op.
      if (seqOf(history.state) == null) rewriteInPlace(current.route);
      return;
    }
    if (deciding) {
      // More traversals while a decision is pending: the latest target wins.
      deciding.target = r;
      deciding.arrived = true;
      return;
    }
    beginDecision(r, null, true);
    runGuard();
  }

  function onPopState() {
    lastPopHash = location.hash;
    handleArrival();
  }

  function onHashChange(e) {
    var h = '';
    try { h = new URL(e.newURL).hash; } catch (err) { h = location.hash; }
    if (lastPopHash != null && h === lastPopHash) { lastPopHash = null; return; }
    handleArrival();
  }

  // ── Boot ────────────────────────────────────────────────────────────────

  function start(hostApi) {
    if (started) return;
    host = hostApi;
    started = true;
    window.addEventListener('popstate', onPopState);
    window.addEventListener('hashchange', onHashChange);
    var seq = seqOf(history.state);
    if (seq == null) { seq = 1; }
    curSeq = seq;
    // At boot an unknown, empty or element-id hash goes to #chats.
    var target = resolve(location.hash);
    if (target.kind !== 'route') target = resolve('chats');
    history.replaceState({ seq: curSeq }, '', '#' + target.route);
    ensureAnnouncer();
    commit(target, true, true);
  }

  window.App.router = {
    destinations: DESTINATIONS,
    start: start,
    go: go,
    sync: sync,
    href: href,
    parse: parse,
    // The redirect/alias resolver (parity-tested against tests/browser/_nav.py).
    resolve: function (input) {
      var r = resolve(input);
      return r.kind === 'route'
        ? { kind: 'route', route: r.route, destination: r.destination, area: r.area, sub: r.sub, redirected: r.redirected }
        : { kind: r.kind };
    },
    // (area, sub) -> route, the alias table's output direction.
    routeFor: function (areaId, sub) { return areaSubToRoute(areaId, sub); },
    root: rootOf,
    current: function () {
      return current ? { route: current.route, destination: current.destination, area: current.area, sub: current.sub } : null;
    },
    onCommit: onCommit,
    lastRoute: function (destId) { return lastRoutes[destId] || rootOf(destId); },
    isDeciding: function () { return !!deciding; }
  };
})();
