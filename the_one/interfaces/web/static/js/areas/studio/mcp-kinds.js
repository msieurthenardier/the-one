// The `mcp_server` kind of the GleepGlorp registry (M36 F4 L4b, flight DD9 and DD11). It registers
// here, where the Studio code it wraps lives, at the end of the Studio script block (after
// agent-kinds.js, so the registry order is agent, rule, routine, mcp_server). Every call into
// App.studio.* is late-bound.
//
// An MCP server is targeted by id: an approval records under (mcp_server, target_id) and
// invalidates the `mcp-sources` store; the card links to #library/mcp/{id}. A create's id exists
// only once it is applied, so a create's `config_changed` frame without a `target_id` records
// nothing. The kind is fillable: the editor is the Library's MCP create form or an existing
// server's edit form.
(function () {
  'use strict';
  window.App = window.App || {};

  function serverExists(view) {
    return App.store.get('mcp-sources', { force: true }).then(function (list) {
      return (list || []).some(function (s) { return s.id === view.target_id; });
    }, function () { return true; }); // unknown: do not call it gone
  }

  var mcpFill = {
    routeFor: function (view) {
      return view.action === 'create'
        ? { destination: 'library', section: 'mcp', create: true }
        : { destination: 'library', section: 'mcp', id: view.target_id };
    },
    openKey: function (view) {
      return view.action === 'create' ? 'create' : 'edit:' + view.target_id;
    },
    exists: serverExists,
    isOpen: function (key) { return App.studio.mcpEditorFill.isOpen(key); },
    whenSettled: function (key) { return App.studio.mcpEditorFill.whenSettled(key); },
    // The MCP editor has no tabs, and a create form does not take focus for a fill.
    select: function () {},
    beforeNavigate: function () {},
    afterNavigate: function () {},
    apply: function (view) { return App.studio.mcpEditorFill.apply(view); }
  };

  App.gleepglorpKinds.register('mcp_server', {
    labels: {
      itemNoun: 'MCP server',
      editorUnavailable: 'The MCP server editor could not open.',
      targetGone: 'That MCP server no longer exists.',
      withdrawnGone: function () { return 'the MCP server no longer exists.'; }
    },
    openLink: function (view) {
      if (!view.target_id) return null;
      return {
        spec: { destination: 'library', section: 'mcp', id: view.target_id },
        text: 'Open MCP server',
        testid: 'proposal-open-item'
      };
    },
    store: 'mcp-sources',
    recordKey: function (detail) {
      return detail && detail.target_id ? { scope: 'target', id: detail.target_id } : null;
    },
    fill: mcpFill
  });
})();
