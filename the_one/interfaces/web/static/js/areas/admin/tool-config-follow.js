// App.admin.toolConfigFollow -- the Built-in tools page follows a change the operator approved in a
// GleepGlorp chat (M36 F5 L4b, flight DD9 and DD14). tools-page.js calls attach(ctx) once:
//
//   ctx: {getController() -> the live tool editor's controller or null,
//         gridShowing() -> bool (the Tools grid is mounted and showing),
//         followed(detail, row, ctl) (the page's own path: it updates its list cache and the open
//         tool's copy, re-renders the grid and places the grid note; never the Save path and
//         never refresh(), which would re-mount the editor and lose its unsaved edits)}
//
// The signal is App.approvals' CONFIG_CHANGED event, listened to once per page through
// App.gleepglorpFollow.listen (areas/shared/gleepglorp-follow-core.js). The one `tool_config`
// registration serves both the editor and the grid. For a change to a tool the stored row is
// fetched once: through refetchThen when that tool's editor is open (it waits for an in-flight
// Save, preview, test or dialog), plainly when only the grid shows. The editor then rebases (a
// clean field takes the stored value; a dirty one keeps the operator's while its baseline moves)
// and notes each changed field. Off the Tools page nothing is fetched.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  var ctx = null;

  function urlOf(name) { return '/api/tools/configs/' + encodeURIComponent(name); }

  function onEvent(detail) {
    if (!ctx || !App.gleepglorpFollow.matches('tool_config', detail)) return;
    var ctl = ctx.getController();
    var editorOpen = !!ctl && ctl.alive() && ctl.id === detail.target_id;
    if (editorOpen) {
      App.gleepglorpFollow.refetchThen(ctl, urlOf(detail.target_id),
        function () { return ctx.getController() === ctl; },
        function (row) {
          ctl.rebase(row);
          ctl.addFollowNotes(detail, detail.fields);
          ctx.followed(detail, row, ctl);
        });
      return;
    }
    if (!ctx.gridShowing()) return;
    App.api.fetchJson(urlOf(detail.target_id)).then(function (row) {
      if (ctx.gridShowing()) ctx.followed(detail, row, null);
    }, function () { /* the next open reads the stored row */ });
  }

  function attach(c) {
    ctx = c;
    App.gleepglorpFollow.listen('tool_config', onEvent);
  }

  window.App.admin.toolConfigFollow = { attach: attach, onEvent: onEvent };
})();
