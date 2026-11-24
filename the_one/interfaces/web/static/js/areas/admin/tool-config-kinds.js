// The `tool_config` kind of the GleepGlorp registry (M36 F5 L4b, flight DD7). It registers here,
// at the end of the admin script block, after secret-kinds.js, so the registry order matches the
// server's. Settings is not the Library, so the spec is built by hand (registerLibraryKind is the
// Library's). Every call into App.admin.* is late-bound.
//
// A built-in tool is targeted by its name: an approval records under (tool_config, name), the
// card links to #settings/tools/{name}, and the kind is fillable (the Enabled switch and the
// allowlisted config fields) in that tool's editor. Built-in tools are never removed, so a fill
// never finds its target gone.
(function () {
  'use strict';
  window.App = window.App || {};

  function route(view) {
    return { destination: 'settings', section: 'tools', id: view.target_id };
  }

  App.gleepglorpKinds.register('tool_config', {
    labels: {
      itemNoun: 'built-in tool',
      editorUnavailable: 'The tool editor could not open.',
      targetGone: 'That built-in tool no longer exists.',
      withdrawnGone: function () { return 'the built-in tool no longer exists.'; }
    },
    openLink: function (view) {
      if (!view.target_id) return null;
      return { spec: route(view), text: 'Open built-in tool', testid: 'proposal-open-item' };
    },
    // The grid and the editor do not read the `agents` store, but turning a tool on or off changes
    // what agents can use, and the editor's own Save invalidates `agents` for the same reason.
    store: 'agents',
    recordKey: function (detail) {
      return detail && detail.target_id ? { scope: 'target', id: detail.target_id } : null;
    },
    fill: {
      routeFor: route,
      openKey: function (view) { return 'edit:' + view.target_id; },
      exists: function () { return Promise.resolve(true); },
      isOpen: function (key) { return App.admin.toolConfigFill.isOpen(key); },
      whenSettled: function (key) { return App.admin.toolConfigFill.whenSettled(key); },
      select: function () {},
      // The editor's title takes focus when a tool opens from a link; a fill keeps it in the drawer.
      beforeNavigate: function () { App.admin.toolsPage.keepFocus = true; },
      afterNavigate: function () { App.admin.toolsPage.keepFocus = false; },
      apply: function (view) { return App.admin.toolConfigFill.apply(view); }
    }
  });
})();
