// App.studio.knowledgeEditorFollow -- the knowledge-base edit form follows a change the operator
// approved in a GleepGlorp chat (M36 F5 L3b, flight DD9 and DD14). knowledge-glue.js calls
// attach(ctx) once:
//
//   ctx: {getController() -> the live editor controller or null, reload(storeName) (the Library
//         list reload)}
//
// The signal is App.approvals' CONFIG_CHANGED event, listened to once per page through
// App.gleepglorpFollow.listen (areas/shared/gleepglorp-follow-core.js, which also holds the note
// and the fetch-and-retry skeleton). For a `knowledge_base` change whose `target_id` is the open
// EDIT form's base (a create form, another base, or an editor that has not mounted yet is
// ignored; a late mount reads fresh data anyway) the stored row is fetched and the controller
// rebases (a clean field takes the stored value; a dirty one keeps the operator's value while its
// baseline moves), the title and subtitle follow, the Library list reloads, and a note under each
// changed field (name, description) says where it came from (flight DD14: per-field, not under
// the header). A Save in flight defers the follow until it ends. The notes are cleared by Save
// and Cancel. The URL is id-based, so a rename moves nothing in it.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var ctx = null;

  function follow_(ctl, detail) {
    App.gleepglorpFollow.refetchThen(ctl, '/api/knowledge-bases/' + encodeURIComponent(ctl.id),
      function () { return ctx.getController() === ctl; },
      function (row) {
        ctl.rebase(row);
        ctl.addFollowNotes(detail, detail.fields);
        ctx.reload('knowledge-bases');
      });
  }

  function onEvent(detail) {
    if (!ctx || !App.gleepglorpFollow.matches('knowledge_base', detail)) return;
    var ctl = ctx.getController();
    if (!ctl || ctl.isCreate || ctl.id !== detail.target_id || !ctl.alive()) return;
    follow_(ctl, detail);
  }

  function attach(c) {
    ctx = c;
    App.gleepglorpFollow.listen('knowledge_base', onEvent);
  }

  window.App.studio.knowledgeEditorFollow = { attach: attach, onEvent: onEvent };
})();
