// App.studio.mcpEditor.connectionFields — the MCP source editor's Connection
// fields, built from the control library (M31 F5 L06, DD4).
//
//   create({source, mcpTypes, onChange, onTypeChange}) ->
//     {el, values(), baselineFrom(source), setValues(source), setError(field, msg|null),
//      clearErrors(), focus(field), setType(type), destroy()}
//
// Fields, in DOM order: Name, Type, Command (with its runtime hint), Custom command,
// Working directory, Arguments, URL. The ids (mf-name, mf-type, mf-command-runtime,
// mf-command, mf-cwd, mf-url), the data-field values and the testids
// (mcp-command-runtime, mcp-command-custom, mcp-command-hint) are the stable DOM
// contract. Arguments (sortie 18) is a group-mode App.ui.field (testid mcp-args-field,
// data-field="args" on its wrapper, role=group named "Arguments") holding a hint and a
// one-column, movable App.ui.keyValueTable (mcp-args-table, rows mcp-args-row): one row is
// one argument, in order, and a value is never split.
//   values()  {name, type, runtime, command, cwd, args, url}; args is the operator's
//             rows only, each trimmed, blank rows dropped, order and repeats kept (the
//             implicit `-y` of `npx -y` and `run` of `pipx run` are the controller's to
//             prepend on collect).
//   baselineFrom(source)  pure: exactly the values() object that setValues(source) would
//             leave (the controller compares dirty against it, M31 F5 L10). It goes
//             through the controls' own normalisation: args are collected the same way as
//             values() (trimmed, blanks dropped, repeats kept), the runtime comes from
//             deriveStdioRuntimeSelection with its `uvx` default (HTTP sources get it
//             too), and it is built by the same shape() as values(), so the key order
//             cannot drift. Limit: a source
//             type must be among the mount-time Type options (a legacy type is appended
//             at mount), or the select reads '' and the two would differ.
//   setError(field, msg)  puts the message on the field; any user edit of that field clears
//             it again (a runtime or custom-command edit clears both command fields).
//   clearErrors()  clears every field's message.
//   setValues(source)  writes a stored source (or the create defaults for null) into the
//             fields and calls setType; it never fires onChange.
//   setType(type)  shows the stdio-only or the HTTP-only fields through the `hidden`
//             attribute. The mcp-stdio-only and mcp-streamable-http-only classes are
//             plain markers with no CSS.
// onChange fires for every user edit (text on input, selects on change, every argument row
// change: edit, add, remove, move). A setValues (a Cancel's re-set rows included) never
// fires it; the controller recomputes dirty itself. A type change also calls onTypeChange(type).
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

    var byName = {};
    // A user edit of a field clears that field's message, then reports the change.
    function changed(field) {
      if (field === 'runtime' || field === 'command') {
        if (byName.runtime) byName.runtime.setError(null);
        if (byName.command) byName.command.setError(null);
      } else if (byName[field]) {
        byName[field].setError(null);
      }
      if (alive && opts.onChange) opts.onChange();
    }

    // Name
    var nameInput = ui.textInput({
      id: 'mf-name', placeholder: 'My MCP server', dataset: { field: 'name' }, onInput: function () { changed('name'); }
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
        changed('type');
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
      onChange: function () { syncRuntime(); changed('runtime'); }
    });
    var runtimeField = ui.field({
      label: 'Command', control: runtimeSelect, hintTestid: 'mcp-command-hint'
    });
    runtimeField.el.classList.add('mcp-stdio-only');

    var customInput = ui.textInput({
      id: 'mf-command', testid: 'mcp-command-custom', placeholder: 'bash /app/start.sh',
      dataset: { field: 'command' }, onInput: function () { changed('command'); }
    });
    var customField = ui.field({ label: 'Custom command', control: customInput });
    customField.el.classList.add('mcp-stdio-only', 'mcp-command-custom-row');

    var cwdInput = ui.textInput({
      id: 'mf-cwd', placeholder: '(optional)', dataset: { field: 'cwd' }, onInput: function () { changed('cwd'); }
    });
    var cwdField = ui.field({ label: 'Working directory', control: cwdInput });
    cwdField.el.classList.add('mcp-stdio-only');

    var argsTable = ui.keyValueTable({
      columns: [{ key: 'value', label: 'Argument', mono: true, inputTestid: 'mcp-args-input' }],
      movable: true, fill: true, headHidden: true,
      testid: 'mcp-args-table', rowTestid: 'mcp-args-row', removeTestid: 'mcp-args-remove',
      moveUpTestid: 'mcp-args-move-up', moveDownTestid: 'mcp-args-move-down',
      addTestid: 'mcp-args-add-row-btn',
      removeLabel: function (n) { return 'Remove argument ' + n; },
      moveLabel: function (n, row, dir) { return 'Move argument ' + n + ' ' + dir; },
      onChange: function () { changed('args'); }
    });
    var argsField = ui.field({
      label: 'Arguments', group: argsTable.el, hint: 'One argument per row, in order.',
      hintTestid: 'mcp-args-hint', testid: 'mcp-args-field'
    });
    argsField.el.setAttribute('data-field', 'args');
    argsField.el.classList.add('mcp-stdio-only');

    var urlInput = ui.textInput({
      id: 'mf-url', placeholder: 'https://example.com/mcp', dataset: { field: 'url' }, onInput: function () { changed('url'); }
    });
    var urlField = ui.field({ label: 'URL', control: urlInput });
    urlField.el.classList.add('mcp-streamable-http-only');

    var el = document.createElement('div');
    el.className = 'mcp-connection-fields';
    [nameField, typeField, runtimeField, customField, cwdField, argsField, urlField].forEach(
      function (f) { el.appendChild(f.el); });

    byName.name = nameField;
    byName.type = typeField;
    byName.runtime = runtimeField;
    byName.command = customField;
    byName.cwd = cwdField;
    byName.args = argsField;
    byName.url = urlField;

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
      argsTable.setValues((sel.displayArgs || []).map(function (a) { return { value: String(a) }; }));
      urlInput.value = cfg.url || '';
      setType((next && next.type) || '');
    }

    // One argument per entry: ends trimmed, blanks dropped, order and repeats kept, a value
    // never split (sortie 18 DD5).
    function collectArgs(list) {
      var out = [];
      for (var i = 0; i < list.length; i++) {
        var s = String(list[i]).trim();
        if (s) out.push(s);
      }
      return out;
    }

    // The one place the values() key order lives.
    function shape(name, type, runtime, command, cwd, args, url) {
      return {
        name: name, type: type, runtime: runtime, command: command, cwd: cwd, args: args,
        url: url
      };
    }

    function values() {
      return shape(nameInput.value, typeSelect.value, runtimeSelect.value, customInput.value,
        cwdInput.value,
        collectArgs(argsTable.values().map(function (r) { return r.value; })), urlInput.value);
    }

    // The Type select's values at mount: a stored type outside them reads ''.
    var typeValues = {};
    typeOptions.forEach(function (o) { typeValues[o.value] = true; });

    function baselineFrom(next) {
      var cfg = (next && next.config) || {};
      var sel = deriveStdioRuntimeSelection(cfg.command || '', cfg.args || []);
      var type = String((next && next.type) || '');
      return shape(
        String((next && next.name) || ''),
        typeValues[type] ? type : '',
        sel.dropdownValue || 'uvx',
        String(sel.customCommand || ''),
        String(cfg.cwd || ''),
        collectArgs(sel.displayArgs || []),
        String(cfg.url || '')
      );
    }

    setValues(source);

    return {
      el: el,
      values: values,
      baselineFrom: baselineFrom,
      setValues: setValues,
      setError: function (field, msg) {
        if (byName[field]) byName[field].setError(msg || null);
      },
      clearErrors: function () {
        Object.keys(byName).forEach(function (k) { byName[k].setError(null); });
      },
      focus: function (field) {
        var f = byName[field];
        if (!f) return;
        if (f.el.hidden) return;
        if (f === argsField) argsTable.focus();
        else if (f.control) f.control.focus();
      },
      setType: setType,
      destroy: function () {
        alive = false;
        argsTable.destroy();
      }
    };
  }

  window.App.studio.mcpEditor.connectionFields = { create: create };
})();
