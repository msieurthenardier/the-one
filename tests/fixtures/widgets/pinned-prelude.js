(function () {
var W = window, D = document;
var ct = W.clearTimeout, ci = W.clearInterval, si = W.setInterval, st = W.setTimeout;
var raf = W.requestAnimationFrame, ric = W.requestIdleCallback, cic = W.cancelIdleCallback;
var pn = W.performance.now.bind(W.performance);
var pm = W.parent.postMessage.bind(W.parent);
var slice = Array.prototype.slice;
var hb = -1;
var lastG = -100000;
function lock(o, n, v) {
try { Object.defineProperty(o, n, { value: v, writable: false, configurable: false }); } catch (e) {}
}
function rethrow(e) { st.call(W, function () { throw e; }, 0); }
function stamp(e) { if (e.isTrusted) { lastG = pn(); } }
var gs = ["pointerdown", "mousedown", "keydown", "click", "touchstart"];
for (var gi = 0; gi < gs.length; gi++) { W.addEventListener(gs[gi], stamp, true); }
var noop = function () {};
lock(W, "RTCPeerConnection", undefined);
lock(W, "webkitRTCPeerConnection", undefined);
lock(W, "RTCDataChannel", undefined);
var hp = W.History && W.History.prototype;
if (hp) {
lock(hp, "back", noop);
lock(hp, "forward", noop);
lock(hp, "go", noop);
lock(hp, "pushState", noop);
lock(hp, "replaceState", noop);
}
var dp = W.Document && W.Document.prototype;
if (dp) { lock(dp, "execCommand", function execCommand() { return false; }); }
function okFocus() { var u = W.navigator.userActivation; return !!(u && u.isActive) && pn() - lastG <= 1000; }
function gateFocus(p) {
if (!p || typeof p.focus !== "function") { return; }
var f = p.focus;
lock(p, "focus", function focus() { if (okFocus()) { return f.apply(this, arguments); } });
}
gateFocus(W.HTMLElement && W.HTMLElement.prototype);
gateFocus(W.SVGElement && W.SVGElement.prototype);
gateFocus(W.MathMLElement && W.MathMLElement.prototype);
gateFocus(W.Window && W.Window.prototype);
var wf = W.focus;
if (typeof wf === "function") { lock(W, "focus", function focus() { if (okFocus()) { return wf.apply(W, arguments); } }); }
function noAuto(c) {
var p = W[c] && W[c].prototype;
if (p && Object.prototype.hasOwnProperty.call(p, "autofocus")) {
try { Object.defineProperty(p, "autofocus", { get: function () { return false; }, set: noop, configurable: false }); } catch (e) {}
}
}
["HTMLElement", "SVGElement", "MathMLElement", "HTMLInputElement", "HTMLButtonElement", "HTMLSelectElement", "HTMLTextAreaElement"].forEach(noAuto);
var LRE = /<(\/?)link(?=[\s/>])/gi;
var XRE = /<(\/?)((?:[\w.-]+:)?)link(?=[\s/>])/gi;
function rw(s) { return String(s).replace(LRE, "<$1x-link"); }
function rx(s) { return String(s).replace(XRE, "<$1$2x-link"); }
function wrapSet(o, n) {
if (!o) { return; }
var d = Object.getOwnPropertyDescriptor(o, n);
if (!d || !d.set) { return; }
var s = d.set;
try { Object.defineProperty(o, n, { get: d.get, set: function (v) { return s.call(this, v === null ? v : rw(v)); }, enumerable: d.enumerable, configurable: false }); } catch (e) {}
}
function wrapM(o, n, i, r) {
if (!o || typeof o[n] !== "function") { return; }
var g = o[n];
var h = r || rw;
lock(o, n, function () { var a = slice.call(arguments); if (a.length > i && a[i] !== null) { a[i] = h(a[i]); } return g.apply(this, a); });
}
var ep = W.Element && W.Element.prototype, sp = W.ShadowRoot && W.ShadowRoot.prototype;
wrapSet(ep, "innerHTML");
wrapSet(ep, "outerHTML");
wrapSet(sp, "innerHTML");
wrapM(ep, "insertAdjacentHTML", 1);
wrapM(ep, "setHTMLUnsafe", 0);
wrapM(ep, "setHTML", 0);
wrapM(sp, "setHTMLUnsafe", 0);
wrapM(sp, "setHTML", 0);
wrapM(W.Document, "parseHTMLUnsafe", 0);
wrapM(W.Document, "parseHTML", 0);
wrapM(W.Range && W.Range.prototype, "createContextualFragment", 0);
wrapM(W.DOMParser && W.DOMParser.prototype, "parseFromString", 0, rx);
var ce = dp.createElement, cn = dp.createElementNS;
lock(dp, "createElement", function createElement() {
var a = slice.call(arguments);
if (a.length) { a[0] = String(a[0]); if (/^link$/i.test(a[0])) { a[0] = "x-link"; } }
return ce.apply(this, a);
});
lock(dp, "createElementNS", function createElementNS() {
var a = slice.call(arguments);
if (a.length > 1) { a[1] = String(a[1]); if (/(^|:)link$/i.test(a[1])) { a[1] = "x-link"; } }
return cn.apply(this, a);
});
var HOLD = /<\/?(?:l(?:i(?:n(?:k)?)?)?)?$/i;
var pends = new W.WeakMap(), ready = false;
var dw = dp.write, dc = dp.close;
D.addEventListener("DOMContentLoaded", function () { ready = true; }, true);
function writeOut(self, t) {
t = (pends.get(self) || "") + t;
var m = HOLD.exec(t);
pends.set(self, m ? m[0] : "");
if (m) { t = t.slice(0, m.index); }
if (t) { dw.call(self, rw(t)); }
}
lock(dp, "write", function write() { if (this === D && ready) { return; } writeOut(this, slice.call(arguments).map(String).join("")); });
lock(dp, "writeln", function writeln() { if (this === D && ready) { return; } writeOut(this, slice.call(arguments).map(String).join("") + "\n"); });
lock(dp, "open", function open() { return this; });
lock(dp, "close", function close() {
var p = pends.get(this);
if (p && !(this === D && ready)) { pends.set(this, ""); dw.call(this, rw(p)); }
return dc.call(this);
});
function sweep(n) {
if (n.nodeType !== 1) { return; }
if (n.hasAttribute("autofocus")) { n.removeAttribute("autofocus"); }
if (W.HTMLLinkElement && n instanceof W.HTMLLinkElement) { n.remove(); return; }
var l = n.querySelectorAll("link, [autofocus]");
for (var li = 0; li < l.length; li++) { if (l[li].hasAttribute("autofocus")) { l[li].removeAttribute("autofocus"); } else { l[li].remove(); } }
}
new W.MutationObserver(function (rs) {
for (var ri = 0; ri < rs.length; ri++) {
var r = rs[ri];
if (r.type === "attributes") { r.target.removeAttribute("autofocus"); continue; }
for (var ai = 0; ai < r.addedNodes.length; ai++) { sweep(r.addedNodes[ai]); }
}
}).observe(D, { childList: true, subtree: true, attributes: true, attributeFilter: ["autofocus"] });
var paused = false, round = false, pausedAt = 0, off = 0, lastPn = 0;
var tmap = {}, imap = {}, rmap = {}, deferred = [], rq = [], rid = 0, rsched = 0;
var sty = null, aset = [], actx = [], asus = [];
function cur(t) { return (paused && t > pausedAt ? pausedAt : t) - off; }
lock(W.Performance.prototype, "now", function now() { lastPn = cur(pn()); return lastPn; });
function halt(c) {
asus.push(c);
try { var p = c.suspend(); if (p && p.catch) { p.catch(noop); } } catch (e) {}
}
function freeze() {
if (!sty) {
sty = ce.call(D, "style");
sty.textContent = "*,*::before,*::after{animation-play-state:paused !important}";
(D.head || D.documentElement).appendChild(sty);
}
var a = D.getAnimations ? D.getAnimations() : [], i;
for (i = 0; i < a.length; i++) { if (a[i].playState === "running") { a[i].pause(); aset.push(a[i]); } }
for (i = 0; i < actx.length; i++) { if (actx[i].state === "running") { halt(actx[i]); } }
}
function sched() { if (!rsched && rq.length && (!paused || round)) { rsched = raf.call(W, rtick); } }
function rtick(ts) {
rsched = 0;
if (paused && !round) { return; }
round = false;
var b = rq, t = Math.max(cur(ts), lastPn);
rq = [];
for (var i = 0; i < b.length; i++) {
if (!b[i].dead) { delete rmap[b[i].id]; try { b[i].cb(t); } catch (e) { rethrow(e); } }
}
sched();
}
function drain() {
var b = deferred;
deferred = [];
if (paused) { deferred = b.concat(deferred); return; }
for (var i = 0; i < b.length; i++) { b[i].q = false; if (!b[i].dead) { b[i].go(); } }
}
function pause() {
if (paused) { return; }
paused = true;
pausedAt = pn();
freeze();
}
function resume() {
if (!paused) { return; }
paused = false;
round = false;
off += pn() - pausedAt;
if (sty) { if (sty.parentNode) { sty.parentNode.removeChild(sty); } sty = null; }
var i;
for (i = 0; i < aset.length; i++) { try { aset[i].play(); } catch (e) {} }
for (i = 0; i < asus.length; i++) { try { var p = asus[i].resume(); if (p && p.catch) { p.catch(noop); } } catch (e) {} }
aset = [];
asus = [];
sched();
if (deferred.length) { st.call(W, drain, 0); }
}
function timer(real, once, args) {
var fn = args[0], r = { a: slice.call(args, 2), q: false, dead: false, id: 0 };
r.go = function () { if (once) { delete tmap[r.id]; } try { fn.apply(W, r.a); } catch (e) { rethrow(e); } };
r.id = real.call(W, function () {
if (r.dead) { return; }
if (paused) { if (!r.q) { r.q = true; deferred.push(r); } } else { r.go(); }
}, args[1]);
tmap[r.id] = r;
return r.id;
}
lock(W, "setTimeout", function setTimeout(fn) { return typeof fn === "function" ? timer(st, true, arguments) : st.apply(W, arguments); });
lock(W, "setInterval", function setInterval(fn) { return typeof fn === "function" ? timer(si, false, arguments) : si.apply(W, arguments); });
function clear(real, id) {
var n = Number(id) | 0;
if (n === hb) { return; }
var r = tmap[n];
if (r) { r.dead = true; delete tmap[n]; }
real.call(W, n);
}
lock(W, "clearTimeout", function clearTimeout(id) { clear(ct, id); });
lock(W, "clearInterval", function clearInterval(id) { clear(ci, id); });
lock(W, "requestAnimationFrame", function requestAnimationFrame(cb) {
if (typeof cb !== "function") { throw new TypeError("requestAnimationFrame: callback is not a function"); }
var r = { id: ++rid, cb: cb, dead: false };
rmap[r.id] = r;
rq.push(r);
sched();
return r.id;
});
lock(W, "cancelAnimationFrame", function cancelAnimationFrame(id) {
var r = rmap[Number(id) | 0];
if (r) { r.dead = true; delete rmap[r.id]; }
});
if (typeof ric === "function") {
lock(W, "requestIdleCallback", function requestIdleCallback(fn, o) {
if (typeof fn !== "function") { return ric.apply(W, arguments); }
var r = { dl: null, q: false, dead: false, id: 0 };
r.go = function () { delete imap[r.id]; try { fn(r.dl || { didTimeout: false, timeRemaining: function () { return 0; } }); } catch (e) { rethrow(e); } };
r.id = ric.call(W, function (dl) {
if (r.dead) { return; }
if (paused) { r.dl = null; r.q = true; deferred.push(r); } else { r.dl = dl; r.go(); }
}, o);
imap[r.id] = r;
return r.id;
});
lock(W, "cancelIdleCallback", function cancelIdleCallback(id) {
var r = imap[Number(id) | 0];
if (r) { r.dead = true; delete imap[r.id]; }
cic.call(W, id);
});
}
var sc = W.Scheduler && W.Scheduler.prototype;
if (sc && typeof sc.postTask === "function") {
var pt = sc.postTask;
lock(sc, "postTask", function postTask(fn, o) {
if (typeof fn !== "function") { return pt.apply(this, arguments); }
return pt.call(this, function () {
if (!paused) { return fn.apply(this, arguments); }
return new W.Promise(function (res, rej) {
deferred.push({ q: true, dead: false, go: function () { try { res(fn()); } catch (e) { rej(e); } } });
});
}, o);
});
}
function wrapCtx(n) {
var C = W[n];
if (typeof C !== "function") { return; }
var X = function () {
var c = W.Reflect.construct(C, slice.call(arguments), X);
actx.push(c);
if (paused) { halt(c); }
return c;
};
X.prototype = C.prototype;
lock(W, n, X);
}
wrapCtx("AudioContext");
wrapCtx("webkitAudioContext");
if (W.getComputedStyle(D.documentElement).getPropertyValue("--frame-paused").trim() === "1") {
paused = true;
round = true;
pausedAt = pn();
freeze();
}
var root = D.documentElement;
var mode = W.getComputedStyle(root).getPropertyValue("--frame-mode").trim();
root.setAttribute("data-theme", mode === "light" ? "light" : "dark");
function height() {
var r = root.getBoundingClientRect().height;
var b = D.body ? D.body.scrollHeight : 0;
return Math.ceil(Math.max(r, b));
}
function post() { try { pm({ t: "size", h: height() }, "*"); } catch (e) {} }
if (W.ResizeObserver) { new W.ResizeObserver(post).observe(root); }
W.addEventListener("load", post);
hb = si(post, 1000);
function applyTheme(vars, m) {
var s = root.style;
if (vars && typeof vars === "object") {
for (var k in vars) {
if (Object.prototype.hasOwnProperty.call(vars, k) && /^--[a-z0-9-]+$/.test(k) && typeof vars[k] === "string") { s.setProperty(k, vars[k]); }
}
}
if (m === "light" || m === "dark") { root.setAttribute("data-theme", m); s.colorScheme = m; }
}
W.addEventListener("message", function (e) {
var d = e.data;
if (e.source !== W.parent || !d) return;
if (d.t === "theme") {
applyTheme(d.vars, d.mode);
W.dispatchEvent(new Event("themechange"));
} else if (d.t === "pause") {
pause();
} else if (d.t === "resume") {
resume();
}
}, true);
})();
