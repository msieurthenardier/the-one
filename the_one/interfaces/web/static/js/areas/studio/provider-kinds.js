// The `provider` kind of the GleepGlorp registry (M36 F4 L5b, flight DD10 and DD11). It registers
// here, where the Studio code it wraps lives, at the end of the Studio script block (after
// mcp-kinds.js, so the registry order is agent, rule, routine, mcp_server, provider). The spec is
// built by App.gleepglorpKinds.registerLibraryKind (M36 F5 L2); the call into App.studio.* is
// late-bound.
//
// A model provider is targeted by id: an approval records under (provider, target_id) and
// invalidates the `providers` store; the card links to #library/providers/{id}. A create's id
// exists only once it is applied, so a create's `config_changed` frame without a `target_id`
// records nothing. The kind is fillable: the editor is the Library's provider create form or an
// existing provider's edit form.
(function () {
  'use strict';
  window.App = window.App || {};

  App.gleepglorpKinds.registerLibraryKind({
    name: 'provider',
    section: 'providers',
    store: 'providers',
    noun: 'model provider',
    fill: function () { return App.studio.providerEditorFill; }
  });
})();
