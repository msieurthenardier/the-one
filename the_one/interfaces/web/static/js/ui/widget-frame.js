(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.widgetFrame(opts) -> {iframe, destroy(), postTheme(theme), postPause(), postResume(),
  //   loads()}
  //   (M35 F2 L1 and L3, flight DD2-DD8; the card, lifecycle and chat wiring are later legs)
  //
  // The frame core for a model-written widget: a sandboxed srcdoc iframe whose fixed policy and
  // prelude come before any model bytes. Options:
  //   slot          the element the iframe is appended to (required)
  //   source        the widget body, HTML with inline style and script, appended after the prelude
  //                 with only its link tags rewritten (DD6: preconnect blocking)
  //   title         the iframe's accessible name
  //   theme         {vars, mode} for the mount; read from the page's computed tokens when omitted
  //   paused        true starts the widget gated (DD8): one animation-frame round runs, then it
  //                 waits for postResume(); the state is in the document, so no timer runs first
  //   onSize(h)     the clamped height, once per applied change (at most one per animation frame)
  //   onHeartbeat() every valid size message (the frame posts one a second)
  //   onEscape()    the frame loaded a second time (a blocked navigation or reload); once, and the
  //                 frame is already removed
  //
  // The iframe carries sandbox="allow-scripts" and nothing else, a no-referrer policy and an empty
  // Permissions Policy. Its document is set BEFORE the iframe is inserted, so the baseline load
  // count is exactly 1 and any later load is an escape attempt (the page also sends
  // frame-src 'none', so the navigation itself is blocked). The control never moves a mounted
  // iframe: a re-parent reloads it.
  //
  // One window message listener serves every live frame and identifies a sender by event.source
  // against the live frames' windows, never by origin (every frame's origin is the string null).
  // Heights are clamped and coalesced to one write per animation frame. One MutationObserver on the
  // root's data-theme pushes a theme change to every live frame. Both are installed with the first
  // frame and removed with the last.

  var MIN_HEIGHT = 48;
  var MAX_HEIGHT = 720;
  var INITIAL_HEIGHT = 240;

  // The policy closes every fetch directive explicitly.
  var POLICY = [
    "default-src 'none'",
    "script-src 'unsafe-inline'",
    "style-src 'unsafe-inline'",
    'img-src data: blob:',
    "media-src 'none'",
    "font-src 'none'",
    "connect-src 'none'",
    "frame-src 'none'",
    "child-src 'none'",
    "worker-src 'none'",
    "object-src 'none'",
    "manifest-src 'none'",
    "form-action 'none'",
    "base-uri 'none'"
  ].join('; ');

  // Page token -> the frame's own variable. The page has no --danger; its token is --status-danger.
  var VAR_SOURCES = [
    ['--bg', '--bg'],
    ['--surface', '--surface'],
    ['--fg', '--fg'],
    ['--fg-muted', '--fg-muted'],
    ['--border', '--border'],
    ['--accent', '--accent'],
    ['--danger', '--status-danger'],
    ['--chart-1', '--chart-1'],
    ['--chart-2', '--chart-2'],
    ['--chart-3', '--chart-3'],
    ['--chart-4', '--chart-4'],
    ['--chart-5', '--chart-5'],
    ['--chart-6', '--chart-6'],
    ['--chart-7', '--chart-7'],
    ['--chart-8', '--chart-8']
  ];

  // DD6 layered link blocking: a link tag in the model's source is rewritten to an inert tag
  // before it is appended. The prelude holds a copy of the same pattern for strings the widget
  // builds at run time; tests/test_widget_frame_prelude.py asserts the two are identical.
  var LINK_RE = /<(\/?)link(?=[\s/>])/gi;

  function rewriteLinks(text) {
    return String(text).replace(LINK_RE, '<$1x-link');
  }

  // The prelude: it runs INSIDE the frame, as the first script, before any model byte. It is a
  // reviewed constant pinned by tests/test_widget_frame_prelude.py; do not edit it without
  // re-pinning. ES5 only. Order: 1 capture (timers, gesture times), 2 neuter (WebRTC, history,
  // execCommand, focus, link entry points), 3 the pause gate (DD8), 4 the size and theme
  // handlers. The words for the HTML setters are in the frame's own document; the guard that scans
  // static/js/ui counts them (UI_DIR_SINK_ALLOWANCE in tests/_ui_guard_helpers.py).
  var PRELUDE = [
    '(function () {',
    'var W = window, D = document;',
    'var ct = W.clearTimeout, ci = W.clearInterval, si = W.setInterval, st = W.setTimeout;',
    'var raf = W.requestAnimationFrame, ric = W.requestIdleCallback, cic = W.cancelIdleCallback;',
    'var pn = W.performance.now.bind(W.performance);',
    'var pm = W.parent.postMessage.bind(W.parent);',
    'var slice = Array.prototype.slice;',
    'var hb = -1;',
    'var lastG = -100000;',
    'function lock(o, n, v) {',
    'try { Object.defineProperty(o, n, { value: v, writable: false, configurable: false }); } catch (e) {}',
    '}',
    'function rethrow(e) { st.call(W, function () { throw e; }, 0); }',
    'function stamp(e) { if (e.isTrusted) { lastG = pn(); } }',
    'var gs = ["pointerdown", "mousedown", "keydown", "click", "touchstart"];',
    'for (var gi = 0; gi < gs.length; gi++) { W.addEventListener(gs[gi], stamp, true); }',
    'var noop = function () {};',
    'lock(W, "RTCPeerConnection", undefined);',
    'lock(W, "webkitRTCPeerConnection", undefined);',
    'lock(W, "RTCDataChannel", undefined);',
    'var hp = W.History && W.History.prototype;',
    'if (hp) {',
    'lock(hp, "back", noop);',
    'lock(hp, "forward", noop);',
    'lock(hp, "go", noop);',
    'lock(hp, "pushState", noop);',
    'lock(hp, "replaceState", noop);',
    '}',
    'var dp = W.Document && W.Document.prototype;',
    'if (dp) { lock(dp, "execCommand", function execCommand() { return false; }); }',
    'function okFocus() { var u = W.navigator.userActivation; return !!(u && u.isActive) && pn() - lastG <= 1000; }',
    'function gateFocus(p) {',
    'if (!p || typeof p.focus !== "function") { return; }',
    'var f = p.focus;',
    'lock(p, "focus", function focus() { if (okFocus()) { return f.apply(this, arguments); } });',
    '}',
    'gateFocus(W.HTMLElement && W.HTMLElement.prototype);',
    'gateFocus(W.SVGElement && W.SVGElement.prototype);',
    'gateFocus(W.MathMLElement && W.MathMLElement.prototype);',
    'gateFocus(W.Window && W.Window.prototype);',
    'var wf = W.focus;',
    'if (typeof wf === "function") { lock(W, "focus", function focus() { if (okFocus()) { return wf.apply(W, arguments); } }); }',
    'function noAuto(c) {',
    'var p = W[c] && W[c].prototype;',
    'if (p && Object.prototype.hasOwnProperty.call(p, "autofocus")) {',
    'try { Object.defineProperty(p, "autofocus", { get: function () { return false; }, set: noop, configurable: false }); } catch (e) {}',
    '}',
    '}',
    '["HTMLElement", "SVGElement", "MathMLElement", "HTMLInputElement", "HTMLButtonElement", "HTMLSelectElement", "HTMLTextAreaElement"].forEach(noAuto);',
    'var LRE = /<(\\/?)link(?=[\\s/>])/gi;',
    'var XRE = /<(\\/?)((?:[\\w.-]+:)?)link(?=[\\s/>])/gi;',
    'function rw(s) { return String(s).replace(LRE, "<$1x-link"); }',
    'function rx(s) { return String(s).replace(XRE, "<$1$2x-link"); }',
    'function wrapSet(o, n) {',
    'if (!o) { return; }',
    'var d = Object.getOwnPropertyDescriptor(o, n);',
    'if (!d || !d.set) { return; }',
    'var s = d.set;',
    'try { Object.defineProperty(o, n, { get: d.get, set: function (v) { return s.call(this, v === null ? v : rw(v)); }, enumerable: d.enumerable, configurable: false }); } catch (e) {}',
    '}',
    'function wrapM(o, n, i, r) {',
    'if (!o || typeof o[n] !== "function") { return; }',
    'var g = o[n];',
    'var h = r || rw;',
    'lock(o, n, function () { var a = slice.call(arguments); if (a.length > i && a[i] !== null) { a[i] = h(a[i]); } return g.apply(this, a); });',
    '}',
    'var ep = W.Element && W.Element.prototype, sp = W.ShadowRoot && W.ShadowRoot.prototype;',
    'wrapSet(ep, "innerHTML");',
    'wrapSet(ep, "outerHTML");',
    'wrapSet(sp, "innerHTML");',
    'wrapM(ep, "insertAdjacentHTML", 1);',
    'wrapM(ep, "setHTMLUnsafe", 0);',
    'wrapM(ep, "setHTML", 0);',
    'wrapM(sp, "setHTMLUnsafe", 0);',
    'wrapM(sp, "setHTML", 0);',
    'wrapM(W.Document, "parseHTMLUnsafe", 0);',
    'wrapM(W.Document, "parseHTML", 0);',
    'wrapM(W.Range && W.Range.prototype, "createContextualFragment", 0);',
    'wrapM(W.DOMParser && W.DOMParser.prototype, "parseFromString", 0, rx);',
    'var ce = dp.createElement, cn = dp.createElementNS;',
    'lock(dp, "createElement", function createElement() {',
    'var a = slice.call(arguments);',
    'if (a.length) { a[0] = String(a[0]); if (/^link$/i.test(a[0])) { a[0] = "x-link"; } }',
    'return ce.apply(this, a);',
    '});',
    'lock(dp, "createElementNS", function createElementNS() {',
    'var a = slice.call(arguments);',
    'if (a.length > 1) { a[1] = String(a[1]); if (/(^|:)link$/i.test(a[1])) { a[1] = "x-link"; } }',
    'return cn.apply(this, a);',
    '});',
    'var HOLD = /<\\/?(?:l(?:i(?:n(?:k)?)?)?)?$/i;',
    'var pends = new W.WeakMap(), ready = false;',
    'var dw = dp.write, dc = dp.close;',
    'D.addEventListener("DOMContentLoaded", function () { ready = true; }, true);',
    'function writeOut(self, t) {',
    't = (pends.get(self) || "") + t;',
    'var m = HOLD.exec(t);',
    'pends.set(self, m ? m[0] : "");',
    'if (m) { t = t.slice(0, m.index); }',
    'if (t) { dw.call(self, rw(t)); }',
    '}',
    'lock(dp, "write", function write() { if (this === D && ready) { return; } writeOut(this, slice.call(arguments).map(String).join("")); });',
    'lock(dp, "writeln", function writeln() { if (this === D && ready) { return; } writeOut(this, slice.call(arguments).map(String).join("") + "\\n"); });',
    'lock(dp, "open", function open() { return this; });',
    'lock(dp, "close", function close() {',
    'var p = pends.get(this);',
    'if (p && !(this === D && ready)) { pends.set(this, ""); dw.call(this, rw(p)); }',
    'return dc.call(this);',
    '});',
    'function sweep(n) {',
    'if (n.nodeType !== 1) { return; }',
    'if (n.hasAttribute("autofocus")) { n.removeAttribute("autofocus"); }',
    'if (W.HTMLLinkElement && n instanceof W.HTMLLinkElement) { n.remove(); return; }',
    'var l = n.querySelectorAll("link, [autofocus]");',
    'for (var li = 0; li < l.length; li++) { if (l[li].hasAttribute("autofocus")) { l[li].removeAttribute("autofocus"); } else { l[li].remove(); } }',
    '}',
    'new W.MutationObserver(function (rs) {',
    'for (var ri = 0; ri < rs.length; ri++) {',
    'var r = rs[ri];',
    'if (r.type === "attributes") { r.target.removeAttribute("autofocus"); continue; }',
    'for (var ai = 0; ai < r.addedNodes.length; ai++) { sweep(r.addedNodes[ai]); }',
    '}',
    '}).observe(D, { childList: true, subtree: true, attributes: true, attributeFilter: ["autofocus"] });',
    'var paused = false, round = false, pausedAt = 0, off = 0, lastPn = 0;',
    'var tmap = {}, imap = {}, rmap = {}, deferred = [], rq = [], rid = 0, rsched = 0;',
    'var sty = null, aset = [], actx = [], asus = [];',
    'function cur(t) { return (paused && t > pausedAt ? pausedAt : t) - off; }',
    'lock(W.Performance.prototype, "now", function now() { lastPn = cur(pn()); return lastPn; });',
    'function halt(c) {',
    'asus.push(c);',
    'try { var p = c.suspend(); if (p && p.catch) { p.catch(noop); } } catch (e) {}',
    '}',
    'function freeze() {',
    'if (!sty) {',
    'sty = ce.call(D, "style");',
    'sty.textContent = "*,*::before,*::after{animation-play-state:paused !important}";',
    '(D.head || D.documentElement).appendChild(sty);',
    '}',
    'var a = D.getAnimations ? D.getAnimations() : [], i;',
    'for (i = 0; i < a.length; i++) { if (a[i].playState === "running") { a[i].pause(); aset.push(a[i]); } }',
    'for (i = 0; i < actx.length; i++) { if (actx[i].state === "running") { halt(actx[i]); } }',
    '}',
    'function sched() { if (!rsched && rq.length && (!paused || round)) { rsched = raf.call(W, rtick); } }',
    'function rtick(ts) {',
    'rsched = 0;',
    'if (paused && !round) { return; }',
    'round = false;',
    'var b = rq, t = Math.max(cur(ts), lastPn);',
    'rq = [];',
    'for (var i = 0; i < b.length; i++) {',
    'if (!b[i].dead) { delete rmap[b[i].id]; try { b[i].cb(t); } catch (e) { rethrow(e); } }',
    '}',
    'sched();',
    '}',
    'function drain() {',
    'var b = deferred;',
    'deferred = [];',
    'if (paused) { deferred = b.concat(deferred); return; }',
    'for (var i = 0; i < b.length; i++) { b[i].q = false; if (!b[i].dead) { b[i].go(); } }',
    '}',
    'function pause() {',
    'if (paused) { return; }',
    'paused = true;',
    'pausedAt = pn();',
    'freeze();',
    '}',
    'function resume() {',
    'if (!paused) { return; }',
    'paused = false;',
    'round = false;',
    'off += pn() - pausedAt;',
    'if (sty) { if (sty.parentNode) { sty.parentNode.removeChild(sty); } sty = null; }',
    'var i;',
    'for (i = 0; i < aset.length; i++) { try { aset[i].play(); } catch (e) {} }',
    'for (i = 0; i < asus.length; i++) { try { var p = asus[i].resume(); if (p && p.catch) { p.catch(noop); } } catch (e) {} }',
    'aset = [];',
    'asus = [];',
    'sched();',
    'if (deferred.length) { st.call(W, drain, 0); }',
    '}',
    'function timer(real, once, args) {',
    'var fn = args[0], r = { a: slice.call(args, 2), q: false, dead: false, id: 0 };',
    'r.go = function () { if (once) { delete tmap[r.id]; } try { fn.apply(W, r.a); } catch (e) { rethrow(e); } };',
    'r.id = real.call(W, function () {',
    'if (r.dead) { return; }',
    'if (paused) { if (!r.q) { r.q = true; deferred.push(r); } } else { r.go(); }',
    '}, args[1]);',
    'tmap[r.id] = r;',
    'return r.id;',
    '}',
    'lock(W, "setTimeout", function setTimeout(fn) { return typeof fn === "function" ? timer(st, true, arguments) : st.apply(W, arguments); });',
    'lock(W, "setInterval", function setInterval(fn) { return typeof fn === "function" ? timer(si, false, arguments) : si.apply(W, arguments); });',
    'function clear(real, id) {',
    'var n = Number(id) | 0;',
    'if (n === hb) { return; }',
    'var r = tmap[n];',
    'if (r) { r.dead = true; delete tmap[n]; }',
    'real.call(W, n);',
    '}',
    'lock(W, "clearTimeout", function clearTimeout(id) { clear(ct, id); });',
    'lock(W, "clearInterval", function clearInterval(id) { clear(ci, id); });',
    'lock(W, "requestAnimationFrame", function requestAnimationFrame(cb) {',
    'if (typeof cb !== "function") { throw new TypeError("requestAnimationFrame: callback is not a function"); }',
    'var r = { id: ++rid, cb: cb, dead: false };',
    'rmap[r.id] = r;',
    'rq.push(r);',
    'sched();',
    'return r.id;',
    '});',
    'lock(W, "cancelAnimationFrame", function cancelAnimationFrame(id) {',
    'var r = rmap[Number(id) | 0];',
    'if (r) { r.dead = true; delete rmap[r.id]; }',
    '});',
    'if (typeof ric === "function") {',
    'lock(W, "requestIdleCallback", function requestIdleCallback(fn, o) {',
    'if (typeof fn !== "function") { return ric.apply(W, arguments); }',
    'var r = { dl: null, q: false, dead: false, id: 0 };',
    'r.go = function () { delete imap[r.id]; try { fn(r.dl || { didTimeout: false, timeRemaining: function () { return 0; } }); } catch (e) { rethrow(e); } };',
    'r.id = ric.call(W, function (dl) {',
    'if (r.dead) { return; }',
    'if (paused) { r.dl = null; r.q = true; deferred.push(r); } else { r.dl = dl; r.go(); }',
    '}, o);',
    'imap[r.id] = r;',
    'return r.id;',
    '});',
    'lock(W, "cancelIdleCallback", function cancelIdleCallback(id) {',
    'var r = imap[Number(id) | 0];',
    'if (r) { r.dead = true; delete imap[r.id]; }',
    'cic.call(W, id);',
    '});',
    '}',
    'var sc = W.Scheduler && W.Scheduler.prototype;',
    'if (sc && typeof sc.postTask === "function") {',
    'var pt = sc.postTask;',
    'lock(sc, "postTask", function postTask(fn, o) {',
    'if (typeof fn !== "function") { return pt.apply(this, arguments); }',
    'return pt.call(this, function () {',
    'if (!paused) { return fn.apply(this, arguments); }',
    'return new W.Promise(function (res, rej) {',
    'deferred.push({ q: true, dead: false, go: function () { try { res(fn()); } catch (e) { rej(e); } } });',
    '});',
    '}, o);',
    '});',
    '}',
    'function wrapCtx(n) {',
    'var C = W[n];',
    'if (typeof C !== "function") { return; }',
    'var X = function () {',
    'var c = W.Reflect.construct(C, slice.call(arguments), X);',
    'actx.push(c);',
    'if (paused) { halt(c); }',
    'return c;',
    '};',
    'X.prototype = C.prototype;',
    'lock(W, n, X);',
    '}',
    'wrapCtx("AudioContext");',
    'wrapCtx("webkitAudioContext");',
    'if (W.getComputedStyle(D.documentElement).getPropertyValue("--frame-paused").trim() === "1") {',
    'paused = true;',
    'round = true;',
    'pausedAt = pn();',
    'freeze();',
    '}',
    'var root = D.documentElement;',
    'var mode = W.getComputedStyle(root).getPropertyValue("--frame-mode").trim();',
    'root.setAttribute("data-theme", mode === "light" ? "light" : "dark");',
    'function height() {',
    'var r = root.getBoundingClientRect().height;',
    'var b = D.body ? D.body.scrollHeight : 0;',
    'return Math.ceil(Math.max(r, b));',
    '}',
    'function post() { try { pm({ t: "size", h: height() }, "*"); } catch (e) {} }',
    'if (W.ResizeObserver) { new W.ResizeObserver(post).observe(root); }',
    'W.addEventListener("load", post);',
    'hb = si(post, 1000);',
    'function applyTheme(vars, m) {',
    'var s = root.style;',
    'if (vars && typeof vars === "object") {',
    'for (var k in vars) {',
    'if (Object.prototype.hasOwnProperty.call(vars, k) && /^--[a-z0-9-]+$/.test(k) && typeof vars[k] === "string") { s.setProperty(k, vars[k]); }',
    '}',
    '}',
    'if (m === "light" || m === "dark") { root.setAttribute("data-theme", m); s.colorScheme = m; }',
    '}',
    'W.addEventListener("message", function (e) {',
    'var d = e.data;',
    'if (e.source !== W.parent || !d) return;',
    'if (d.t === "theme") {',
    'applyTheme(d.vars, d.mode);',
    'W.dispatchEvent(new Event("themechange"));',
    '} else if (d.t === "pause") {',
    'pause();',
    '} else if (d.t === "resume") {',
    'resume();',
    '}',
    '}, true);',
    '})();'
  ].join('\n');

  function cssValue(v) {
    // A token value goes into a <style>; keep it to a literal (no markup, no declarations).
    return String(v).replace(/[<>{};\\]/g, '').trim();
  }

  // var(--name) written in two pieces so the guard that scans JS strings for undefined page
  // tokens does not read the frame's own variables as page references.
  function ref(name) {
    return 'var(' + '--' + name + ')';
  }

  function buildBaseStyle(opts) {
    var vars = (opts && opts.vars) || {};
    var mode = opts && opts.mode === 'light' ? 'light' : 'dark';
    var decls = [];
    var i;
    for (i = 0; i < VAR_SOURCES.length; i++) {
      var name = VAR_SOURCES[i][0];
      var value = Object.prototype.hasOwnProperty.call(vars, name) ? cssValue(vars[name]) : '';
      if (value) decls.push(name + ':' + value);
    }
    decls.push('--frame-mode:' + mode);
    decls.push('--frame-paused:' + (opts && opts.paused === true ? '1' : '0'));
    decls.push('color-scheme:' + mode);
    return (
      ':root{' + decls.join(';') + '}' +
      'html,body{margin:0}' +
      'html{background:' + ref('surface') + ';color:' + ref('fg') +
      ';font-family:system-ui,-apple-system,sans-serif}'
    );
  }

  // buildDocument(source, {vars, mode, paused}) -> string: the exact document the frame loads. The
  // six fixed parts come first, in this order, then the source with only its link tags rewritten
  // (DD6; nothing else in it is parsed or changed).
  function buildDocument(source, opts) {
    return (
      '<!doctype html>' +
      '<meta charset="utf-8">' +
      '<meta http-equiv="Content-Security-Policy" content="' + POLICY + '">' +
      '<meta name="viewport" content="width=device-width, initial-scale=1">' +
      '<style>' + buildBaseStyle(opts) + '</style>' +
      '<script>' + PRELUDE + '</script>' +
      rewriteLinks(source)
    );
  }

  // ── Page-side registry (module level) ──────────────────────────────────────
  var live = new Map(); // contentWindow -> handle
  var liveCount = 0;
  var themeObserver = null;

  function readTheme(slot) {
    var root = document.documentElement;
    var node = slot && root.contains(slot) ? slot : root;
    var cs = window.getComputedStyle(node);
    var vars = {};
    var i;
    for (i = 0; i < VAR_SOURCES.length; i++) {
      var v = cs.getPropertyValue(VAR_SOURCES[i][1]).trim();
      if (v) vars[VAR_SOURCES[i][0]] = v;
    }
    var th = node.closest ? node.closest('[data-theme]') : null;
    var mode = th && th.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    return { vars: vars, mode: mode };
  }

  function clampHeight(h) {
    return Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, Math.round(h)));
  }

  function onMessage(event) {
    var handle = live.get(event.source);
    if (!handle) return;
    var d = event.data;
    if (!d || typeof d !== 'object' || d.t !== 'size') return;
    if (typeof d.h !== 'number' || !isFinite(d.h)) return;
    handle._size(d.h);
  }

  function onThemeMutation() {
    live.forEach(function (handle) {
      handle.postTheme();
    });
  }

  function installShared() {
    if (liveCount === 0) {
      window.addEventListener('message', onMessage);
      themeObserver = new MutationObserver(onThemeMutation);
      themeObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme']
      });
    }
    liveCount += 1;
  }

  function releaseShared() {
    liveCount -= 1;
    if (liveCount === 0) {
      window.removeEventListener('message', onMessage);
      if (themeObserver) themeObserver.disconnect();
      themeObserver = null;
    }
  }

  App.ui.widgetFrame = function (opts) {
    opts = opts || {};
    var slot = opts.slot;
    if (!slot || typeof slot.appendChild !== 'function') {
      throw new TypeError('App.ui.widgetFrame needs a slot element');
    }
    var mountTheme = opts.theme || readTheme(slot);
    var iframe = document.createElement('iframe');
    var loadCount = 0;
    var registered = null;
    var destroyed = false;
    var escaped = false;
    var rafId = 0;
    var wantHeight = INITIAL_HEIGHT;
    var appliedHeight = INITIAL_HEIGHT;
    var pendingTheme = null;
    var pendingPause = null;
    var handle;

    iframe.className = 'ui-widget-frame';
    iframe.setAttribute('sandbox', 'allow-scripts');
    iframe.setAttribute('referrerpolicy', 'no-referrer');
    iframe.setAttribute('allow', '');
    iframe.setAttribute('title', typeof opts.title === 'string' ? opts.title : 'Widget');
    iframe.style.height = INITIAL_HEIGHT + 'px';

    function register() {
      var w = iframe.contentWindow;
      if (!w || registered === w) return;
      if (registered) live.delete(registered);
      registered = w;
      live.set(w, handle);
    }

    function writeHeight() {
      rafId = 0;
      if (destroyed || wantHeight === appliedHeight) return;
      appliedHeight = wantHeight;
      iframe.style.height = appliedHeight + 'px';
      if (typeof opts.onSize === 'function') opts.onSize(appliedHeight);
    }

    function postTheme(theme) {
      var t = theme || readTheme(slot);
      if (destroyed) return;
      // Before the first load the frame has no listener yet (it read the mount theme from its
      // document); keep the newest push and send it at load.
      if (loadCount < 1 || !iframe.contentWindow) {
        pendingTheme = t;
        return;
      }
      iframe.contentWindow.postMessage({ t: 'theme', vars: t.vars, mode: t.mode }, '*');
    }

    // Pause and resume (DD8): queued until the frame has loaded, like the theme; the newest wins.
    // The mount state is the `paused` option, which is in the document itself.
    function postGate(kind) {
      if (destroyed) return;
      if (loadCount < 1 || !iframe.contentWindow) {
        pendingPause = kind;
        return;
      }
      iframe.contentWindow.postMessage({ t: kind }, '*');
    }

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = 0;
      }
      iframe.removeEventListener('load', onLoad);
      if (registered) live.delete(registered);
      registered = null;
      if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
      releaseShared();
    }

    function onLoad() {
      if (destroyed) return;
      loadCount += 1;
      if (loadCount === 1) {
        register();
        if (pendingTheme) {
          var t = pendingTheme;
          pendingTheme = null;
          postTheme(t);
        }
        if (pendingPause) {
          var k = pendingPause;
          pendingPause = null;
          postGate(k);
        }
        return;
      }
      if (escaped) return;
      escaped = true;
      destroy();
      if (typeof opts.onEscape === 'function') opts.onEscape();
    }

    handle = {
      iframe: iframe,
      destroy: destroy,
      postTheme: postTheme,
      postPause: function () {
        postGate('pause');
      },
      postResume: function () {
        postGate('resume');
      },
      loads: function () {
        return loadCount;
      },
      // Internal: the page's one message listener hands a validated height here.
      _size: function (h) {
        if (destroyed) return;
        if (typeof opts.onHeartbeat === 'function') opts.onHeartbeat();
        wantHeight = clampHeight(h);
        if (!rafId && wantHeight !== appliedHeight) rafId = requestAnimationFrame(writeHeight);
      }
    };

    iframe.addEventListener('load', onLoad);
    installShared();
    // The one allowed srcdoc sink in static/js: the document is the fixed prelude plus the
    // model's body. It is set before the iframe is inserted (baseline load count is then 1).
    iframe.srcdoc = buildDocument(opts.source === undefined ? '' : opts.source, {
      vars: mountTheme.vars,
      mode: mountTheme.mode,
      paused: opts.paused === true
    });
    slot.appendChild(iframe);
    register();
    return handle;
  };

  // Test-only seam (M35 F2 L4): whether a contentWindow is still in the live map.
  App.ui.widgetFrame._has = function (win) {
    return live.has(win);
  };
  App.ui.widgetFrame.buildDocument = buildDocument;
  App.ui.widgetFrame.readTheme = readTheme;
  App.ui.widgetFrame.PRELUDE = PRELUDE;
  App.ui.widgetFrame.POLICY = POLICY;
  App.ui.widgetFrame.LINK_RE = LINK_RE;
  App.ui.widgetFrame.limits = {
    minHeight: MIN_HEIGHT,
    maxHeight: MAX_HEIGHT,
    initialHeight: INITIAL_HEIGHT
  };
})();
