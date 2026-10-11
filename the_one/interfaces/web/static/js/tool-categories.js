// App.toolCategories -- the ONE built-in tool category table (M25 F4 L6,
// flight DD7, leg AC9). It replaced three hand-kept copies (studio.js's
// per-agent Tools tab table, admin/tools-grid.js's and admin/tools-editor.js's
// tool -> category maps; squawks 0028 and 0032 kept them in step by hand,
// and all three had missed M23 F4 L3's find_platform_destination).
//
// Every tool in the_one/tools/builtins.py::_TOOL_CLASSES is listed exactly
// once: tests/test_tool_categories.py parses _TOOL_CLASSES and this file's
// TABLE and asserts the same set, so a new built-in cannot be silently left
// uncategorised (it would show in no Settings tab and no Tools-tab tile).
//
// The derived shapes, all frozen (read-only, shared by every consumer):
//   order       ['filesystem', 'execution', 'web', 'connectors', 'time']: the
//               category slugs in tab order
//   labels      {slug: 'Filesystem', ...}: the display names
//   byCategory  {'Filesystem': [tool, ...], ...}: label -> tool names, in
//               order (the agent editor's Tools tab, studio.js
//               toolCategories -> tools-tab.js)
//   categoryOf  {tool: 'filesystem', ...}: tool -> slug (the Settings ›
//               Built-in tools tabs, badges and the tool editor's subtitle)
//   ungatedPrefixes  ['mcp__', 'kb__']: name prefixes the whitelist never gates
//               (server: UNGATED_TOOL_PREFIXES)
//   whitelistExempt  ['current_time']: built-ins the `enabled_tools` whitelist
//               never gates (M28; server: WHITELIST_EXEMPT_TOOLS)
// The agent drawer's "What it can use" groups the agent's built-ins by
// byCategory too. Loaded before studio.js and admin/tools-*.js.
(function () {
  'use strict';
  window.App = window.App || {};

  var TABLE = [
    { id: 'filesystem', label: 'Filesystem', tools: ['read_file', 'write_file', 'edit_file', 'delete_file', 'move_file', 'mkdir', 'glob', 'grep', 'list_dir'] },
    { id: 'execution', label: 'Execution', tools: ['shell', 'python_exec', 'shell_session_start', 'shell_session_send', 'shell_session_close', 'shell_session_list'] },
    { id: 'web', label: 'Web', tools: ['download_file', 'fetch_url', 'http_request', 'web_search'] },
    // Mission 23's platform-connector tools: the send and history pair
    // (Flight 2; squawks 0028 and 0032) and the destination lookup (Flight 4
    // Leg 3). Distinct from the Library's Connectors group (connector
    // configs): this is a built-in tool category.
    { id: 'connectors', label: 'Connectors', tools: ['send_to_platform_channel', 'fetch_channel_history', 'find_platform_destination'] },
    // Mission 28 F1: the current-time tool, in its own category (appended last).
    { id: 'time', label: 'Time', tools: ['current_time'] }
  ];

  // Built-ins exempt from the agent's `enabled_tools` whitelist (mirrors
  // the_one/agent/config.py::WHITELIST_EXEMPT_TOOLS; tests/test_tool_categories.py
  // pins the two together). Consumers that mirror the whitelist logic read this.
  var whitelistExempt = Object.freeze(['current_time']);

  // Name prefixes exempt from the `enabled_tools` whitelist (mirrors
  // the_one/agent/config.py::UNGATED_TOOL_PREFIXES; pinned by
  // tests/test_tool_categories.py).
  var ungatedPrefixes = Object.freeze(['mcp__', 'kb__']);

  var order = [];
  var labels = {};
  var byCategory = {};
  var categoryOf = {};
  for (var i = 0; i < TABLE.length; i++) {
    var row = TABLE[i];
    order.push(row.id);
    labels[row.id] = row.label;
    byCategory[row.label] = Object.freeze(row.tools.slice());
    for (var j = 0; j < row.tools.length; j++) categoryOf[row.tools[j]] = row.id;
  }

  window.App.toolCategories = Object.freeze({
    order: Object.freeze(order),
    labels: Object.freeze(labels),
    byCategory: Object.freeze(byCategory),
    categoryOf: Object.freeze(categoryOf),
    whitelistExempt: whitelistExempt,
    ungatedPrefixes: ungatedPrefixes
  });
})();
