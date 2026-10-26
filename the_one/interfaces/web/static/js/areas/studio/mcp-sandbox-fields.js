// App.studio.mcpEditor.sandboxFields — the MCP source editor's Sandbox section, built
// from the control library (M31 F5 L06, DD4).
//
//   create({source, onChange}) ->
//     {el, values(), baselineFrom(source), setValues(source), setType(type), destroy()}
//
// el is an App.ui.section (stack layout, testid mcp-sandbox-section) holding the
// "Allow network access" switch (mf-sandbox-network-allowed, label inline, with a hint)
// and the Writable paths chip list (mf-sandbox-writable-paths). The section is for stdio
// sources only: setType shows it for `stdio` and hides it for anything else, a create
// form with no type chosen included.
//   values()  {networkAllowed, writablePaths}
//   baselineFrom(source)  pure: exactly the values() object setValues(source) would leave
//             (M31 F5 L10): null is the create default (network on), a stored source takes
//             `network_allowed === true`, and the writable paths go through the chip list's
//             normalisation (Strings, repeats dropped), in the same key order as values().
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

    // The one place the values() key order lives.
    function shape(networkAllowed, writablePaths) {
      return { networkAllowed: networkAllowed, writablePaths: writablePaths };
    }

    function baselineFrom(source) {
      var sandbox = (source && source.config && source.config.sandbox) || {};
      return shape(!source ? true : sandbox.network_allowed === true,
        window.App.studio.mcpEditor.shared.uniqueStrings(sandbox.writable_paths));
    }

    function setValues(source) {
      var sandbox = (source && source.config && source.config.sandbox) || {};
      network.setChecked(!source ? true : sandbox.network_allowed === true);
      paths.setValues(sandbox.writable_paths || []);
    }
    setValues(opts.source || null);

    return {
      el: section.el,
      values: function () { return shape(network.control.checked, paths.values()); },
      baselineFrom: baselineFrom,
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
