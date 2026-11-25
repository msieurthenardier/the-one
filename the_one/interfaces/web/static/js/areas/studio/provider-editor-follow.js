// App.studio.providerEditorFollow -- the provider editor follows a change the operator approved
// in a GleepGlorp chat (M36 F4 L5b, flight DD10 and DD11). providers-section.js calls attach(ctx)
// once:
//
//   ctx: {getController() -> the live editor controller or null, getEditing(), setEditing(row),
//         remount(row, detail) (render the editor again from a stored row; the new mount draws
//         the follow note), reload(storeName) (the Library list reload), renamed(row)}
//
// The signal is App.approvals' CONFIG_CHANGED event, listened to once per page through
// App.gleepglorpFollow.listen (areas/shared/gleepglorp-follow-core.js, which also holds the note
// and the fetch-and-retry skeleton). For a `provider` change whose `target_id` is the open EDIT
// editor's provider (a create form, or another provider, is ignored) the stored row is fetched
// and:
//   - same type: the controller rebases (a clean field takes the stored value; a dirty one keeps
//     the operator's value while its baseline moves), the list reloads and a rename moves the
//     title and the URL; the follow note sits under the header, and a Save block from an earlier
//     type change is lifted;
//   - a type change by the approval: a clean editor re-mounts from the stored row (a type switch
//     rebuilds the rows, the key label and the sign-in section); a dirty editor is left alone and
//     its note says "This provider's type changed; Cancel to see it" (Cancel then re-mounts).
//     Dirty fields are never merged across types. Save is refused with that same sentence in the
//     editor's error line until Cancel (squawk 0401: a Save would send the old type back).
// A Save in flight defers the follow until it ends, and the row is fetched again then. The note
// is cleared by Save and Cancel.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var TYPE_CHANGED = "This provider's type changed; Cancel to see it";
  var ctx = null;

  // The note; `text` (the type-changed sentence) replaces the approval line.
  function buildNote(detail, text) {
    return App.gleepglorpFollow.buildNote(detail,
      { testid: 'provider-approved-change-note', text: text });
  }

  function follow_(ctl, detail) {
    App.gleepglorpFollow.refetchThen(ctl, '/api/providers/' + encodeURIComponent(ctl.id),
      function () { return ctx.getController() === ctl; },
      function (row) {
        var before = ctx.getEditing();
        if (row.type !== ctl.baseline().type) {
          ctx.setEditing(row);
          ctx.reload('providers');
          if (!ctl.isDirty()) {
            ctx.remount(row, detail);
          } else {
            ctl.placeFollowNote(buildNote(detail, TYPE_CHANGED));
            ctl.blockSave(TYPE_CHANGED);
            ctl.afterCancel(function () { ctx.remount(row, detail); });
          }
          return;
        }
        var renamed = !before || before.name !== row.name;
        ctx.setEditing(row);
        ctl.rebase(row);
        ctl.blockSave(null);
        ctl.afterCancel(null); // a type change that was reverted: Cancel has nothing to show
        ctl.placeFollowNote(buildNote(detail));
        ctx.reload('providers');
        if (renamed) ctx.renamed(row);
      });
  }

  function onEvent(detail) {
    if (!ctx || !App.gleepglorpFollow.matches('provider', detail)) return;
    var ctl = ctx.getController();
    if (!ctl || ctl.isCreate || ctl.id !== detail.target_id || !ctl.alive()) return;
    follow_(ctl, detail);
  }

  function attach(c) {
    ctx = c;
    App.gleepglorpFollow.listen('provider', onEvent);
  }

  window.App.studio.providerEditorFollow = { attach: attach, onEvent: onEvent, buildNote: buildNote };
})();
