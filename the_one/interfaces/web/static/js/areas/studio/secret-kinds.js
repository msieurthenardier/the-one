// The `secret` kind of the GleepGlorp registry (M36 F5 L3b, flight DD6). It registers here, where
// the Studio code it wraps lives, at the end of the Studio script block (after
// knowledge-kinds.js, so the registry order matches the server's). The spec is built by
// App.gleepglorpKinds.registerLibraryKind; the call into App.studio.* is late-bound.
//
// A secret is targeted by id: an approval records under (secret, target_id) and invalidates the
// `secrets` store; the card links to #library/secrets/{id}. The kind is fillable (name,
// description, allowed tools; never a value): the editor is the Library's secret create form or
// an existing secret's edit form.
(function () {
  'use strict';
  window.App = window.App || {};

  App.gleepglorpKinds.registerLibraryKind({
    name: 'secret',
    section: 'secrets',
    store: 'secrets',
    noun: 'secret',
    fill: function () { return App.studio.secretEditorFill; }
  });
})();
