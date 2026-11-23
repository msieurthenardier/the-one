// The `mcp_server` kind of the GleepGlorp registry (M36 F4 L4b, flight DD9 and DD11). It registers
// here, where the Studio code it wraps lives, at the end of the Studio script block (after
// agent-kinds.js, so the registry order is agent, rule, routine, mcp_server). The spec is built by
// App.gleepglorpKinds.registerLibraryKind (M36 F5 L2); the call into App.studio.* is late-bound.
//
// An MCP server is targeted by id: an approval records under (mcp_server, target_id) and
// invalidates the `mcp-sources` store; the card links to #library/mcp/{id}. A create's id exists
// only once it is applied, so a create's `config_changed` frame without a `target_id` records
// nothing. The kind is fillable: the editor is the Library's MCP create form or an existing
// server's edit form.
(function () {
  'use strict';
  window.App = window.App || {};

  App.gleepglorpKinds.registerLibraryKind({
    name: 'mcp_server',
    section: 'mcp',
    store: 'mcp-sources',
    noun: 'MCP server',
    fill: function () { return App.studio.mcpEditorFill; }
  });
})();
