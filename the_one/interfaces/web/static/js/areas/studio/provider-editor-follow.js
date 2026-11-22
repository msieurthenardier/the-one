// App.studio.providerEditorFollow -- the provider editor follows a change the operator approved
// in a GleepGlorp chat (M36 F4 L5b, flight DD10 and DD11). providers-section.js calls attach(ctx)
// once:
//
//   ctx: {getController() -> the live editor controller or null, getEditing(), setEditing(row),
//         remount(row, detail) (render the editor again from a stored row; the new mount draws
//         the follow note), reload(storeName) (the Library list reload), renamed(row)}
//
// The signal is App.approvals' CONFIG_CHANGED event (the document is the transport, and has no
// `off`), so the listener is registered once per page. For a `provider` change whose `target_id`
// is the open EDIT editor's provider (a create form, or another provider, is ignored) the stored
// row is fetched and:
//   - same type: the controller rebases (a clean field takes the stored value; a dirty one keeps
//     the operator's value while its baseline moves), the list reloads and a rename moves the
//     title and the URL; the follow note sits under the header;
//   - a type change by the approval: a clean editor re-mounts from the stored row (a type switch
//     rebuilds the rows, the key label and the sign-in section); a dirty editor is left alone and
//     its note says "This provider's type changed; Cancel to see it" (Cancel then re-mounts).
//     Dirty fields are never merged across types.
// A Save in flight defers the follow until it ends, and the row is fetched again then. The note
// is cleared by Save and Cancel.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var registered = false;
  var ctx = null;

  function buildNote(detail, text) {
    var p = document.createElement('p');
    p.className = 'agent-approved-change-note';
    p.setAttribute('data-testid', 'provider-approved-change-note');
    if (text) {
      p.appendChild(document.createTextNode(text));
      return p;
    }
    var when = '';
    var t = detail && detail.at ? new Date(detail.at) : null;
    if (t && !isNaN(t.getTime())) when = ' · ' + App.time.formatClock(t);
    p.appendChild(document.createTextNode(
      'Changed by a change you approved in a GleepGlorp chat' + when));
    if (detail && detail.session_id) {
      p.appendChild(document.createTextNode(' · '));
      var a = document.createElement('a');
      a.setAttribute('href', App.router.href({ destination: 'chats', id: detail.session_id }));
      a.textContent = 'Open chat';
      p.appendChild(a);
    }
    return p;
  }

  function follow_(ctl, detail) {
    ctl.onIdle(function () {
      if (ctx.getController() !== ctl || !ctl.alive()) return;
      App.api.fetchJson('/api/providers/' + encodeURIComponent(ctl.id)).then(function (row) {
        if (ctx.getController() !== ctl || !ctl.alive()) return;
        // A Save began while the row was in flight: wait for it, then read the row again.
        if (ctl.saving()) { follow_(ctl, detail); return; }
        var before = ctx.getEditing();
        if (row.type !== ctl.baseline().type) {
          ctx.setEditing(row);
          ctx.reload('providers');
          if (!ctl.isDirty()) {
            ctx.remount(row, detail);
          } else {
            ctl.placeFollowNote(buildNote(detail,
              "This provider's type changed; Cancel to see it"));
            ctl.afterCancel(function () { ctx.remount(row, detail); });
          }
          return;
        }
        var renamed = !before || before.name !== row.name;
        ctx.setEditing(row);
        ctl.rebase(row);
        ctl.placeFollowNote(buildNote(detail));
        ctx.reload('providers');
        if (renamed) ctx.renamed(row);
      }, function () { /* the next open reads the stored row */ });
    });
  }

  function onEvent(detail) {
    if (!ctx || !detail || detail.kind !== 'provider' || !detail.target_id) return;
    var ctl = ctx.getController();
    if (!ctl || ctl.isCreate || ctl.id !== detail.target_id || !ctl.alive()) return;
    follow_(ctl, detail);
  }

  function attach(c) {
    ctx = c;
    if (registered) return;
    registered = true;
    document.addEventListener(App.approvals.CONFIG_CHANGED, function (e) { onEvent(e.detail); });
  }

  window.App.studio.providerEditorFollow = { attach: attach, onEvent: onEvent, buildNote: buildNote };
})();
