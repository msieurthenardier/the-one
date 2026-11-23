// App.studio.mcpEditorFollow -- the MCP server editor follows a change the operator approved in a
// GleepGlorp chat (M36 F4 L4b, flight DD9). The glue calls attach(ctx) once:
//
//   ctx: {getController() -> the live editor controller or null, state (the Studio state),
//         self (the Studio instance), reload(storeName) (the Library list reload),
//         syncSelection(bool)}
//
// The signal is App.approvals' CONFIG_CHANGED event, listened to once per page through
// App.gleepglorpFollow.listen (areas/shared/gleepglorp-follow-core.js, which also holds the note
// and the fetch-and-retry skeleton). For an `mcp_server` change whose `target_id` is the open
// EDIT editor's server (a create form, or another server, is ignored): the stored row is fetched
// and the editor rebased by the controller (a clean field and a clean row take the stored value;
// a dirty one keeps the operator's value while its baseline moves; a row only the stored side has
// is added). A Save in flight defers the rebase until it ends, and the row is fetched again
// then. A Test in flight writes only the cache and does not block.
// The follow note (the approval line with its time and an Open chat link) sits under the
// editor's header, and Save or Cancel clears it.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var ctx = null;

  function follow_(ctl, detail) {
    App.gleepglorpFollow.refetchThen(ctl, '/api/mcp-sources/' + encodeURIComponent(ctl.id),
      function () { return ctx.getController() === ctl; },
      function (src) {
        var before = ctx.state.editingMcpSource;
        var renamed = !before || before.name !== src.name;
        ctx.state.editingMcpSource = src;
        ctl.rebase(src);
        ctl.placeFollowNote(App.gleepglorpFollow.buildNote(detail,
          { testid: 'mcp-approved-change-note' }));
        ctx.reload('mcp-sources');
        if (renamed && App.router) {
          App.router.sync('studio', ctx.self.serializeState(), { name: src.name });
          ctx.syncSelection(true);
        }
      });
  }

  function onEvent(detail) {
    if (!ctx || !App.gleepglorpFollow.matches('mcp_server', detail)) return;
    var ctl = ctx.getController();
    if (!ctl || ctl.isCreate || ctl.id !== detail.target_id || !ctl.alive()) return;
    follow_(ctl, detail);
  }

  function attach(c) {
    ctx = c;
    App.gleepglorpFollow.listen('mcp_server', onEvent);
  }

  window.App.studio.mcpEditorFollow = { attach: attach, onEvent: onEvent };
})();
