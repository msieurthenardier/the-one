// App.studio.secretEditorFollow -- the secret editor follows a change the operator approved in a
// GleepGlorp chat (M36 F5 L3b, flight DD9 and DD14). secret-glue.js calls attach(ctx) once:
//
//   ctx: {getController() -> the live editor controller or null, followed(row) (the glue's own
//         follow path: the list reload, the router's name and the Library selection; never the
//         Save path, so the form's dirty mirror and its mode are left alone)}
//
// The signal is App.approvals' CONFIG_CHANGED event, listened to once per page through
// App.gleepglorpFollow.listen (areas/shared/gleepglorp-follow-core.js, which also holds the note
// and the fetch-and-retry skeleton). For a `secret` change whose `target_id` is the open EDIT
// form's secret (a create form or another secret is ignored) the stored row is fetched and the
// controller rebases the METADATA (name, description, allowed tools: a clean field takes the
// stored value; a dirty one keeps the operator's while its baseline moves). The values table is
// never rebased or re-read, so a value row being edited is untouched. A note under each changed
// field says where it came from (flight DD14: per-field). A Save in flight defers the follow
// until it ends. The notes are cleared by Save and Cancel.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var ctx = null;

  function follow_(ctl, detail) {
    App.gleepglorpFollow.refetchThen(ctl, '/api/secrets/' + encodeURIComponent(ctl.id),
      function () { return ctx.getController() === ctl; },
      function (row) {
        ctl.rebase(row);
        ctl.addFollowNotes(detail, detail.fields);
        ctx.followed(row);
      });
  }

  function onEvent(detail) {
    if (!ctx || !App.gleepglorpFollow.matches('secret', detail)) return;
    var ctl = ctx.getController();
    if (!ctl || ctl.isCreate || ctl.id !== detail.target_id || !ctl.alive()) return;
    follow_(ctl, detail);
  }

  function attach(c) {
    ctx = c;
    App.gleepglorpFollow.listen('secret', onEvent);
  }

  window.App.studio.secretEditorFollow = { attach: attach, onEvent: onEvent };
})();
