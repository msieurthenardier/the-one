// App.studio.mcpEditor.connectionFields — the MCP source editor's Connection
// fields, built from the control library (M31 F5 L06, DD4).
//
//   create({source, mcpTypes, onChange, onTypeChange}) ->
//     {el, values(), setValues(source), setError(field, msg|null), focus(field),
//      setType(type), destroy()}
//
// Fields, in DOM order: Name, Type, Command (with its runtime hint), Custom command,
// Working directory, Arguments, URL. The ids (mf-name, mf-type, mf-command-runtime,
// mf-command, mf-cwd, mf-args, mf-url), the data-field values and the testids
// (mcp-command-runtime, mcp-command-custom, mcp-command-hint) are the stable DOM
// contract.
//   values()  {name, type, runtime, command, cwd, args, url}; args is the operator's
//             chips only (the implicit `-y` of `npx -y` and `run` of `pipx run` are the
//             controller's to prepend on collect).
//   setValues(source)  writes a stored source (or the create defaults for null) into the
//             fields and calls setType; it never fires onChange.
//   setType(type)  shows the stdio-only or the HTTP-only fields through the `hidden`
//             attribute. The mcp-stdio-only and mcp-streamable-http-only classes are
//             plain markers with no CSS.
// onChange fires for every user edit (text on input, selects on change, every chip
// change, a Cancel's re-set chips included). A type change also calls onTypeChange(type).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var shared = window.App.studio.mcpEditor.shared;
  var STDIO_CUSTOM_SENTINEL = shared.STDIO_CUSTOM_SENTINEL;
  var STDIO_RUNTIME_OPTIONS = shared.STDIO_RUNTIME_OPTIONS;
  var deriveStdioRuntimeSelection = shared.deriveStdioRuntimeSelection;
  var lookupStdioRuntimeHint = shared.lookupStdioRuntimeHint;

  function create(opts) {
    opts = opts || {};
    var ui = window.App.ui;
    var source = opts.source || null;
    var isCreate = !source;
    var alive = true;
    var currentType = '';

    function report() { if (alive && opts.onChange) opts.onChange(); }

    // Name
    var nameInput = ui.textInput({
      id: 'mf-name', placeholder: 'My MCP server', dataset: { field: 'name' }, onInput: report
    });
    var nameField = ui.field({ label: 'Name', control: nameInput });

    // Type: the placeholder is hidden from the open list (create mode only).
    var typeOptions = [];
    var types = opts.mcpTypes || [];
    if (isCreate) typeOptions.push({ value: '', label: 'Choose how it connects', disabled: true });
    var knownType = false;
    for (var t = 0; t < types.length; t++) {
      typeOptions.push({ value: types[t].value, label: types[t].label });
      if (source && types[t].value === source.type) knownType = true;
    }
    if (!isCreate && !knownType) {
      typeOptions.push({ value: source.type || '', label: source.type || '' });
    }
    var typeSelect = ui.select({
      id: 'mf-type', options: typeOptions, value: isCreate ? '' : (source.type || ''),
      dataset: { field: 'type' },
      onChange: function () {
        setType(typeSelect.value);
        report();
        if (alive && opts.onTypeChange) opts.onTypeChange(typeSelect.value);
      }
    });
    if (isCreate) typeSelect.options[0].hidden = true;
    var typeField = ui.field({ label: 'Type', control: typeSelect });

    // Command: the runtime dropdown and its hint.
    var runtimeSelect = ui.select({
      id: 'mf-command-runtime', testid: 'mcp-command-runtime',
      options: STDIO_RUNTIME_OPTIONS.map(function (o) { return { value: o.value, label: o.label }; }),
      value: 'uvx', dataset: { field: 'command-runtime' },
      onChange: function () { syncRuntime(); report(); }
    });
    var runtimeField = ui.field({
      label: 'Command', control: runtimeSelect, hintTestid: 'mcp-command-hint'
    });
    runtimeField.el.classList.add('mcp-stdio-only');

    var customInput = ui.textInput({
      id: 'mf-command', testid: 'mcp-command-custom', placeholder: 'bash /app/start.sh',
      dataset: { field: 'command' }, onInput: report
    });
    var customField = ui.field({ label: 'Custom command', control: customInput });
    customField.el.classList.add('mcp-stdio-only', 'mcp-command-custom-row');

    var cwdInput = ui.textInput({
      id: 'mf-cwd', placeholder: '(optional)', dataset: { field: 'cwd' }, onInput: report
    });
    var cwdField = ui.field({ label: 'Working directory', control: cwdInput });
    cwdField.el.classList.add('mcp-stdio-only');

    var argsChips = ui.chipList({
      inputId: 'mf-args', dataset: { field: 'args', fieldType: 'array' }, onChange: report
    });
    var argsField = ui.field({ label: 'Arguments', control: argsChips.input, host: argsChips.el });
    argsField.el.classList.add('mcp-stdio-only');

    var urlInput = ui.textInput({
      id: 'mf-url', placeholder: 'https://example.com/mcp', dataset: { field: 'url' }, onInput: report
    });
    var urlField = ui.field({ label: 'URL', control: urlInput });
    urlField.el.classList.add('mcp-streamable-http-only');

    var el = document.createElement('div');
    el.className = 'mcp-connection-fields';
    [nameField, typeField, runtimeField, customField, cwdField, argsField, urlField].forEach(
      function (f) { el.appendChild(f.el); });

    var byName = {
      name: nameField, type: typeField, runtime: runtimeField, command: customField,
      cwd: cwdField, args: argsField, url: urlField
    };

    // The Custom row follows the transport AND the runtime; the hint follows the runtime.
    function syncRuntime() {
      customField.el.hidden = !(currentType === 'stdio' && runtimeSelect.value === STDIO_CUSTOM_SENTINEL);
      runtimeField.setHint(lookupStdioRuntimeHint(runtimeSelect.value));
    }

    function setType(type) {
      currentType = type || '';
      var stdio = currentType === 'stdio';
      runtimeField.el.hidden = !stdio;
      cwdField.el.hidden = !stdio;
      argsField.el.hidden = !stdio;
      urlField.el.hidden = currentType !== 'streamable-http';
      syncRuntime();
    }

    function setValues(next) {
      var cfg = (next && next.config) || {};
      var sel = deriveStdioRuntimeSelection(cfg.command || '', cfg.args || []);
      nameInput.value = (next && next.name) || '';
      typeSelect.value = (next && next.type) || '';
      runtimeSelect.value = sel.dropdownValue || 'uvx';
      customInput.value = sel.customCommand || '';
      cwdInput.value = cfg.cwd || '';
      argsChips.setValues(sel.displayArgs || []);
      urlInput.value = cfg.url || '';
      setType((next && next.type) || '');
    }

    function values() {
      return {
        name: nameInput.value,
        type: typeSelect.value,
        runtime: runtimeSelect.value,
        command: customInput.value,
        cwd: cwdInput.value,
        args: argsChips.values(),
        url: urlInput.value
      };
    }

    setValues(source);

    return {
      el: el,
      values: values,
      setValues: setValues,
      setError: function (field, msg) {
        if (byName[field]) byName[field].setError(msg || null);
      },
      focus: function (field) {
        var f = byName[field];
        if (!f) return;
        var c = f === argsField ? argsChips.input : f.control;
        if (c && !f.el.hidden) c.focus();
      },
      setType: setType,
      destroy: function () {
        alive = false;
        argsChips.destroy();
      }
    };
  }

  window.App.studio.mcpEditor.connectionFields = { create: create };
})();
