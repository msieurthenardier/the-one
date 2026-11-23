// The `knowledge_base` kind of the GleepGlorp registry (M36 F5 L3b, flight DD5). It registers
// here, where the Studio code it wraps lives, at the end of the Studio script block (after
// provider-kinds.js, so the registry order is agent, rule, routine, mcp_server, provider,
// knowledge_base, secret: the server REGISTRY's). The spec is built by
// App.gleepglorpKinds.registerLibraryKind; the calls into App.studio.* are late-bound.
//
// A knowledge base is targeted by id: an approval records under (knowledge_base, target_id) and
// invalidates the `knowledge-bases` store; the card links to #library/knowledge/{id}. The kind is
// fillable: the editor is the Library's create form or an existing base's edit form. A fill
// navigation to the create form leaves focus in the drawer composer (the create form's own
// name-field focus is suppressed for that one navigation).
(function () {
  'use strict';
  window.App = window.App || {};

  App.gleepglorpKinds.registerLibraryKind({
    name: 'knowledge_base',
    section: 'knowledge',
    store: 'knowledge-bases',
    noun: 'knowledge base',
    fill: function () { return App.studio.knowledgeEditorFill; },
    beforeNavigate: function (view) {
      if (view.action === 'create') App.studio.knowledgeEditorFill.suppressNextCreateFocus();
    },
    afterNavigate: function () { App.studio.knowledgeEditorFill.clearCreateFocusSuppression(); }
  });
})();
