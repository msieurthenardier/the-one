// App.studio.mcpEditor.sandboxFields — the MCP source editor's Sandbox section
// markup (M31 F5 L02, extracted verbatim from renderMcpSourceEditor).
//
// Holds: renderSandboxSection(source, type), the stdio-only network switch and the
// Writable paths chip-list placeholder (mounted by connectionFields.mountChipListEditors).
// Exposes: renderSandboxSection.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  // The Sandbox section's markup (stdio only). `type` is the source's transport.
  function renderSandboxSection(source, type) {
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !source;
    var html = '';
    // ── Sandbox section (stdio only) ──────────────────────────────────
    // F3 L5b: surfaces SandboxProfile fields for stdio sources. Auto-hides
    // for streamable-http via the existing mcp-stdio-only CSS class. The
    // chip-list mounts post-innerHTML in mountChipListEditors.
    var sandboxHidden = (type !== 'stdio');
    var sandbox = (!isCreate && source.config && source.config.sandbox) || {};
    // F9 L2 vibing: new-source default is `true` — the lazy-install runtimes
    // shipped in L2 D2 (uvx, npx, pipx run) all REQUIRE network egress on
    // first spawn to fetch packages from PyPI/npm. Defaulting to `false`
    // here means a fresh stdio source's first Refresh fails. Existing
    // sources preserve their stored value via the explicit `=== true`
    // check below; only when NO sandbox key is present (new-source path)
    // do we fall through to the network-on default.
    var networkAllowed = isCreate
      ? true
      : sandbox.network_allowed === true;
    html += '<div class="editor-section mcp-stdio-only' + (sandboxHidden ? ' is-hidden' : '') + '" data-testid="mcp-sandbox-section">';
    html += '<div class="section-title">Sandbox</div>';
    // Network allowed: stacked .field-group (M17 F5 L4 migration) — label
    // above the iOS-style toggle, matching the self-configuration tab's
    // toggle field-group. The class="field-input" on the checkbox keeps
    // attachStaticListeners wiring dirty-tracking via change events.
    var netTitleText = networkAllowed
      ? 'Network access enabled'
      : 'Network access disabled';
    html += '<div class="field-group mf-sandbox-network-row">';
    html += '<label for="mf-sandbox-network-allowed">Allow network access</label>';
    html += '<label class="tool-enable-switch" title="' + escapeAttr(netTitleText) + '">';
    html += '<input type="checkbox" class="field-input" id="mf-sandbox-network-allowed" data-field="sandbox-network-allowed"' + (networkAllowed ? ' checked' : '') + ' aria-label="Allow network access" />';
    html += '<span class="tool-enable-switch-track" aria-hidden="true"></span>';
    html += '</label>';
    html += '</div>';
    // Writable paths chip-list (mounted via App.adminFormHelpers post-innerHTML).
    // M17 F6 L3: the placeholder <div> carries NO id — mountChipListEditors
    // replaces it via outerHTML= (which would strip an id), so the `label[for]`
    // target is landed on the real `.chip-list-input` via renderChipListEditor's
    // controlId (see mountChipListEditors / the re-mount path below). Post-mount
    // selectors key on [data-field="sandbox-writable-paths"].chip-list-editor,
    // not the id (js:873/917/1505), so dropping the placeholder id is safe.
    html += '<div class="field-group">';
    html += '<label for="mf-sandbox-writable-paths">Writable paths</label>';
    html += '<div class="chip-list-editor" data-field="sandbox-writable-paths" data-field-type="array"></div>';
    html += '</div>';
    html += '</div>';
    return html;
  }

  window.App.studio.mcpEditor.sandboxFields = {
    renderSandboxSection: renderSandboxSection
  };
})();
