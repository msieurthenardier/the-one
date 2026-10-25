// App.studio.mcpEditor.connectionFields — the MCP source editor's Connection
// fields (M31 F5 L02, split out of mcp-server-editor.js, moved verbatim).
//
// Holds: renderConnectionFields (name, transport, stdio command runtime, cwd,
// args placeholder, command hint, URL), mountChipListEditors / wireChipLists
// (the args and sandbox writable-paths chip lists), and the transport and
// stdio-runtime visibility helpers (applyStdioRuntimeSelection,
// applyTransportVisibility).
// Exposes: renderConnectionFields, mountChipListEditors, wireChipLists,
// applyStdioRuntimeSelection, applyTransportVisibility.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var STDIO_CUSTOM_SENTINEL = window.App.studio.mcpEditor.shared.STDIO_CUSTOM_SENTINEL;
  var STDIO_RUNTIME_OPTIONS = window.App.studio.mcpEditor.shared.STDIO_RUNTIME_OPTIONS;
  var deriveStdioRuntimeSelection = window.App.studio.mcpEditor.shared.deriveStdioRuntimeSelection;
  var lookupStdioRuntimeHint = window.App.studio.mcpEditor.shared.lookupStdioRuntimeHint;

  function renderConnectionFields(source, mcpTypes) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !source;
    var type = isCreate ? '' : (source.type || '');
    var stdioHidden = (type !== 'stdio');
    var streamableHidden = (type !== 'streamable-http');

    var html = '';

    // Name
    html += '<div class="field-group">';
    html += '<label for="mf-name">Name</label>';
    html += '<input class="field-input" id="mf-name" data-field="name" value="' + escapeAttr(isCreate ? '' : (source.name || '')) + '" placeholder="My MCP Server" />';
    html += '</div>';

    // Type
    html += '<div class="field-group">';
    html += '<label for="mf-type">Type</label>';
    html += '<select class="field-input field-select" id="mf-type" data-field="type">';
    // F5 L6 HAT: ``hidden`` attribute keeps the placeholder out of the
    // open list while still displaying its text in the closed state.
    if (isCreate) html += '<option value="" disabled selected hidden>Select a transport…</option>';
    var types = mcpTypes || [];
    for (var t = 0; t < types.length; t++) {
      var mt = types[t];
      html += '<option value="' + escapeAttr(mt.value) + '"' + (!isCreate && type === mt.value ? ' selected' : '') + '>' + escapeHtml(mt.label) + '</option>';
    }
    html += '</select>';
    html += '</div>';

    // stdio: command — F9 L2 vibing: replaced free-text input with a
    // canonical-runtime dropdown + Custom… escape. The dropdown is the
    // primary affordance; the legacy free-text input still ships in the DOM
    // (hidden by default) and only surfaces when the operator picks
    // Custom…. Hydrate flow: derive (dropdownValue, displayArgs,
    // customCommand) from the saved (command, args) pair so the dropdown
    // selection round-trips. New stdio source: default to `uvx` (canonical
    // "just works" path); operator can change.
    var savedCommand = (!isCreate && source.config && source.config.command) ? source.config.command : '';
    var savedArgs = (!isCreate && source.config && source.config.args) ? source.config.args : [];
    var stdioSelection = deriveStdioRuntimeSelection(savedCommand, savedArgs);
    var dropdownValue = stdioSelection.dropdownValue || (isCreate ? 'uvx' : '');
    var customCommandValue = stdioSelection.customCommand || '';
    var customCommandHidden = (dropdownValue !== STDIO_CUSTOM_SENTINEL);

    html += '<div class="field-group mcp-stdio-only' + (stdioHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-command-runtime">Command</label>';
    html += '<select class="field-input field-select" id="mf-command-runtime" data-field="command-runtime" data-testid="mcp-command-runtime">';
    for (var ri = 0; ri < STDIO_RUNTIME_OPTIONS.length; ri++) {
      var opt = STDIO_RUNTIME_OPTIONS[ri];
      var isSelected = (opt.value === dropdownValue);
      html += '<option value="' + escapeAttr(opt.value) + '"' + (isSelected ? ' selected' : '') + '>' +
              escapeHtml(opt.label) + '</option>';
    }
    html += '</select>';
    html += '</div>';

    // stdio: custom command (free-text) — only visible when Custom… is
    // selected. The legacy `mf-command` id + data-field="command" are
    // preserved so any external selector that pinned to them keeps
    // working; the field only feeds `config.command` when the dropdown is
    // on the Custom sentinel (collectFormData enforces this).
    html += '<div class="field-group mcp-stdio-only mcp-command-custom-row' +
            (stdioHidden || customCommandHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-command">Custom command</label>';
    html += '<input class="field-input" id="mf-command" data-field="command" data-testid="mcp-command-custom" ' +
            'value="' + escapeAttr(customCommandValue) + '" placeholder="bash /app/start.sh" />';
    html += '</div>';

    // stdio: cwd
    var cwdValue = (!isCreate && source.config && source.config.cwd) ? source.config.cwd : '';
    html += '<div class="field-group mcp-stdio-only' + (stdioHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-cwd">Working Directory</label>';
    html += '<input class="field-input" id="mf-cwd" data-field="cwd" value="' + escapeAttr(cwdValue) + '" placeholder="(optional)" />';
    html += '</div>';

    // stdio: args (chip-list, mounted via App.adminFormHelpers post-innerHTML)
    // M17 F6 L3: placeholder <div> carries NO id (mountChipListEditors replaces
    // it via outerHTML=, which strips ids); the `label[for="mf-args"]` target is
    // landed on the real `.chip-list-input` via renderChipListEditor's controlId.
    // Post-mount selectors key on [data-field="args"].chip-list-editor
    // (js:857/915/1484), not the id, so dropping the placeholder id is safe.
    html += '<div class="field-group mcp-stdio-only' + (stdioHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-args">Arguments</label>';
    html += '<div class="chip-list-editor" data-field="args" data-field-type="array"></div>';
    html += '</div>';

    // F9 L2 vibing: helper text below the args field, dynamically updated
    // on dropdown change. Low-emphasis tone (--fg-secondary, body-sm)
    // matches the studio token convention; uses .form-hint for the new
    // class hook (added in studio.css alongside this leg).
    var initialHint = lookupStdioRuntimeHint(dropdownValue);
    // De-guttered (F5 L4): dropped the empty label-slot + `.field-row` wrapper
    // so the hint aligns flush-left under the now-stacked `.field-group` args
    // field above it (the migration invalidated the old 100px-gutter alignment
    // whose whole purpose was to line up with the label-left args row).
    html += '<div class="mcp-stdio-only mcp-command-hint-row' + (stdioHidden ? ' is-hidden' : '') + '">';
    html += '<small class="form-hint mcp-command-hint" data-testid="mcp-command-hint">' +
            escapeHtml(initialHint) + '</small>';
    html += '</div>';

    // streamable-http: url
    var urlValue = (!isCreate && source.config && source.config.url) ? source.config.url : '';
    html += '<div class="field-group mcp-streamable-http-only' + (streamableHidden ? ' is-hidden' : '') + '">';
    html += '<label for="mf-url">URL</label>';
    html += '<input class="field-input" id="mf-url" data-field="url" value="' + escapeAttr(urlValue) + '" placeholder="https://example.com/mcp" />';
    html += '</div>';

    return html;
  }

  // ── Chip-list mount helpers ─────────────────────────────────────────

  function mountChipListEditors(container, source) {
    var helpers = window.App.adminFormHelpers;
    if (!helpers || !helpers.renderChipListEditor) return;

    var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
    if (argsHost) {
      // F9 L2 vibing: when the saved (command, args) pair represents
      // the `npx -y` or `pipx run` runtime split, the implicit `-y` /
      // `run` lives at args[0]. The dropdown's hydrate path already
      // collapses that pair back into the dropdown selection — strip
      // it from the chip-list so the operator sees only their own args
      // (the package name + flags they typed).
      var savedCmd = (source && source.config && source.config.command) || '';
      var savedArgsList = (source && source.config && source.config.args) || [];
      var derived = deriveStdioRuntimeSelection(savedCmd, savedArgsList);
      argsHost.outerHTML = helpers.renderChipListEditor('args', derived.displayArgs || [], null, { controlId: 'mf-args' });
    }
    // F3 L5b: sandbox writable_paths chip-list (stdio only, but mount for
    // any type — visibility is controlled by the section's mcp-stdio-only
    // class).
    var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
    if (sandboxPathsHost) {
      var sandboxPathsItems = (source && source.config && source.config.sandbox && source.config.sandbox.writable_paths) || [];
      sandboxPathsHost.outerHTML = helpers.renderChipListEditor('sandbox-writable-paths', sandboxPathsItems, null, { controlId: 'mf-sandbox-writable-paths' });
    }
  }

  function wireChipLists(container, onChange) {
    var helpers = window.App.adminFormHelpers;
    if (!helpers || !helpers.wireChipListEditor) return;
    var hosts = container.querySelectorAll('.chip-list-editor');
    for (var i = 0; i < hosts.length; i++) {
      helpers.wireChipListEditor(hosts[i], { onChange: onChange });
    }
  }

  // ── Type-change visibility helpers ──────────────────────────────────

  // F9 L2 vibing: keep the Custom… free-text row's visibility + the
  // args-helper text in sync with the dropdown selection. Called from
  // the change handler AND from revertEditorToSource so a Cancel-revert
  // restores the row visibility to match the source's saved command.
  function applyStdioRuntimeSelection(container, dropdownValue) {
    var customRow = container.querySelector('.mcp-command-custom-row');
    if (customRow) {
      customRow.classList.toggle('is-hidden', dropdownValue !== STDIO_CUSTOM_SENTINEL);
    }
    var hintEl = container.querySelector('[data-testid="mcp-command-hint"]');
    if (hintEl) {
      hintEl.textContent = lookupStdioRuntimeHint(dropdownValue);
    }
  }

  function applyTransportVisibility(container, type) {
    var stdioRows = container.querySelectorAll('.mcp-stdio-only');
    var streamableRows = container.querySelectorAll('.mcp-streamable-http-only');
    for (var i = 0; i < stdioRows.length; i++) {
      stdioRows[i].classList.toggle('is-hidden', type !== 'stdio');
    }
    for (var j = 0; j < streamableRows.length; j++) {
      streamableRows[j].classList.toggle('is-hidden', type !== 'streamable-http');
    }
    var kvLabel = container.querySelector('.kv-section-title');
    if (kvLabel) {
      var stdioLabel = kvLabel.getAttribute('data-stdio-label') || 'Environment Variables';
      var streamLabel = kvLabel.getAttribute('data-streamable-http-label') || 'Custom Headers';
      kvLabel.textContent = (type === 'streamable-http') ? streamLabel : stdioLabel;
    }
  }

  window.App.studio.mcpEditor.connectionFields = {
    renderConnectionFields: renderConnectionFields,
    mountChipListEditors: mountChipListEditors,
    wireChipLists: wireChipLists,
    applyStdioRuntimeSelection: applyStdioRuntimeSelection,
    applyTransportVisibility: applyTransportVisibility
  };
})();
