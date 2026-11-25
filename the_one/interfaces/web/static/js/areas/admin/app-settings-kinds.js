// The `app_settings` kind of the GleepGlorp registry (M36 F5 L4b, flight DD8). It registers here,
// at the end of the admin script block, after tool-config-kinds.js, so the registry order matches
// the server's. One page per proposal: the target is the page key, which is also the Settings
// route section (`date-and-time` or `knowledge-indexing`).
//
// Only Knowledge indexing is fillable (the server refuses a Date and time fill), so the fill spec
// names that page alone. An approval records under (app_settings, page key); the Date and time
// page and the app's own clock follow it in areas/shared/app-settings-follow.js, the Knowledge
// indexing page in knowledge-settings-follow.js. No App.store collection is involved.
(function () {
  'use strict';
  window.App = window.App || {};

  var KNOWLEDGE = 'knowledge-indexing';

  App.gleepglorpKinds.register('app_settings', {
    labels: {
      itemNoun: 'settings page',
      editorUnavailable: 'The settings page could not open.',
      targetGone: 'That settings page no longer exists.',
      withdrawnGone: function () { return 'the settings page no longer exists.'; }
    },
    openLink: function (view) {
      if (!view.target_id) return null;
      return {
        spec: { destination: 'settings', section: view.target_id },
        text: 'Open settings page',
        testid: 'proposal-open-item'
      };
    },
    store: null,
    recordKey: function (detail) {
      return detail && detail.target_id ? { scope: 'target', id: detail.target_id } : null;
    },
    fill: {
      routeFor: function () { return { destination: 'settings', section: KNOWLEDGE }; },
      openKey: function () { return 'edit:' + KNOWLEDGE; },
      exists: function () { return Promise.resolve(true); },
      isOpen: function (key) { return App.admin.knowledgeSettingsFill.isOpen(key); },
      whenSettled: function (key) { return App.admin.knowledgeSettingsFill.whenSettled(key); },
      select: function () {},
      beforeNavigate: function () {},
      afterNavigate: function () {},
      apply: function (view) { return App.admin.knowledgeSettingsFill.apply(view); }
    }
  });
})();
