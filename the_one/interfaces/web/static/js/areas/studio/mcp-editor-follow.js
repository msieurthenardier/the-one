// App.studio.mcpEditorFollow -- the MCP server editor follows a change the operator approved in a
// GleepGlorp chat (M36 F4 L4b, flight DD9). The glue calls attach(ctx) once:
//
//   ctx: {getController() -> the live editor controller or null, state (the Studio state),
//         self (the Studio instance), reload(storeName) (the Library list reload),
//         syncSelection(bool)}
//
// The signal is App.approvals' CONFIG_CHANGED event (the document is the transport, and has no
// `off`), so the listener is registered once per page. For an `mcp_server` change whose
// `target_id` is the open EDIT editor's server (a create form, or another server, is ignored):
// the stored row is fetched and the editor rebased by the controller (a clean field and a clean
// row take the stored value; a dirty one keeps the operator's value while its baseline moves; a
// row only the stored side has is added). A Save in flight defers the rebase until it ends, and
// the row is fetched again then. A Test in flight writes only the cache and does not block.
// The follow note ("Changed by a change you approved in a GleepGlorp chat · time · Open chat")
// sits under the editor's header, and Save or Cancel clears it.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var registered = false;
  var ctx = null;

  function buildNote_(detail) {
    var p = document.createElement('p');
    p.className = 'agent-approved-change-note';
    p.setAttribute('data-testid', 'mcp-approved-change-note');
    var when = '';
    var t = detail.at ? new Date(detail.at) : null;
    if (t && !isNaN(t.getTime())) when = ' · ' + App.time.formatClock(t);
    p.appendChild(document.createTextNode(
      'Changed by a change you approved in a GleepGlorp chat' + when));
    if (detail.session_id) {
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
      App.api.fetchJson('/api/mcp-sources/' + encodeURIComponent(ctl.id)).then(function (src) {
        if (ctx.getController() !== ctl || !ctl.alive()) return;
        // A Save began while the row was in flight: wait for it, then read the row again.
        if (ctl.saving()) { follow_(ctl, detail); return; }
        var before = ctx.state.editingMcpSource;
        var renamed = !before || before.name !== src.name;
        ctx.state.editingMcpSource = src;
        ctl.rebase(src);
        ctl.placeFollowNote(buildNote_(detail));
        ctx.reload('mcp-sources');
        if (renamed && App.router) {
          App.router.sync('studio', ctx.self.serializeState(), { name: src.name });
          ctx.syncSelection(true);
        }
      }, function () { /* the next open reads the stored row */ });
    });
  }

  function onEvent(detail) {
    if (!ctx || !detail || detail.kind !== 'mcp_server' || !detail.target_id) return;
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

  window.App.studio.mcpEditorFollow = { attach: attach, onEvent: onEvent };
})();
