// The `provider` kind of the GleepGlorp registry (M36 F4 L5b, flight DD10 and DD11). It registers
// here, where the Studio code it wraps lives, at the end of the Studio script block (after
// mcp-kinds.js, so the registry order is agent, rule, routine, mcp_server, provider). Every call
// into App.studio.* is late-bound.
//
// A model provider is targeted by id: an approval records under (provider, target_id) and
// invalidates the `providers` store; the card links to #library/providers/{id}. A create's id
// exists only once it is applied, so a create's `config_changed` frame without a `target_id`
// records nothing. The kind is fillable: the editor is the Library's provider create form or an
// existing provider's edit form.
(function () {
  'use strict';
  window.App = window.App || {};

  function providerExists(view) {
    return App.store.get('providers', { force: true }).then(function (list) {
      return (list || []).some(function (p) { return p.id === view.target_id; });
    }, function () { return true; }); // unknown: do not call it gone
  }

  var providerFill = {
    routeFor: function (view) {
      return view.action === 'create'
        ? { destination: 'library', section: 'providers', create: true }
        : { destination: 'library', section: 'providers', id: view.target_id };
    },
    openKey: function (view) {
      return view.action === 'create' ? 'create' : 'edit:' + view.target_id;
    },
    exists: providerExists,
    isOpen: function (key) { return App.studio.providerEditorFill.isOpen(key); },
    whenSettled: function (key) { return App.studio.providerEditorFill.whenSettled(key); },
    // The provider editor has no tabs, and a create form does not take focus for a fill.
    select: function () {},
    beforeNavigate: function () {},
    afterNavigate: function () {},
    apply: function (view) { return App.studio.providerEditorFill.apply(view); }
  };

  App.gleepglorpKinds.register('provider', {
    labels: {
      itemNoun: 'model provider',
      editorUnavailable: 'The model provider editor could not open.',
      targetGone: 'That model provider no longer exists.',
      withdrawnGone: function () { return 'the model provider no longer exists.'; }
    },
    openLink: function (view) {
      if (!view.target_id) return null;
      return {
        spec: { destination: 'library', section: 'providers', id: view.target_id },
        text: 'Open model provider',
        testid: 'proposal-open-item'
      };
    },
    store: 'providers',
    recordKey: function (detail) {
      return detail && detail.target_id ? { scope: 'target', id: detail.target_id } : null;
    },
    fill: providerFill
  });
})();
