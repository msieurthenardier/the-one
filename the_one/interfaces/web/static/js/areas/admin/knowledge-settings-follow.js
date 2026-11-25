// App.admin.knowledgeSettingsFollow -- the Knowledge indexing page follows a change the operator
// approved in a GleepGlorp chat (M36 F5 L4b, flight DD8, DD9 and DD14). admin.js calls attach(ctx)
// once:
//
//   ctx: {getController() -> the page's controller or null (null while the first load is in
//         flight)}
//
// The signal is App.approvals' CONFIG_CHANGED event, but `listen` registers once per kind per
// page and the Date and time page shares the `app_settings` kind, so this module registers its
// handler with the shared dispatcher (areas/shared/app-settings-follow.js) for the page key
// `knowledge-indexing`. The stored settings are fetched (through refetchThen, which waits for a
// Save in flight) and the controller rebases: a clean field takes the stored value, a dirty one
// keeps the operator's while its baseline moves, and the read-only facts refresh. A note under
// each changed field says where it came from. The notes are cleared by Save and Cancel.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  var ctx = null;

  function onEvent(detail) {
    if (!ctx) return;
    var ctl = ctx.getController();
    if (!ctl || !ctl.alive() || !ctl.ready()) return;
    App.gleepglorpFollow.refetchThen(ctl, '/api/knowledge-settings',
      function () { return ctx.getController() === ctl; },
      function (data) {
        ctl.rebase(data);
        ctl.addFollowNotes(detail, detail.fields);
      });
  }

  var unregister = null;

  function attach(c) {
    ctx = c;
    if (unregister) unregister(); // a second area init replaces the first's registration
    unregister = App.appSettingsFollow.register('knowledge-indexing', onEvent);
  }

  window.App.admin.knowledgeSettingsFollow = { attach: attach, onEvent: onEvent };
})();
