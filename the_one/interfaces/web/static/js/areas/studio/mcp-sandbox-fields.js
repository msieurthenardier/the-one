// App.studio.mcpEditor.sandboxFields — the MCP source editor's Sandbox section, built
// from the control library (M31 F5 L06, DD4).
//
//   create({source, onChange}) -> {el, values(), setValues(source), setType(type), destroy()}
//
// el is an App.ui.section (stack layout, testid mcp-sandbox-section) holding the
// "Allow network access" switch (mf-sandbox-network-allowed, label inline, with a hint)
// and the Writable paths chip list (mf-sandbox-writable-paths). The section is for stdio
// sources only: setType shows it for `stdio` and hides it for anything else, a create
// form with no type chosen included.
//   values()  {networkAllowed, writablePaths}
//   setValues(source)  a new source (null) has the network on; a stored source takes its
//             stored `network_allowed === true`. It never fires onChange.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  function create(opts) {
    opts = opts || {};
    var ui = window.App.ui;
    var alive = true;
    function report() { if (alive && opts.onChange) opts.onChange(); }

    // The lazy-install runtimes (uvx, npx, pipx run) all need the network on first
    // spawn, so a new source defaults to on; a stored source keeps its stored value.
    var network = ui.toggle({
      label: 'Allow network access',
      id: 'mf-sandbox-network-allowed',
      hint: 'Needed for uvx, npx and pipx run on first use.',
      dataset: { field: 'sandbox-network-allowed' },
      onChange: report
    });
    var paths = ui.chipList({
      inputId: 'mf-sandbox-writable-paths',
      dataset: { field: 'sandbox-writable-paths', fieldType: 'array' },
      onChange: report
    });
    var pathsField = ui.field({ label: 'Writable paths', control: paths.input, host: paths.el });
    var section = ui.section({
      title: 'Sandbox', layout: 'stack', testid: 'mcp-sandbox-section',
      className: 'mcp-stdio-only', children: [network.el, pathsField.el]
    });

    function setValues(source) {
      var sandbox = (source && source.config && source.config.sandbox) || {};
      network.setChecked(!source ? true : sandbox.network_allowed === true);
      paths.setValues(sandbox.writable_paths || []);
    }
    setValues(opts.source || null);

    return {
      el: section.el,
      values: function () {
        return { networkAllowed: network.control.checked, writablePaths: paths.values() };
      },
      setValues: setValues,
      setType: function (type) { section.el.hidden = type !== 'stdio'; },
      destroy: function () {
        alive = false;
        paths.destroy();
      }
    };
  }

  window.App.studio.mcpEditor.sandboxFields = { create: create };
})();
