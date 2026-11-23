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

  // registerLibraryKind({name, section, store, noun, fill}): the spec of a Library kind whose
  // item is edited in a Library editor that GleepGlorp can fill (the MCP server and the model
  // provider; M36 F5 L2). `section` is the Library section in the route (#library/{section}/{id}),
  // `store` the App.store collection an approval invalidates, `noun` the lower-case item noun
  // ("MCP server", "model provider"), `fill` a function returning the editor's fill module
  // (late-bound, as the module loads after this file). An approval records under (name,
  // target_id); a create's frame without a target_id records nothing.
  function registerLibraryKind(o) {
    var fillOf = o.fill;
    var section = o.section;
    var noun = o.noun;
    return register(o.name, {
      labels: {
        itemNoun: noun,
        editorUnavailable: 'The ' + noun + ' editor could not open.',
        targetGone: 'That ' + noun + ' no longer exists.',
        withdrawnGone: function () { return 'the ' + noun + ' no longer exists.'; }
      },
      openLink: function (view) {
        if (!view.target_id) return null;
        return {
          spec: { destination: 'library', section: section, id: view.target_id },
          text: 'Open ' + noun,
          testid: 'proposal-open-item'
        };
      },
      store: o.store,
      recordKey: function (detail) {
        return detail && detail.target_id ? { scope: 'target', id: detail.target_id } : null;
      },
      fill: {
        routeFor: function (view) {
          return view.action === 'create'
            ? { destination: 'library', section: section, create: true }
            : { destination: 'library', section: section, id: view.target_id };
        },
        openKey: function (view) {
          return view.action === 'create' ? 'create' : 'edit:' + view.target_id;
        },
        // A forced fetch; unknown (a failed fetch) is not "gone".
        exists: function (view) {
          return App.store.get(o.store, { force: true }).then(function (list) {
            return (list || []).some(function (x) { return x.id === view.target_id; });
          }, function () { return true; });
        },
        isOpen: function (key) { return fillOf().isOpen(key); },
        whenSettled: function (key) { return fillOf().whenSettled(key); },
        // These editors have no tabs, and a create form does not take focus for a fill.
        select: function () {},
        beforeNavigate: function () {},
        afterNavigate: function () {},
        apply: function (view) { return fillOf().apply(view); }
      }
    });
  }

  window.App.gleepglorpKinds = {
    register: register, registerLibraryKind: registerLibraryKind, get: get, names: names
  };
})();
