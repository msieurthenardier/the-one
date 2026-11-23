// App.gleepglorpKinds -- the browser's per-kind registry for GleepGlorp proposals and fills
// (M36 F4 L2, flight DD11). The drawer's fill applier, the fill receipts, the proposal cards and
// App.approvals all read a kind's behaviour from here, so a new kind (an MCP server, a provider)
// registers a spec instead of editing four modules.
//
// Eager and DOM-free. The namespace is App.gleepglorpKinds, not App.gleepglorp.kinds: gleepglorp.js
// assigns App.gleepglorp wholesale and would clobber a sub-key.
//
//   App.gleepglorpKinds.register(name, spec)   throws on a duplicate name (a double script load)
//   App.gleepglorpKinds.get(name)              the spec, or null for an unknown name
//   App.gleepglorpKinds.names()                the registered names, in registration order
//
// spec:
//   labels: {itemNoun, editorUnavailable, targetGone, withdrawnGone(view)}
//   openLink(view) -> {spec, text, testid} | null   the card's link to the item (spec is a router spec)
//   store                                           the App.store collection an approval invalidates
//   recordKey(detail) -> {scope: 'agent' | 'target', id, fields?} | null
//       where App.approvals records the change; fields (when set) replaces detail.fields as the keys;
//       null: not recordable (record returns false)
//   fill (only a fillable kind): {routeFor(view), openKey(view), exists(view) -> Promise<bool>,
//       isOpen(key), whenSettled(key) -> Promise<bool>, select(), beforeNavigate(view),
//       afterNavigate(), apply(view) -> Promise<{unavailable?, kept}>}
//       exists must be re-callable and free of side effects.
//
// Specs stay mutable (a browser test nulls a kind's `fill`). A kind registers itself where the code
// it wraps lives (the agent kinds: areas/studio/agent-kinds.js); a spec's calls into other modules
// are late-bound.
(function () {
  'use strict';
  window.App = window.App || {};

  var specs = Object.create(null);
  var order = [];

  function register(name, spec) {
    if (typeof name !== 'string' || !name) throw new Error('gleepglorpKinds.register: a kind needs a name');
    if (specs[name]) throw new Error('gleepglorpKinds.register: "' + name + '" is already registered');
    specs[name] = spec;
    order.push(name);
    return spec;
  }

  function get(name) {
    return (typeof name === 'string' && specs[name]) || null;
  }

  function names() {
    return order.slice();
  }

  window.App.gleepglorpKinds = { register: register, get: get, names: names };
})();
