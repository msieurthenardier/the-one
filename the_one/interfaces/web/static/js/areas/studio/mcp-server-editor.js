// App.studio.renderMcpSourceEditor — MCP source editor (M07 F1 L6;
// relocated from admin → studio post-F2 retrofit).
//
// Mirrors provider-editor.js structural shape:
//   <div class="editor-header"> … </div>
//   <div class="editor-section">Connection</div>          (name, type, transport-fields)
//   <div class="editor-section">Environment Variables /
//                               Custom Headers</div>      (unified kv table)
//   <div class="editor-section danger-zone"> … </div>     (edit only)
//
// Per-row UI shape (option c): unified kv table with key / value / sensitive
// checkbox / eye / remove columns. The label swaps "Environment Variables"
// (stdio) ↔ "Custom Headers" (streamable-http) on type change. Sensitive=true
// rows route to `secrets[key]`; sensitive=false rows route to `config.env[key]`
// (stdio) or `config.headers[key]` (streamable-http).
//
// Per-key __MASKED__ round-trip: each kv row captures `_originalMasked` at
// mount via data-original-masked attribute. At save time, if value ===
// _originalMasked AND sensitive=true, payload sends '__MASKED__' for that key
// and the L3 endpoint preserves the stored secret.
//
// callbacks: { onBack, onCancel, onSaveSuccess, onDeleteSuccess, onDirtyChange }
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var MASKED_SENTINEL = '__MASKED__';

  // ── F9 L1 (vibing): OAuth-managed-secret-keys allowlist ─────────────
  // Mirrors the backend's `OAUTH_MANAGED_SECRET_KEYS` constant in
  // `the_one/mcp/oauth/storage.py`. Used by the Reset-connection-button
  // visibility check to detect whether a streamable-http source has any
  // OAuth state worth resetting. Keep in sync with the backend constant.
  var OAUTH_MANAGED_SECRET_KEYS = [
    'access_token',
    'refresh_token',
    'token_expires_at',
    'token_type',
    'scope',
    'dcr_credentials',
  ];

  // ── F9 L1 (vibing): inline relative-time helper ─────────────────────
  // No existing App.formatTimeAgo helper found in the codebase; this
  // ~10-LOC inline helper renders a Unix epoch (seconds) as a coarse
  // relative-time string. If a shared helper later lands in app.js or
  // utils.js, replace this and remove.
  function formatTimeAgo(epochSeconds) {
    if (typeof epochSeconds !== 'number' || !isFinite(epochSeconds)) return '';
    var diffSec = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
    if (diffSec < 60) return 'just now';
    var diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return diffMin + ' minute' + (diffMin === 1 ? '' : 's') + ' ago';
    var diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return diffHr + ' hour' + (diffHr === 1 ? '' : 's') + ' ago';
    var diffDay = Math.floor(diffHr / 24);
    return diffDay + ' day' + (diffDay === 1 ? '' : 's') + ' ago';
  }

  // True iff the source carries any OAuth-managed secret. The masked
  // GET response strips these keys entirely (never even masked), so the
  // canonical signal is the presence of ANY managed-key string in the
  // returned secrets dict — but since the API strips them, the UI has
  // no direct read on the OAuth state. Pragmatic substitute: treat the
  // presence of `_cache` (server-written after a successful authenticated
  // /test/connect) as a strong-but-imperfect proxy. The endpoint itself
  // is idempotent on already-clean state, so a Reset click on a source
  // that has no OAuth state is harmless.
  //
  // F9 L1 (vibing) refinement: read the `oauth_active` flag the masked
  // response can carry (server adds it when any managed key is present).
  // If absent, fall back to the cache-presence proxy.
  function hasOAuthState(source) {
    if (!source || source.type !== 'streamable-http') return false;
    if (source.oauth_active === true) return true;
    var secrets = source.secrets || {};
    for (var i = 0; i < OAUTH_MANAGED_SECRET_KEYS.length; i++) {
      if (Object.prototype.hasOwnProperty.call(secrets, OAUTH_MANAGED_SECRET_KEYS[i])) {
        return true;
      }
    }
    // Fallback proxy: a populated _cache implies a successful authed
    // /test/connect happened in the past. Reset is a no-op on already-
    // clean OAuth state, so a false-positive here is harmless.
    return !!(source.config && source.config._cache);
  }

  // ── F8 L2: Capability flags ─────────────────────────────────────────
  // Server capability keys per the installed `mcp` SDK's ServerCapabilities
  // model. 'experimental' is intentionally excluded — it's a free-form
  // sub-namespace dict (per-server custom keys), not a typed presence flag.
  // Update this allowlist when bumping to a newer SDK that adds new typed flags.
  var SPEC_CAPABILITY_KEYS = ['tools', 'resources', 'prompts', 'logging', 'completions', 'tasks'];

  // ── F9 L2 vibing: stdio command runtime dropdown ────────────────────
  // The free-text `command` input let operators type values that would not
  // resolve at runtime (e.g. `python -m foo` when `foo` isn't pip-installed
  // inside the container). The dropdown makes the canonical "just works"
  // runtimes the path of least resistance and keeps a Custom… escape for
  // power users who need bare paths or wrapper scripts.
  //
  // `value` is the dropdown literal (also the saved `config.command` for
  // single-token runtimes). `__custom__` is the sentinel that swaps in the
  // free-text input below. `npx -y` and `pipx run` are 2-token runtimes —
  // at save time they are split into `command=<binary>, args=[<flag>,
  // ...userArgs]` (option (b) in the leg spec); the reverse split happens
  // at hydrate time so the dropdown selection round-trips and the
  // operator's chip-list shows only their own args, not the implicit
  // `-y`/`run`. The literal `npx -y` / `pipx run` is never written to
  // `config.command` — keeps the saved JSON transparent to anyone
  // inspecting it via the API, and avoids the FileNotFoundError that
  // would result if the spawn layer tried to exec a 2-token string as
  // a single binary.
  var STDIO_CUSTOM_SENTINEL = '__custom__';
  var STDIO_RUNTIME_OPTIONS = [
    {
      value: 'uvx',
      label: 'uvx (Python · PyPI lazy install)',
      hint: 'Args: package name (e.g. `mcp-server-time`). Fetched + cached on first use.',
    },
    {
      value: 'npx -y',
      label: 'npx -y (Node · npm lazy install)',
      hint: 'Args: package name (e.g. `@modelcontextprotocol/server-everything`). Fetched + cached on first use.',
    },
    {
      value: 'pipx run',
      label: 'pipx run (Python · PyPI alternative)',
      hint: 'Args: package name. Alternative to uvx.',
    },
    {
      value: 'python',
      label: 'python (pre-installed module/script)',
      hint: 'Args: `-m <module>` (module must be pip-installed) or path to script.',
    },
    {
      value: 'node',
      label: 'node (script path)',
      hint: 'Args: path to .js file inside container.',
    },
    {
      value: 'bash',
      label: 'bash (wrapper script)',
      hint: 'Args: path to shell script.',
    },
    {
      value: STDIO_CUSTOM_SENTINEL,
      label: 'Custom…',
      hint: 'Free-text mode — operator owns the command resolution. ' +
            'Common patterns: `bash /app/script.sh`, absolute paths, custom binaries on container PATH.',
    },
  ];

  // True when `value` matches one of the canonical runtime literals (i.e.
  // not Custom). Used at hydrate time to decide whether to round-trip the
  // saved command into the dropdown vs. the Custom… free-text field.
  function findStdioRuntimeOption(value) {
    if (!value) return null;
    for (var i = 0; i < STDIO_RUNTIME_OPTIONS.length; i++) {
      var opt = STDIO_RUNTIME_OPTIONS[i];
      if (opt.value === STDIO_CUSTOM_SENTINEL) continue;
      if (opt.value === value) return opt;
    }
    return null;
  }

  // Decompose a stored (command, args) pair into (dropdownValue, displayArgs).
  // Handles the `npx -y` split (option (b)): command=npx + args[0]=-y →
  // dropdownValue='npx -y', displayArgs=args.slice(1). Same pattern for
  // `pipx run`: command=pipx + args[0]=run → dropdownValue='pipx run',
  // displayArgs=args.slice(1). Falls back to the saved literal for the
  // other single-token runtimes; everything else (bash /app/x.sh,
  // absolute paths, etc.) lands on Custom… with the raw command string
  // preserved into the free-text field.
  function deriveStdioRuntimeSelection(command, args) {
    var argsList = Array.isArray(args) ? args.slice() : [];
    var cmd = (typeof command === 'string') ? command : '';
    if (!cmd) {
      // No saved command (newly typed-in row, defensive). Caller decides
      // the default; we just report "no match".
      return { dropdownValue: '', displayArgs: argsList, customCommand: '' };
    }
    // npx -y round-trip: detect and re-collapse.
    if (cmd === 'npx' && argsList.length > 0 && argsList[0] === '-y') {
      return {
        dropdownValue: 'npx -y',
        displayArgs: argsList.slice(1),
        customCommand: '',
      };
    }
    // pipx run round-trip: detect and re-collapse.
    if (cmd === 'pipx' && argsList.length > 0 && argsList[0] === 'run') {
      return {
        dropdownValue: 'pipx run',
        displayArgs: argsList.slice(1),
        customCommand: '',
      };
    }
    var match = findStdioRuntimeOption(cmd);
    if (match) {
      return { dropdownValue: cmd, displayArgs: argsList, customCommand: '' };
    }
    // Anything else falls into Custom… with the full saved string.
    return {
      dropdownValue: STDIO_CUSTOM_SENTINEL,
      displayArgs: argsList,
      customCommand: cmd,
    };
  }

  function lookupStdioRuntimeHint(dropdownValue) {
    for (var i = 0; i < STDIO_RUNTIME_OPTIONS.length; i++) {
      if (STDIO_RUNTIME_OPTIONS[i].value === dropdownValue) {
        return STDIO_RUNTIME_OPTIONS[i].hint;
      }
    }
    return '';
  }

  // F9 L1 (vibing): tools-list HTML extracted from handleTestConnection
  // so initial-mount cached render and post-refresh render share one
  // template. `tools` is the same shape both paths produce — array of
  // {name, description, input_schema}.
  function renderToolsListHtml(tools) {
    var escapeHtml = window.App.escapeHtml;
    var html = '';
    for (var i = 0; i < tools.length; i++) {
      var t = tools[i];
      var desc = t.description || '';
      var truncated = desc.length > 100 ? desc.slice(0, 100) + '…' : desc;

      // Summary line: `name — preview` (single line, 100-char ellipsis,
      // matches the agent-editor MCPs tab tile shape). Body reveals the
      // full description (with line breaks preserved) + the input schema
      // collapsible. Mission 08 F4 L3.
      html += '<details class="mcp-tool-item">';
      html += '<summary class="mcp-tool-summary">';
      html += '<span class="mcp-tool-summary-text">';
      html += '<span class="mcp-tool-name">' + escapeHtml(t.name) + '</span>';
      if (desc) {
        html += '<span class="mcp-tool-summary-desc"> — ' + escapeHtml(truncated) + '</span>';
      }
      html += '</span>';
      html += '<span class="mcp-tool-chevron">▸</span>';
      html += '</summary>';

      html += '<div class="mcp-tool-body">';

      // Section 1: Prompt (the tool description; this IS what the LLM sees).
      html += '<div class="mcp-tool-section">';
      html += '<div class="mcp-tool-section-label">Prompt</div>';
      if (desc) {
        var safeDesc = escapeHtml(desc).replace(/\n/g, '<br>');
        html += '<div class="mcp-tool-full-description">' + safeDesc + '</div>';
      } else {
        html += '<div class="mcp-tool-full-description mcp-tool-description-empty">(no description provided)</div>';
      }
      html += '</div>';

      // Section 2: Input Schema (always rendered, even when absent — labeled
      // section makes the contract visible rather than silently absent).
      html += '<div class="mcp-tool-section">';
      html += '<div class="mcp-tool-section-label">Input Schema</div>';
      if (t.input_schema && Object.keys(t.input_schema).length > 0) {
        var schemaJson = JSON.stringify(t.input_schema, null, 2);
        html += '<pre class="mcp-tool-schema-content">' + escapeHtml(schemaJson) + '</pre>';
      } else {
        html += '<div class="mcp-tool-schema-empty">(no input schema)</div>';
      }
      html += '</div>';

      html += '</div>';
      html += '</details>';
    }
    return html;
  }

  function renderCapabilityFlags(capabilities) {
    if (!capabilities) return ''; // capabilities key missing entirely (pre-L1 server, defensive)
    var present = SPEC_CAPABILITY_KEYS.filter(function (k) {
      var v = capabilities[k];
      return v !== null && v !== undefined;
    });
    if (present.length === 0) {
      // Pathological but documented: server announced no capabilities.
      // Render an explicit message so operators don't see a blank status area.
      return '<div class="mcp-capability-flags mcp-capability-flags-empty">Server announced no capabilities.</div>';
    }
    return (
      '<div class="mcp-capability-flags">' +
      'Server supports: <strong>' + present.join(', ') + '</strong>' +
      '</div>'
    );
  }

  // F4 L3 (M08): Render the "Server" section — surfaces everything the
  // MCP `initialize()` response gave us:
  //   - serverInfo: title/name/version/websiteUrl/icons
  //   - negotiated protocol version (cache.protocol_version)
  //   - instructions (server-supplied usage prose, often long)
  //   - capabilities (rendered as the same flags line as the Tools status)
  //   - _meta (free-shape; only displayed when populated)
  // Defensive on every field — all are spec-optional. Returns '' if the
  // cache has none of them.
  function renderServerInfoSection(cache) {
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var safeUrl = window.App.safeUrl;
    if (!cache) return '';

    var info = cache.server_info || {};
    var title = info.title || info.name || '';
    var nameSubtitle = (info.title && info.name && info.title !== info.name) ? info.name : '';
    var version = info.version || '';
    var websiteUrl = info.websiteUrl || '';
    var icons = Array.isArray(info.icons) ? info.icons : [];
    var protocolVersion = cache.protocol_version || '';
    var instructions = cache.instructions || '';
    var capabilities = cache.capabilities || null;
    var meta = cache.meta && typeof cache.meta === 'object' && Object.keys(cache.meta).length > 0
      ? cache.meta
      : null;

    // If the cache has none of the renderable fields, skip the section
    // entirely (caller already gates on the same condition; defensive).
    if (!title && !version && !websiteUrl && icons.length === 0 &&
        !protocolVersion && !instructions && !capabilities && !meta) {
      return '';
    }

    var html = '';
    html += '<div class="editor-section mcp-server-info-section" data-testid="mcp-server-info-section">';
    html += '<div class="section-title">Server</div>';

    // Identity row — icon (if any) + title + version + protocol version badge.
    // Squawk 0010: icons[0].src is MCP-server-supplied (initialize() response
    // from a third party) and is fetched by the operator's browser outside
    // the app's SSRF-guarded transport — route through the fail-closed
    // http(s)-only allow-list and drop the element entirely on rejection
    // (never emit a rejected scheme into a live src).
    var safeIconSrc = (icons.length > 0 && icons[0] && icons[0].src)
      ? safeUrl(icons[0].src)
      : null;
    html += '<div class="mcp-server-identity">';
    if (safeIconSrc) {
      // F2 Leg 2 (A.6): icon is decorative — the server title is rendered
      // alongside (L343-344). Always emit alt="" so SR doesn't announce
      // the icon MIME type as text content.
      html += '<img class="mcp-server-icon" src="' + escapeAttr(safeIconSrc) + '"' +
        ' alt=""' +
        ' loading="lazy" decoding="async">';
    }
    html += '<div class="mcp-server-identity-text">';
    if (title) {
      html += '<div class="mcp-server-title">' + escapeHtml(title) + '</div>';
    }
    if (nameSubtitle) {
      html += '<div class="mcp-server-name-subtitle">' + escapeHtml(nameSubtitle) + '</div>';
    }
    var versionLineParts = [];
    if (version) versionLineParts.push('v' + escapeHtml(version));
    if (protocolVersion) versionLineParts.push('protocol ' + escapeHtml(protocolVersion));
    if (versionLineParts.length > 0) {
      html += '<div class="mcp-server-version-line">' + versionLineParts.join(' · ') + '</div>';
    }
    if (websiteUrl) {
      // Squawk 0010: same MCP-server-supplied / fail-closed treatment as the
      // icon above, applied to the clickable link. On rejection, render the
      // raw string as inert text (still escaped) rather than dropping the
      // whole row — the operator can still see what the server claimed, it
      // just isn't a live href in the app's own origin.
      var safeWebsiteHref = safeUrl(websiteUrl);
      if (safeWebsiteHref) {
        html += '<div class="mcp-server-website">' +
          '<a href="' + escapeAttr(safeWebsiteHref) + '" target="_blank" rel="noopener noreferrer">' +
            escapeHtml(websiteUrl) +
          '</a>' +
        '</div>';
      } else {
        html += '<div class="mcp-server-website">' + escapeHtml(websiteUrl) + '</div>';
      }
    }
    html += '</div>'; // mcp-server-identity-text
    html += '</div>'; // mcp-server-identity

    // Capabilities — reuse the existing flags renderer for vocabulary parity.
    if (capabilities) {
      html += renderCapabilityFlags(capabilities);
    }

    // Instructions — collapsible since Cloudflare-class servers ship
    // multi-paragraph guidance. Default closed; renders the prose with
    // newlines preserved.
    if (instructions) {
      html += '<details class="mcp-server-instructions" data-testid="mcp-server-instructions">';
      html += '<summary class="mcp-server-instructions-summary">' +
        '<span class="mcp-server-instructions-label">Instructions</span>' +
        '<span class="mcp-server-instructions-chevron">▸</span>' +
      '</summary>';
      html += '<div class="mcp-server-instructions-body">' +
        escapeHtml(instructions).replace(/\n/g, '<br>') +
      '</div>';
      html += '</details>';
    }

    // _meta — debug/free-shape. Render as collapsible JSON if non-empty.
    if (meta) {
      var metaJson = JSON.stringify(meta, null, 2);
      html += '<details class="mcp-server-meta" data-testid="mcp-server-meta">';
      html += '<summary class="mcp-server-meta-summary">' +
        '<span class="mcp-server-meta-label">Metadata</span>' +
        '<span class="mcp-server-meta-chevron">▸</span>' +
      '</summary>';
      html += '<pre class="mcp-server-meta-content">' + escapeHtml(metaJson) + '</pre>';
      html += '</details>';
    }

    html += '</div>'; // mcp-server-info-section
    return html;
  }

  // Mount-time gate for the Server section — shared with the post-refresh
  // repaint (syncServerInfoSection) so both paths agree on when it shows.
  function cacheHasServerInfo(cache) {
    return !!(cache && (cache.server_info || cache.instructions ||
      cache.capabilities || cache.meta || cache.protocol_version));
  }

  // Squawk 0102: repaint the Server section in place after a successful
  // Refresh connection. The section was previously rendered only at mount,
  // so a server that reported a new serverInfo (e.g. an upgraded version)
  // kept showing the old value until the editor was re-mounted. Targeted
  // DOM mutation only — replace the existing node, insert it above the
  // Tools section if this is the first refresh to populate it, or remove
  // it if the cache no longer qualifies. A full re-render would clobber
  // dirty form state. The section's only interactive parts are native
  // <details> elements, so nothing needs re-wiring after replacement.
  function syncServerInfoSection(container, cache) {
    var existing = container.querySelector('[data-testid="mcp-server-info-section"]');
    var html = cacheHasServerInfo(cache) ? renderServerInfoSection(cache) : '';
    var fresh = null;
    if (html) {
      var tmp = document.createElement('div');
      tmp.innerHTML = html;
      fresh = tmp.firstElementChild;
    }
    if (existing) {
      if (fresh) {
        existing.parentNode.replaceChild(fresh, existing);
      } else {
        existing.parentNode.removeChild(existing);
      }
      return;
    }
    if (!fresh) return;
    var toolsSection = container.querySelector('.mcp-tools-section');
    if (toolsSection && toolsSection.parentNode) {
      toolsSection.parentNode.insertBefore(fresh, toolsSection);
    }
  }

  // ── Public entry point ──────────────────────────────────────────────

  function renderMcpSourceEditor(container, source, mcpTypes, callbacks) {
    callbacks = callbacks || {};
    var escapeHtml = window.App.escapeHtml;
    var escapeAttr = window.App.escapeAttr;
    var isCreate = !source;
    var name = isCreate ? 'New MCP Server' : (source.name || '');
    var type = isCreate ? '' : (source.type || '');

    // ── Header ─────────────────────────────────────────────────────────
    var html = '';
    html += '<div class="editor-header">';
    html += '<div class="editor-header-text">';
    html += '<h1 class="editor-title">' + escapeHtml(name) + '</h1>';
    if (!isCreate) {
      var summary = '';
      if (source.config) {
        if (type === 'stdio' && source.config.command) summary = source.config.command;
        else if (type === 'streamable-http' && source.config.url) summary = source.config.url;
      }
      var subtitleParts = [escapeHtml(type)];
      if (summary) subtitleParts.push(escapeHtml(summary));
      html += '<p class="editor-subtitle">' + subtitleParts.join(' · ') + '</p>';
    }
    html += '</div>';

    // Action cluster
    html += '<div class="form-actions">';
    html += '<button type="button" class="btn-outlined-primary back-btn" data-testid="back-mcp-source-btn" aria-label="Back to MCP server list">' + window.App.icon('arrow-left') + ' Back</button>';
    html += '<button type="button" class="btn-outlined-primary cancel-btn" data-testid="cancel-mcp-source-btn" disabled>Cancel</button>';
    html += '<button type="button" class="btn-filled-primary save-btn" data-testid="save-mcp-source-btn" disabled>' + (isCreate ? 'Create' : 'Save') + '</button>';
    html += '<span class="editor-error"></span>';
    html += '</div>';
    html += '</div>'; // .editor-header

    // ── Connection section ────────────────────────────────────────────
    html += '<div class="editor-section">';
    html += '<div class="section-title">Connection</div>';
    html += renderConnectionFields(source, mcpTypes);
    // F9 L1: Refresh-connection button (renamed from "Test connection")
    // lives at the bottom of the Connection section in edit-mode for
    // streamable-http sources. The result panel renders into the Tools
    // section below. The data-testid hook stays "mcp-test-connection"
    // so existing browser-test selectors keep working — it's an
    // implementation handle, not a label.
    //
    // F9 L1 (vibing follow-up): Reset connection button paired with
    // Refresh in the same row. Reset is reversible (just re-OAuth) — it
    // belongs next to Refresh as a secondary connection action, not in
    // Danger Zone. Visible only when the source carries OAuth state
    // (gated by `hasOAuthState`); hidden for stdio and unauth'd
    // streamable-http. Uses the same `btn-outlined-primary` cosmetic as
    // Refresh so the pair reads as grouped connection controls.
    //
    // F9 L1 (vibing polish): "Last updated" label lives inside the
    // same flex row as Refresh/Reset, pushed to the far end via
    // `margin-left: auto`. Low-emphasis (--fg-secondary, body-sm) so it
    // reads as informational, not actionable. Hidden until a successful
    // refresh seeds source.config._cache.last_updated. Placed AFTER the
    // buttons in source order so syncResetButtonVisibility can insert
    // Reset between Refresh and the label without re-shuffling.
    // F9 L2 D1: Refresh-connection button now renders for BOTH streamable-http
    // AND stdio sources. Stdio's backend dispatch (api.py /test/connect) is a
    // straight transient-client lifecycle — no OAuth, no popup. The Reset
    // button is gated by hasOAuthState() which already returns false for stdio,
    // so the existing OAuth-state-dependent UI hides itself for stdio without
    // additional changes here.
    if (!isCreate && source && (source.type === 'streamable-http' || source.type === 'stdio')) {
      html += '<div class="field-row admin-pf-row mcp-test-row">';
      html += '<label></label>';
      html += '<div class="mcp-connection-actions">';
      html += '<button type="button" class="btn-outlined-primary mcp-refresh-connection-btn" data-testid="mcp-test-connection">' +
              window.App.icon('refresh-cw') + ' Refresh connection</button>';
      if (hasOAuthState(source)) {
        var resetTooltip = 'Reset this connection? This clears the stored login and tools list. ' +
          'You will need to log in again on the next refresh.';
        html += '<button type="button" class="btn-outlined-primary mcp-reset-connection-btn" data-testid="reset-mcp-connection-btn" title="' + escapeAttr(resetTooltip) + '" aria-label="' + escapeAttr(resetTooltip) + '" data-name="' + escapeAttr(source.name || '') + '"><span data-confirm-title>Reset connection</span></button>';
      }
      var connCache = (source.config && source.config._cache) || null;
      // F4 L7 (M08): LED moved from the Tools-status banner up to the
      // connection-actions row so it sits adjacent to the Refresh button
      // that drives its state. Computed from cache shape (mirrors the
      // success-when-tools-present heuristic the banner uses below).
      var connLedState = (connCache && Array.isArray(connCache.tools)) ? 'success' : 'idle';
      var connLedLabel = (connLedState === 'success') ? 'Connected' : 'Not connected';
      html += '<span class="indicator-led indicator-led--' + connLedState +
              '" data-testid="mcp-connection-led" data-state="' + connLedState +
              '" aria-label="' + connLedLabel + '"></span>';
      var connLastUpdatedText = connCache ? formatTimeAgo(connCache.last_updated) : '';
      var connLastUpdatedHidden = connLastUpdatedText ? '' : ' hidden';
      html += '<div class="mcp-tools-last-updated" data-testid="mcp-tools-last-updated"' +
              connLastUpdatedHidden + '>' +
              (connLastUpdatedText ? 'Last updated: ' + escapeHtml(connLastUpdatedText) : '') +
              '</div>';
      html += '</div>';
      html += '</div>';
    }
    html += '</div>';

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

    // ── Tools section (edit only, streamable-http + stdio) ────────────
    // Populated by handleTestConnection after a successful refresh. Empty
    // state until first refresh runs. Verbose tool descriptions (e.g.
    // Cloudflare API MCP) get a collapsible <details> per tool so the
    // section stays scannable.
    //
    // F9 L1: Tools section moved ABOVE the Custom Headers section per
    // operator feedback — connection diagnostics belong nearer the
    // Connection block, headers are configuration that lives further down.
    //
    // F9 L1 (vibing): if the backend persisted a tools cache to
    // source.config._cache after a previous successful refresh, render
    // it on initial mount so the operator sees the tools list without
    // having to click Refresh first. Cache is updated server-side on
    // every successful /test/connect.
    //
    // F9 L1 (vibing polish): the "Last updated" timestamp moved up to
    // the connection-actions row (next to Refresh/Reset) so it sits
    // visually with the controls that drive its value. The label is
    // rendered above; this section now contains only the connection
    // status banner + the tool list.
    //
    // F9 L2 D1: Tools section renders for stdio sources too so the
    // post-test render path (capability flags + collapsible schemas)
    // shares the same code path with streamable-http.
    if (!isCreate && source && (source.type === 'streamable-http' || source.type === 'stdio')) {
      var cache = (source.config && source.config._cache) || null;
      // F4 L3 (M08): Server section — surfaces server-declared identity
      // (serverInfo: title / name / version / websiteUrl / icons), the
      // negotiated protocol version, the server's free-form instructions
      // prose, declared capabilities, and any `_meta` extras. Rendered
      // above Tools when any of these are available in the cache.
      if (cacheHasServerInfo(cache)) {
        html += renderServerInfoSection(cache);
      }
      html += '<div class="editor-section mcp-tools-section">';
      html += '<div class="section-title">Tools</div>';
      if (cache && Array.isArray(cache.tools)) {
        // F4 L7 (M08): LED + "Connected." moved up to the connection-actions
        // row. The status banner here keeps the tool-count line + the
        // `mcp-test-status` data-testid that browser tests assert against.
        var statusInner = (
          'Server exposes <strong>' + cache.tools.length + '</strong> tool' +
          (cache.tools.length === 1 ? '' : 's') + '.'
        );
        html += '<div class="mcp-tools-status" data-testid="mcp-test-status">' + statusInner + '</div>';
        html += '<div class="mcp-tools-list" data-testid="mcp-tools-list">' +
                renderToolsListHtml(cache.tools) +
                '</div>';
      } else {
        html += '<div class="mcp-tools-status" data-testid="mcp-test-status">';
        html += 'Click <strong>Refresh connection</strong> above to discover the tools this server exposes.';
        html += '</div>';
        html += '<div class="mcp-tools-list" data-testid="mcp-tools-list" hidden></div>';
      }
      html += '</div>';
    }

    // ── Environment / Headers section ─────────────────────────────────
    // Sits below Tools for streamable-http (F9 L1 reorder); for stdio
    // there is no Tools section, so it lands right after Sandbox as before.
    var kvLabel = (type === 'streamable-http') ? 'Custom Headers' : 'Environment Variables';
    html += '<div class="editor-section">';
    html += '<div class="section-title kv-section-title" ' +
            'data-stdio-label="Environment Variables" ' +
            'data-streamable-http-label="Custom Headers">' +
            escapeHtml(kvLabel) + '</div>';
    html += renderKvTable(source, type);
    html += '</div>';

    // ── Danger Zone (edit only) ───────────────────────────────────────
    // F9 L1 (vibing follow-up): the "Reset connection" button moved out
    // of Danger Zone and now sits next to Refresh in the Connection
    // block — it's a reversible operation (re-OAuth on next Refresh),
    // not a destructive one. Danger Zone now contains only Delete.
    if (!isCreate) {
      html += '<div class="editor-section danger-zone">';
      html += '<div class="section-title danger-zone-title">Danger Zone</div>';
      // F9 L1 (vibing polish): trash icon to the LEFT of the label,
      // mirroring the Refresh button's icon-then-text pattern and the
      // per-row Custom Headers trash glyph. The icon sits OUTSIDE the
      // `data-confirm-title` span so App.confirmDelete only swaps the
      // label text on arm; the glyph persists through the confirm flow.
      html += '<button type="button" class="btn-muted-destructive delete-btn mcp-delete-btn" data-testid="delete-mcp-source-btn" data-name="' + escapeAttr(source.name || '') + '">' +
              window.App.icon('trash') +
              '<span data-confirm-title>Delete MCP Server</span>' +
              '</button>';
      html += '</div>';
    }

    container.innerHTML = html;

    mountChipListEditors(container, source);
    wireEditorEvents(container, source, mcpTypes, callbacks);
  }

  // ── Field rendering ─────────────────────────────────────────────────

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

  function collectExistingKvRows(source, type) {
    /* Walk source.config.env (stdio) or source.config.headers
       (streamable-http) AND source.secrets to build the kv-row union list.
       Per-row data shape: { key, value, sensitive, _originalMasked }.
       For sensitive rows the value field is the masked tail, captured into
       _originalMasked for round-trip preservation. */
    var rows = [];
    if (!source) return rows;
    var cfg = source.config || {};
    var plaintextDict = (type === 'streamable-http') ? (cfg.headers || {}) : (cfg.env || {});
    var secrets = source.secrets || {};
    var seen = Object.create(null);

    // Plaintext rows first (in dict-iteration order).
    for (var k in plaintextDict) {
      if (Object.prototype.hasOwnProperty.call(plaintextDict, k)) {
        rows.push({ key: k, value: String(plaintextDict[k]), sensitive: false, _originalMasked: '' });
        seen[k] = true;
      }
    }
    // Sensitive rows.
    for (var sk in secrets) {
      if (!Object.prototype.hasOwnProperty.call(secrets, sk)) continue;
      if (seen[sk]) continue; // operator may have a duplicate key; plaintext wins.
      var maskedVal = String(secrets[sk] == null ? '' : secrets[sk]);
      rows.push({ key: sk, value: maskedVal, sensitive: true, _originalMasked: maskedVal });
    }
    return rows;
  }

  // F9 L1: hint copy migrated from a `<p class="kv-hint">` paragraph below
  // the table to the title attribute of an info icon next to the
  // "Sensitive" column header. Single source of truth for the tooltip text.
  var SENSITIVE_HINT = 'Sensitive values are encrypted at rest. ' +
    'Unchecking Sensitive on a stored secret clears the value — re-type to keep it.';

  function renderKvTable(source, type) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var existingRows = collectExistingKvRows(source, type);
    // F9 L1: thead is hidden when the table has zero rows (empty state).
    // The `is-hidden` class is toggled at row-add / row-remove time so the
    // header reveals itself with the first data row.
    var headHiddenClass = existingRows.length === 0 ? ' is-hidden' : '';
    // F9 L1: info icon (existing studio pattern from tools-form-helpers.js)
    // next to the "Sensitive" column header. Tooltip explains the
    // encrypted-at-rest contract and the unchecking-clears-value rule.
    var infoIconHtml = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';
    var sensitiveHeader = 'Sensitive ' +
      '<button type="button" class="field-info-icon mcp-kv-sensitive-info" ' +
      'title="' + escapeAttr(SENSITIVE_HINT) + '" ' +
      'aria-label="' + escapeAttr(SENSITIVE_HINT) + '" ' +
      'data-testid="mcp-kv-sensitive-info">' + infoIconHtml + '</button>';
    var html = '<table class="mcp-kv-table" data-testid="mcp-kv-table">';
    html += '<thead class="mcp-kv-thead' + headHiddenClass + '" data-testid="mcp-kv-thead">' +
            '<tr><th>Key</th><th>Value</th>' +
            '<th class="mcp-kv-th-sensitive">' + sensitiveHeader + '</th>' +
            '<th aria-label="Actions"></th></tr></thead>';
    html += '<tbody data-testid="mcp-kv-tbody">';
    for (var i = 0; i < existingRows.length; i++) {
      html += renderKvRow(existingRows[i], i);
    }
    html += '</tbody></table>';
    html += '<button type="button" class="btn-outlined-primary kv-add-row-btn" data-testid="kv-add-row-btn">+ Add row</button>';
    // Suppress unused-var warning in legacy environments — referenced indirectly above.
    void escapeHtml;
    return html;
  }

  function renderKvRow(row, idx) {
    var escapeAttr = window.App.escapeAttr;
    var sensitive = !!row.sensitive;
    var inputType = sensitive ? 'password' : 'text';
    var origMasked = row._originalMasked || '';
    var html = '';
    html += '<tr class="mcp-kv-row" data-row-idx="' + idx + '">';
    html += '<td><input class="field-input kv-key-input" data-field="kv-key" data-row="' + idx + '" value="' + escapeAttr(row.key || '') + '" placeholder="KEY" /></td>';
    html += '<td><div class="api-key-wrap">';
    html += '<input class="field-input kv-value-input' + (sensitive ? ' kv-value-secret' : '') + '" type="' + inputType + '" data-field="kv-value" data-row="' + idx + '" value="' + escapeAttr(row.value || '') + '" data-original-masked="' + escapeAttr(origMasked) + '" placeholder="value" />';
    if (sensitive) {
      html += '<button class="api-key-eye kv-eye-btn" type="button" data-row="' + idx + '" aria-label="Show value">' + window.App.icon('eye') + '</button>';
    }
    html += '</div></td>';
    // F9 L1: per-row sensitive control switched from <input type="checkbox">
    // to the studio iOS-style toggle pattern (`tool-enable-switch` + track).
    // The checkbox is visually-hidden inside the label; CSS in admin.css
    // renders the toggle. The class name `kv-sensitive-checkbox` is kept
    // on the input element so partitionKvRows / handleSensitiveToggle /
    // getFormSnapshot continue to match the same selector.
    html += '<td class="mcp-kv-sensitive-cell">';
    html += '<label class="tool-enable-switch mcp-kv-sensitive-switch" aria-label="Mark sensitive">';
    html += '<input type="checkbox" class="kv-sensitive-checkbox" data-field="kv-sensitive" data-row="' + idx + '"' + (sensitive ? ' checked' : '') + ' aria-label="Mark sensitive" />';
    html += '<span class="tool-enable-switch-track" aria-hidden="true"></span>';
    html += '</label>';
    html += '</td>';
    // F9 L1: per-row remove affordance switched from the `x` close-icon to
    // the studio `trash` icon used elsewhere for destructive row actions.
    html += '<td><button type="button" class="kv-remove-row-btn" data-row="' + idx + '" aria-label="Remove row" title="Remove row">' + window.App.icon('trash') + '</button></td>';
    html += '</tr>';
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

  // ── Form snapshot + dirty tracking ──────────────────────────────────

  function getFormSnapshot(container) {
    /* Three explicit walks (avoid the flat data[dataset.field] = value
       collision since multiple kv rows share data-field="kv-key" etc.). */
    var helpers = window.App.adminFormHelpers;
    var staticData = {};
    // F3 L5b: sandbox-network-allowed is a checkbox; the loop below reads
    // el.checked for type === 'checkbox' and el.value otherwise.
    // F9 L2 vibing: `command-runtime` is the new dropdown driving the
    // stdio command field. It needs to be in the dirty-tracking snapshot
    // so changing the dropdown alone (e.g. uvx → npx -y without typing in
    // the Custom field) marks the form dirty.
    var staticFields = ['name', 'type', 'command', 'command-runtime', 'cwd', 'url',
                        'sandbox-network-allowed'];
    for (var i = 0; i < staticFields.length; i++) {
      var el = container.querySelector('[data-field="' + staticFields[i] + '"]:not(.chip-list-editor)');
      if (el && el.type === 'checkbox') {
        staticData[staticFields[i]] = !!el.checked;
      } else {
        staticData[staticFields[i]] = el ? el.value : '';
      }
    }

    var chips = { args: [], 'sandbox-writable-paths': [] };
    if (helpers && helpers.readChipListValue) {
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      if (argsHost) chips.args = helpers.readChipListValue(argsHost);
      var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      if (sandboxPathsHost) chips['sandbox-writable-paths'] = helpers.readChipListValue(sandboxPathsHost);
    }

    var kvRows = [];
    var rowEls = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row');
    for (var j = 0; j < rowEls.length; j++) {
      var row = rowEls[j];
      var keyEl = row.querySelector('.kv-key-input');
      var valueEl = row.querySelector('.kv-value-input');
      var sensEl = row.querySelector('.kv-sensitive-checkbox');
      kvRows.push({
        key: keyEl ? keyEl.value : '',
        value: valueEl ? valueEl.value : '',
        sensitive: sensEl ? !!sensEl.checked : false
      });
    }

    return JSON.stringify({ static: staticData, chips: chips, kvRows: kvRows });
  }

  // ── Event wiring ────────────────────────────────────────────────────

  function wireEditorEvents(container, source, mcpTypes, callbacks) {
    var isEdit = !!source;
    var snapshot = getFormSnapshot(container);
    var dirty = false;
    var nextRowIdx = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row').length;

    function checkDirty() {
      var current = getFormSnapshot(container);
      dirty = (current !== snapshot);
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = !dirty;
      if (cancelBtn) cancelBtn.disabled = !dirty;
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);
    }

    function recaptureSnapshot() {
      snapshot = getFormSnapshot(container);
      dirty = false;
      var saveBtn = container.querySelector('.save-btn');
      var cancelBtn = container.querySelector('.cancel-btn');
      if (saveBtn) saveBtn.disabled = true;
      if (cancelBtn) cancelBtn.disabled = true;
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
    }

    // ── Static field listeners ────────────────────────────────────────
    function attachStaticListeners() {
      var inputs = container.querySelectorAll('.editor-section .field-input:not(.kv-key-input):not(.kv-value-input), .editor-section .field-select');
      for (var i = 0; i < inputs.length; i++) {
        // Skip chip-list elements (handled via wireChipLists).
        if (inputs[i].classList.contains('chip-list-editor')) continue;
        if (inputs[i].classList.contains('chip-list-input')) continue;
        inputs[i].addEventListener('input', checkDirty);
        inputs[i].addEventListener('change', checkDirty);
      }
    }
    attachStaticListeners();

    // Chip-list onChange bridges
    wireChipLists(container, checkDirty);

    // ── Type-change handler ───────────────────────────────────────────
    var typeSelect = container.querySelector('[data-field="type"]');
    var runtimeSelect = container.querySelector('[data-field="command-runtime"]');
    if (typeSelect) {
      typeSelect.addEventListener('change', function () {
        applyTransportVisibility(container, typeSelect.value);
        // F9 L2 vibing: applyTransportVisibility blindly toggles the
        // `is-hidden` class on every `.mcp-stdio-only` row based on the
        // selected transport. The Custom-command row is also gated by
        // the runtime dropdown's state (Custom… vs canonical literal),
        // so a transport-switch into stdio would otherwise reveal the
        // Custom row even when the dropdown is on `uvx`. Re-sync here.
        if (typeSelect.value === 'stdio' && runtimeSelect) {
          applyStdioRuntimeSelection(container, runtimeSelect.value);
        }
        // checkDirty already wired via static listener above.
      });
    }

    // ── F9 L2 vibing: stdio command-runtime dropdown change handler ──
    // Toggles the Custom-command free-text row visibility + swaps the
    // helper-text under the args chip-list. checkDirty is already wired
    // via attachStaticListeners (the dropdown carries .field-select), so
    // we don't re-wire that here.
    if (runtimeSelect) {
      runtimeSelect.addEventListener('change', function () {
        applyStdioRuntimeSelection(container, runtimeSelect.value);
      });
    }

    // ── kv table delegated events ─────────────────────────────────────
    var kvTable = container.querySelector('.mcp-kv-table');
    if (kvTable) {
      // Input/keyup on key/value inputs.
      kvTable.addEventListener('input', function (e) {
        var target = e.target;
        if (!target) return;
        if (target.classList && (target.classList.contains('kv-key-input') || target.classList.contains('kv-value-input'))) {
          checkDirty();
        }
      });

      // Change on sensitive checkbox + click on remove / eye buttons.
      kvTable.addEventListener('change', function (e) {
        var target = e.target;
        if (!target) return;
        if (target.classList && target.classList.contains('kv-sensitive-checkbox')) {
          handleSensitiveToggle(target);
          checkDirty();
        }
      });

      kvTable.addEventListener('click', function (e) {
        var target = e.target;
        if (!target) return;
        // Eye toggle (button OR svg inside)
        var eyeBtn = target.closest && target.closest('.kv-eye-btn');
        if (eyeBtn) {
          var row = eyeBtn.closest('tr.mcp-kv-row');
          if (row) {
            var valueInput = row.querySelector('.kv-value-input');
            if (valueInput) {
              if (valueInput.type === 'password') {
                valueInput.type = 'text';
                eyeBtn.innerHTML = window.App.icon('eye-off');
                eyeBtn.setAttribute('aria-label', 'Hide value');
              } else {
                valueInput.type = 'password';
                eyeBtn.innerHTML = window.App.icon('eye');
                eyeBtn.setAttribute('aria-label', 'Show value');
              }
            }
          }
          return;
        }
        // Remove row
        var removeBtn = target.closest && target.closest('.kv-remove-row-btn');
        if (removeBtn) {
          var rrow = removeBtn.closest('tr.mcp-kv-row');
          if (rrow) {
            rrow.parentNode.removeChild(rrow);
            updateKvHeadVisibility(container);
            checkDirty();
          }
          return;
        }
      });
    }

    // ── Add-row button ────────────────────────────────────────────────
    var addRowBtn = container.querySelector('.kv-add-row-btn');
    if (addRowBtn) {
      addRowBtn.addEventListener('click', function () {
        var tbody = container.querySelector('.mcp-kv-table tbody');
        if (!tbody) return;
        var idx = nextRowIdx++;
        var emptyRow = { key: '', value: '', sensitive: false, _originalMasked: '' };
        var tmp = document.createElement('tbody');
        tmp.innerHTML = renderKvRow(emptyRow, idx);
        var newTr = tmp.querySelector('tr.mcp-kv-row');
        if (newTr) {
          tbody.appendChild(newTr);
          updateKvHeadVisibility(container);
          checkDirty();
        }
      });
    }

    // ── Back ──────────────────────────────────────────────────────────
    var backBtn = container.querySelector('.back-btn');
    if (backBtn && callbacks.onBack) {
      backBtn.addEventListener('click', function () { callbacks.onBack(); });
    }

    // ── Cancel ────────────────────────────────────────────────────────
    var cancelBtn = container.querySelector('.cancel-btn');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', function () {
        if (isEdit) {
          revertEditorToSource(container, source, callbacks);
          // Re-bind delegated/static listeners that depend on snapshot/dirty
          // tracking — note: kv table itself was rebuilt; the table's
          // delegated listeners are still attached to the same .mcp-kv-table
          // element (we did innerHTML on the section, NOT replaceChild on
          // the table) — but to be safe, re-acquire references.
          // Actually we replace the tbody contents in-place.
          recaptureSnapshot();
        } else if (callbacks.onCancel) {
          callbacks.onCancel();
        }
      });
    }

    // ── Save ──────────────────────────────────────────────────────────
    var saveBtn = container.querySelector('.save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', function () {
        var errorEl = container.querySelector('.editor-error');
        if (errorEl) errorEl.textContent = '';
        var payload = collectFormData(container, source, isEdit);
        if (!payload) return;
        var url = isEdit ? '/api/mcp-sources/' + encodeURIComponent(source.id) : '/api/mcp-sources';
        var method = isEdit ? 'PUT' : 'POST';
        fetch(url, {
          method: method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
          .then(function (r) {
            if (!r.ok) {
              // F9 L2 vibing: read body as text first, then try JSON. A
              // proper FastAPI error response is JSON {detail: ...}; a
              // catastrophic 5xx (handler raised before our envelope) is
              // HTML and would choke r.json() with "Unexpected token <".
              return r.text().then(function (body) {
                var detail;
                try {
                  var parsed = JSON.parse(body);
                  detail = parsed && parsed.detail;
                } catch (_) {
                  // Non-JSON body — fall through to status-based message.
                }
                if (Array.isArray(detail)) {
                  // Pydantic ValidationError shape
                  detail = detail.map(function (d) {
                    var loc = (d.loc || []).join('.');
                    return loc ? (loc + ': ' + d.msg) : d.msg;
                  }).join(' | ');
                }
                if (!detail) {
                  var snippet = (body || '').trim().slice(0, 500);
                  detail = 'Server error ' + r.status + ' ' + r.statusText +
                           (snippet ? ': ' + snippet : '');
                }
                throw new Error(detail || (isEdit ? 'Save failed' : 'Create failed'));
              });
            }
            return r.json();
          })
          .then(function (updated) {
            window.App.showFlash(container, isEdit ? 'MCP Server saved' : 'MCP Server created');
            if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated, !isEdit);
            if (isEdit) {
              // Edit→edit: refresh snapshot from the masked response so
              // subsequent typing dirties from the post-save baseline.
              snapshot = getFormSnapshot(container);
              dirty = false;
              if (saveBtn) saveBtn.disabled = true;
              var c2 = container.querySelector('.cancel-btn');
              if (c2) c2.disabled = true;
              if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
            }
          })
          .catch(function (err) {
            if (errorEl) errorEl.textContent = err.message || String(err);
          });
      });
    }

    // ── Test Connection (edit only, streamable-http only) ─────────────
    var testBtn = container.querySelector('[data-testid="mcp-test-connection"]');
    if (testBtn) {
      // F9 L1 (vibing follow-up): after a successful /test/connect (Phase A
      // ok OR Phase 2 ok after OAuth popup), refetch the source so any
      // OAuth-state-dependent UI (currently: the Reset button) reflects
      // the post-flow truth. Without this, a fresh OAuth grant via the
      // popup leaves source.oauth_active stale at the value captured on
      // editor mount, hiding the Reset button until the operator
      // reloads. Targeted DOM mutation keeps in-flight form edits intact
      // (a full re-render would clobber dirty form state).
      function onTestConnectSuccess() {
        fetch('/api/mcp-sources/' + encodeURIComponent(source.id))
          .then(function (r) { return r && r.ok ? r.json() : null; })
          .then(function (refreshed) {
            if (!refreshed) return;
            source.oauth_active = !!refreshed.oauth_active;
            syncResetButtonVisibility(container, source, mcpTypes, callbacks);
            // Squawk 0102: the refresh just rewrote config._cache server-side
            // (serverInfo, capabilities, instructions, ...) — repaint the
            // Server section from it. source.config._cache is deliberately
            // NOT overwritten in memory: hasOAuthState's cache-presence
            // fallback reads it, so syncing it would change Reset-button
            // visibility on later refreshes (outside this squawk's scope).
            syncServerInfoSection(container,
              (refreshed.config && refreshed.config._cache) || null);
          })
          .catch(function () { /* best-effort; UI stays consistent on next mount */ });
      }
      testBtn.addEventListener('click', function () {
        // F8 L4: pass a no-op error-clearer so collectFormData's
        // validation messages don't accidentally show up in the editor's
        // generic .editor-error div for the Test path; if validation
        // fails (missing name / type / url), the form data is null and
        // we fall through to the no-payload path which uses persisted
        // state — same behavior as before.
        var formData = collectFormData(container, source, true);
        // F9 L1 (vibing follow-up): the auto-run-after-create path
        // (studio.js onSaveSuccess) sets dataset.autoRun on the button
        // before dispatching click() — signal to handleTestConnection
        // that it must NOT open the OAuth popup automatically (the
        // user-gesture context from Save is no longer fresh). Cleared
        // after read so subsequent manual clicks behave normally.
        var autoRun = testBtn.dataset.autoRun === '1';
        if (autoRun) delete testBtn.dataset.autoRun;
        handleTestConnection(source.id, container, testBtn, formData,
          onTestConnectSuccess, { noAutoPopup: autoRun });
      });
    }

    // ── Delete (edit only) ────────────────────────────────────────────
    var deleteBtn = container.querySelector('.delete-btn');
    if (deleteBtn && isEdit) {
      function doDelete(btn, revertFn) {
        fetch('/api/mcp-sources/' + encodeURIComponent(source.id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error((e && e.detail) || 'Delete failed'); });
            window.App.showFlash(container, 'MCP Server deleted');
            if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
          })
          .catch(function (err) {
            revertFn();
            window.App.showFlash(container, 'Error: ' + err.message, true);
          });
      }
      deleteBtn.addEventListener('click', function () {
        // L6: NO agent-usage pre-gate (F4 lands per-agent attachments).
        // Bare confirmDelete two-step.
        window.App.confirmDelete(deleteBtn, doDelete, { confirmLabel: 'Confirm Delete?' });
      });
    }

    // ── Reset connection (edit only, streamable-http with OAuth state) ─
    // F9 L1 (vibing): clears tokens + DCR + tools cache server-side and
    // re-renders the editor from the response shape so the Tools section
    // collapses to empty-state and the button itself hides (no more
    // OAuth state to reset). On error, surfaces via showFlash.
    if (isEdit) {
      wireResetButton(container, source, mcpTypes, callbacks);
    }
  }

  // F9 L1 (vibing follow-up): wire the Reset connection button's click
  // handler. Extracted from inline wireEditorEvents so it can also fire
  // after dynamic injection (post-OAuth-grant), where the original
  // wireEditorEvents pass already ran without finding the button in the
  // DOM. Idempotent: skips wiring if a marker dataset is already set on
  // the button (re-runs from syncResetButtonVisibility are no-ops on
  // already-wired buttons).
  function wireResetButton(container, source, mcpTypes, callbacks) {
    var resetBtn = container.querySelector('[data-testid="reset-mcp-connection-btn"]');
    if (!resetBtn) return;
    if (resetBtn.dataset.resetWired === '1') return;
    resetBtn.dataset.resetWired = '1';
    function doReset(btn, revertFn) {
      fetch('/api/mcp-sources/' + encodeURIComponent(source.id) + '/connection', { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) return r.json().then(function (e) { throw new Error((e && e.detail) || 'Reset failed'); });
          return fetch('/api/mcp-sources/' + encodeURIComponent(source.id));
        })
        .then(function (r) {
          if (!r || !r.ok) throw new Error('Failed to refetch source after reset');
          return r.json();
        })
        .then(function (refreshed) {
          // Re-render from the refreshed source. The Tools section
          // collapses to empty-state (no _cache); the Reset button
          // hides itself (no more OAuth state); the kv-table rebuilds
          // (OAuth-managed keys were stripped from the response anyway,
          // so the visible kv shape is unchanged for non-OAuth secrets).
          renderMcpSourceEditor(container, refreshed, mcpTypes, callbacks);
          window.App.showFlash(container, 'Connection reset');
        })
        .catch(function (err) {
          revertFn();
          window.App.showFlash(container, 'Error: ' + err.message, true);
        });
    }
    resetBtn.addEventListener('click', function () {
      window.App.confirmDelete(resetBtn, doReset, { confirmLabel: 'Confirm Reset?' });
    });
  }

  // F9 L1 (vibing follow-up): inject or remove the Reset connection button
  // based on the source's current OAuth-state. Called after a successful
  // /test/connect refetch reveals oauth_active changed (e.g., after a
  // fresh OAuth grant via the popup). Targeted DOM mutation — does NOT
  // re-render the editor (would clobber in-flight form edits).
  function syncResetButtonVisibility(container, source, mcpTypes, callbacks) {
    var escapeAttr = window.App.escapeAttr;
    var actionsHost = container.querySelector('.mcp-connection-actions');
    if (!actionsHost) return;
    var existing = actionsHost.querySelector('[data-testid="reset-mcp-connection-btn"]');
    if (hasOAuthState(source)) {
      if (existing) return; // already present
      var resetTooltip = 'Reset this connection? This clears the stored login and tools list. ' +
        'You will need to log in again on the next refresh.';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-outlined-primary mcp-reset-connection-btn';
      btn.setAttribute('data-testid', 'reset-mcp-connection-btn');
      btn.setAttribute('title', resetTooltip);
      btn.setAttribute('aria-label', resetTooltip);
      btn.setAttribute('data-name', source.name || '');
      btn.innerHTML = '<span data-confirm-title>Reset connection</span>';
      // escapeAttr is used in the static-render path; for dynamic creation
      // the DOM API handles attribute encoding, so escapeAttr is unused
      // here. The reference is kept to mirror the static path's import.
      void escapeAttr;
      // Insert before the "Last updated" label (if present) so the label
      // stays the trailing element with `margin-left: auto`. Falls back
      // to appendChild when no label sibling exists yet.
      var luSibling = actionsHost.querySelector('[data-testid="mcp-tools-last-updated"]');
      if (luSibling) {
        actionsHost.insertBefore(btn, luSibling);
      } else {
        actionsHost.appendChild(btn);
      }
      wireResetButton(container, source, mcpTypes, callbacks);
    } else if (existing) {
      existing.parentNode.removeChild(existing);
    }
  }

  // ── KV table head visibility (F9 L1) ────────────────────────────────
  // The thead is hidden when the table has zero rows (empty-state UX) and
  // revealed once the operator adds the first row. Toggled in three call
  // sites: add-row click, remove-row click, and cancel-revert (where the
  // tbody is rebuilt from the source object).

  function updateKvHeadVisibility(container) {
    var thead = container.querySelector('.mcp-kv-thead');
    if (!thead) return;
    var rowCount = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row').length;
    thead.classList.toggle('is-hidden', rowCount === 0);
  }

  // ── Sensitive toggle helpers ────────────────────────────────────────

  function handleSensitiveToggle(checkbox) {
    /* Toggle the value input's type between password/text + render or
       remove the eye-toggle. Critical: when unchecking sensitive on a
       row whose value still equals _originalMasked, clear the value
       field — otherwise the masked tail leaks into plaintext on save. */
    var row = checkbox.closest('tr.mcp-kv-row');
    if (!row) return;
    var valueInput = row.querySelector('.kv-value-input');
    var wrap = row.querySelector('.api-key-wrap');
    if (!valueInput || !wrap) return;

    if (checkbox.checked) {
      // → sensitive
      valueInput.type = 'password';
      valueInput.classList.add('kv-value-secret');
      // Add eye button if missing.
      if (!wrap.querySelector('.kv-eye-btn')) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'api-key-eye kv-eye-btn';
        btn.setAttribute('data-row', valueInput.dataset.row || '');
        btn.setAttribute('aria-label', 'Show value');
        btn.innerHTML = window.App.icon('eye');
        wrap.appendChild(btn);
      }
    } else {
      // → plaintext
      var origMasked = valueInput.dataset.originalMasked || '';
      if (origMasked && valueInput.value === origMasked) {
        // Clear the masked tail so it doesn't leak into config.env / config.headers.
        valueInput.value = '';
      }
      valueInput.type = 'text';
      valueInput.classList.remove('kv-value-secret');
      var eye = wrap.querySelector('.kv-eye-btn');
      if (eye) eye.parentNode.removeChild(eye);
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

  // ── Cancel-revert: rebuild kv-table + chip-lists from source ────────

  function revertEditorToSource(container, source, callbacks) {
    /* In edit mode, revert the form to the source object. Static fields
       restore via a value-loop; the kv-table rebuilds from source (its
       row count can change during edit); chip-list editors re-mount
       fresh. */
    if (!source) return;

    // 1. Static fields
    // F9 L2 vibing: derive the command-runtime dropdown value + the
    // free-text Custom… field's value from the saved (command, args)
    // pair. `command` (free-text) is only populated when the saved
    // command falls into Custom… — for the canonical runtimes the
    // Custom row is hidden and its value is empty.
    var savedCmd = (source.config && source.config.command) || '';
    var savedArgs = (source.config && source.config.args) || [];
    var sel = deriveStdioRuntimeSelection(savedCmd, savedArgs);
    var staticMap = {
      'name': source.name || '',
      'type': source.type || '',
      'command-runtime': sel.dropdownValue || '',
      'command': sel.customCommand || '',
      'cwd': (source.config && source.config.cwd) || '',
      'url': (source.config && source.config.url) || ''
    };
    Object.keys(staticMap).forEach(function (key) {
      var el = container.querySelector('[data-field="' + key + '"]:not(.chip-list-editor)');
      if (el) el.value = staticMap[key];
    });
    // Sync the Custom-row visibility + helper-text to the restored
    // dropdown selection.
    applyStdioRuntimeSelection(container, sel.dropdownValue || '');
    // F3 L5b: sandbox-network-allowed is a checkbox — its display state
    // is controlled by .checked, not .value. Pulled out of the loop above
    // so el.value = ... doesn't no-op the visible checked state.
    var sandboxNetEl = container.querySelector('[data-field="sandbox-network-allowed"]:not(.chip-list-editor)');
    if (sandboxNetEl) {
      sandboxNetEl.checked = !!(source.config && source.config.sandbox && source.config.sandbox.network_allowed === true);
    }

    // 2. Visibility
    applyTransportVisibility(container, source.type || '');

    // 3. KV table — rebuild tbody contents
    var tbody = container.querySelector('.mcp-kv-table tbody');
    if (tbody) {
      var rows = collectExistingKvRows(source, source.type || '');
      var html = '';
      for (var i = 0; i < rows.length; i++) {
        html += renderKvRow(rows[i], i);
      }
      tbody.innerHTML = html;
      updateKvHeadVisibility(container);
    }

    // 4. Chip-list editors — re-mount fresh
    var helpers = window.App.adminFormHelpers;
    if (helpers && helpers.renderChipListEditor) {
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      if (argsHost && argsHost.parentNode) {
        var wrapper = document.createElement('div');
        // F9 L2 vibing: use sel.displayArgs so the operator's chip-list
        // shows only their own args — the implicit `-y` for `npx -y` and
        // the implicit `run` for `pipx run` (option (b) split) stay in
        // the saved JSON but never surface as editable chips the
        // operator could accidentally remove.
        wrapper.innerHTML = helpers.renderChipListEditor('args', sel.displayArgs || [], null, { controlId: 'mf-args' });
        var newArgs = wrapper.firstChild;
        argsHost.parentNode.replaceChild(newArgs, argsHost);
        if (helpers.wireChipListEditor) {
          helpers.wireChipListEditor(newArgs, function () {
            // Note: this onChange fires before we have a recaptured snapshot;
            // the orchestrator's wireEditorEvents runs once per render and
            // captures dirty-tracking via its own checkDirty closure. After
            // a Cancel revert, we recaptureSnapshot externally.
          });
        }
      }
      // F3 L5b: sandbox writable_paths chip-list re-mount.
      var sandboxPathsHost = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      if (sandboxPathsHost && sandboxPathsHost.parentNode) {
        var wrapper3 = document.createElement('div');
        wrapper3.innerHTML = helpers.renderChipListEditor('sandbox-writable-paths',
          (source.config && source.config.sandbox && source.config.sandbox.writable_paths) || [],
          null, { controlId: 'mf-sandbox-writable-paths' });
        var newSandboxPaths = wrapper3.firstChild;
        sandboxPathsHost.parentNode.replaceChild(newSandboxPaths, sandboxPathsHost);
        if (helpers.wireChipListEditor) {
          helpers.wireChipListEditor(newSandboxPaths, function () { /* dirty-tracking handled externally */ });
        }
      }
    }
  }

  // ── Payload assembly ────────────────────────────────────────────────

  function collectFormData(container, source, isEdit) {
    /* Routes by `type` (NOT by visible-field set). A type-change
       immediately followed by Save emits the type-correct payload. */
    var errorEl = container.querySelector('.editor-error');
    var nameEl = container.querySelector('[data-field="name"]');
    var name = nameEl ? nameEl.value.trim() : '';
    if (!name) {
      if (errorEl) errorEl.textContent = 'Name is required.';
      return null;
    }
    var typeEl = container.querySelector('[data-field="type"]');
    var type = typeEl ? typeEl.value : '';
    if (!type) {
      if (errorEl) errorEl.textContent = 'Type is required.';
      return null;
    }

    var config = {};
    var secrets = {};

    if (type === 'stdio') {
      // F9 L2 vibing: command source is the dropdown selection. For all
      // canonical runtime literals except `npx -y` and `pipx run` the
      // dropdown value IS `config.command` verbatim. For `npx -y` we
      // split into `command=npx, args=[-y, ...userArgs]`; for `pipx run`
      // we split into `command=pipx, args=[run, ...userArgs]` (option
      // (b)) so the saved JSON stays transparent — and so the spawn
      // layer doesn't try to exec a 2-token string as a single binary
      // and FileNotFoundError. For Custom… the free-text input feeds
      // `config.command` directly (operator owns resolution).
      var runtimeEl = container.querySelector('[data-field="command-runtime"]');
      var runtimeValue = runtimeEl ? runtimeEl.value : '';
      var command = '';
      var prependArgs = [];
      if (runtimeValue === STDIO_CUSTOM_SENTINEL) {
        var customEl = container.querySelector('[data-field="command"]');
        command = customEl ? customEl.value.trim() : '';
      } else if (runtimeValue === 'npx -y') {
        command = 'npx';
        prependArgs = ['-y'];
      } else if (runtimeValue === 'pipx run') {
        command = 'pipx';
        prependArgs = ['run'];
      } else if (runtimeValue) {
        command = runtimeValue;
      }
      if (!command) {
        if (errorEl) errorEl.textContent = 'Command is required for stdio servers.';
        return null;
      }
      config.command = command;
      var cwdEl = container.querySelector('[data-field="cwd"]');
      var cwd = cwdEl ? cwdEl.value.trim() : '';
      if (cwd) config.cwd = cwd;
      var argsHost = container.querySelector('[data-field="args"].chip-list-editor');
      var helpers = window.App.adminFormHelpers;
      var userArgsList = (argsHost && helpers && helpers.readChipListValue) ? helpers.readChipListValue(argsHost) : [];
      var argsList = prependArgs.concat(userArgsList);
      if (argsList.length > 0) config.args = argsList;
      config.env = {};
      partitionKvRows(container, config.env, secrets);
      // F3 L5b: sandbox profile (stdio only). Always-emit precedent
      // matches config.env above: empty defaults are written explicitly,
      // not omitted. The L1b API validator accepts the default shape.
      var sandboxNetEl = container.querySelector('[data-field="sandbox-network-allowed"]');
      var networkAllowed = !!(sandboxNetEl && sandboxNetEl.checked);
      var sandboxPathsList = container.querySelector('[data-field="sandbox-writable-paths"].chip-list-editor');
      var writablePaths = (sandboxPathsList && helpers && helpers.readChipListValue) ? helpers.readChipListValue(sandboxPathsList) : [];
      config.sandbox = { network_allowed: networkAllowed, writable_paths: writablePaths };
    } else if (type === 'streamable-http') {
      var urlEl = container.querySelector('[data-field="url"]');
      var urlValue = urlEl ? urlEl.value.trim() : '';
      if (!urlValue) {
        if (errorEl) errorEl.textContent = 'URL is required for streamable-http servers.';
        return null;
      }
      config.url = urlValue;
      config.headers = {};
      partitionKvRows(container, config.headers, secrets);
    } else {
      if (errorEl) errorEl.textContent = 'Unsupported transport type: ' + type;
      return null;
    }

    return { name: name, type: type, config: config, secrets: secrets };
  }

  function partitionKvRows(container, plaintextDict, secretsDict) {
    var rows = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row');
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var keyEl = row.querySelector('.kv-key-input');
      var valueEl = row.querySelector('.kv-value-input');
      var sensEl = row.querySelector('.kv-sensitive-checkbox');
      if (!keyEl || !valueEl) continue;
      var key = (keyEl.value || '').trim();
      if (!key) continue; // empty key → silently skip
      var value = valueEl.value || '';
      var sensitive = !!(sensEl && sensEl.checked);
      var origMasked = valueEl.dataset.originalMasked || '';
      if (sensitive) {
        if (origMasked && value === origMasked) {
          // Per-row MASKED_SENTINEL — preserves stored secret backend-side.
          secretsDict[key] = MASKED_SENTINEL;
        } else {
          secretsDict[key] = value;
        }
      } else {
        plaintextDict[key] = value;
      }
    }
  }

  // ── Test Connection handler ─────────────────────────────────────────
  // Promise-chain style ONLY — the entire file uses .then().catch() with
  // zero async/await. Diverging would create a stylistic outlier and may
  // not transpile if the build pipeline targets ES5.

  function handleTestConnection(sourceId, container, testBtn, formData, onSuccess, opts) {
    var escapeHtml = window.App.escapeHtml;
    var statusEl = container.querySelector('[data-testid="mcp-test-status"]');
    var listEl = container.querySelector('[data-testid="mcp-tools-list"]');
    // F9 L1 (vibing follow-up): opts.noAutoPopup suppresses the
    // window.open() call on auth_required and instead renders an
    // explicit "Sign in" consent button into the status panel. Used by
    // the auto-run-after-create path (studio.js onSaveSuccess), where
    // the original Save click's user-gesture context is lost by the
    // time the create POST resolves and Phase A surfaces auth_required —
    // popup-blockers reject popups not triggered by direct interaction.
    // Default false preserves the manual-Refresh-click behavior verbatim.
    var noAutoPopup = !!(opts && opts.noAutoPopup);
    statusEl.textContent = 'Testing connection…';
    statusEl.hidden = false;
    listEl.hidden = true;
    listEl.innerHTML = '';
    testBtn.disabled = true; // concurrent-Test guard: re-enabled only on final state

    function settle() {
      testBtn.disabled = false; // re-enable on final state
    }

    // F9 L1 (vibing follow-up) + F4 L3 popup-loop fix: popup-launch +
    // close-watcher extracted so both the auto-popup branch (manual
    // click) and the explicit "Sign in" consent-button branch (auto-run
    // after create) share one implementation. `consentUrl` is the
    // auth_required response's URL.
    //
    // Close-watcher contract (F4 L3 — fix the Cloudflare-class popup
    // loop): the backend's /api/oauth/callback page posts a result
    // message to `window.opener` BEFORE closing. The watcher branches
    // on the received result rather than blindly re-POSTing /test/connect:
    //   - 'success' → defensive re-POST with noAutoPopup=true. Phase A
    //     should now succeed; if the token-exchange race wins we'd loop
    //     forever without noAutoPopup, so we set it as a guard.
    //   - 'failed' / 'expired' → render error + "Sign in" retry button.
    //     The IdP's error_description is surfaced so the operator can
    //     diagnose. NO re-POST.
    //   - no message received (user cancelled the popup before OAuth
    //     resolved, or browser blocked the postMessage) → render
    //     "Sign-in did not complete" + retry button. NO re-POST.
    function launchConsentPopup(consentUrl) {
      statusEl.textContent = 'Opening consent popup…';
      var popupW = 600;
      var popupH = 700;
      var parentX = window.screenX !== undefined ? window.screenX : window.screenLeft;
      var parentY = window.screenY !== undefined ? window.screenY : window.screenTop;
      var parentW = window.outerWidth || window.innerWidth || screen.width;
      var parentH = window.outerHeight || window.innerHeight || screen.height;
      var popupLeft = parentX + Math.max(0, (parentW - popupW) / 2);
      var popupTop = parentY + Math.max(0, (parentH - popupH) / 2);
      var features = (
        'width=' + popupW + ',height=' + popupH +
        ',left=' + Math.round(popupLeft) +
        ',top=' + Math.round(popupTop)
      );
      var popup = window.open(consentUrl, 'mcp-oauth-consent', features);
      if (!popup) {
        statusEl.textContent = 'Popup blocked — please allow popups and retry.';
        settle();
        return;
      }
      // F4 L3 — postMessage-independent polling. Earlier iterations
      // gated polling on a `success` postMessage from /oauth/callback,
      // but Cloudflare's OAuth page sets COOP (or similar) which severs
      // `window.opener` across the cross-origin navigation chain. By
      // the time the popup is back on loopback, opener is null and the
      // postMessage silently no-ops — polling never starts, popup
      // closes, UI shows "did not complete" even though OAuth succeeded.
      //
      // Decoupled design: poll `GET /api/mcp-sources/{id}` for
      // `has_access_token: true` from popup-open. Polling is the source
      // of truth for success. postMessage demotes to a fast-fail signal
      // for failed/expired (short-circuits the wait to give the
      // operator the IdP's error text immediately).
      //
      // States:
      //   POLLING — popup open or recently closed; checking for tokens.
      //   DONE    — final action taken (re-POST or retry-UI). Idempotent.
      //
      // Popup-close handling: when popup.closed flips, we don't bail
      // immediately — give a short grace window (a few more polls) in
      // case tokens are still landing. If polling still misses, render
      // retry. If user cancelled, polling never finds tokens and falls
      // through to retry after the grace window.
      var state = 'POLLING';
      var pollTimer = null;
      var pollAttempts = 0;
      var maxPollAttempts = 30; // 30 × 500ms = 15s overall ceiling
      var graceAfterClose = 6; // 3s extra polls after popup-close
      var attemptsCapAfterClose = null; // set on close; bails when reached

      function cleanup() {
        if (pollTimer) clearInterval(pollTimer);
        window.removeEventListener('message', onOAuthMessage);
      }

      function finalize(action) {
        if (state === 'DONE') return;
        state = 'DONE';
        cleanup();
        action();
      }

      function renderRetryUi(headerText) {
        statusEl.innerHTML = '';
        var msg = document.createElement('span');
        msg.className = 'mcp-tools-error';
        msg.textContent = headerText + ' ';
        statusEl.appendChild(msg);
        var retryBtn = document.createElement('button');
        retryBtn.type = 'button';
        retryBtn.className = 'btn-outlined-primary';
        retryBtn.setAttribute('data-testid', 'mcp-consent-btn');
        retryBtn.textContent = 'Sign in';
        retryBtn.addEventListener('click', function () {
          launchConsentPopup(consentUrl);
        });
        statusEl.appendChild(retryBtn);
      }

      function onOAuthMessage(evt) {
        if (state === 'DONE') return;
        if (evt.origin !== window.location.origin) return;
        var d = evt.data;
        if (!d || typeof d !== 'object') return;
        if (d.type !== 'mcp-oauth-result') return;
        // success status is informational only — polling owns that
        // transition. failed/expired short-circuit to retry so the
        // operator sees the IdP's error without waiting out the poll.
        if (d.status === 'failed') {
          var failMsg = d.description || d.error || 'sign-in failed';
          finalize(function () {
            if (!popup.closed) { try { popup.close(); } catch (e) { /* */ } }
            renderRetryUi('✗ Sign-in failed: ' + failMsg + '.');
            settle();
          });
        } else if (d.status === 'expired') {
          finalize(function () {
            if (!popup.closed) { try { popup.close(); } catch (e) { /* */ } }
            renderRetryUi('✗ Sign-in window expired.');
            settle();
          });
        }
      }
      window.addEventListener('message', onOAuthMessage);

      statusEl.textContent = 'Awaiting sign-in…';

      pollTimer = setInterval(function () {
        if (state === 'DONE') return;

        // Track popup-close transition (first observation only).
        var popupNowClosed = popup.closed;
        if (popupNowClosed && attemptsCapAfterClose === null) {
          attemptsCapAfterClose = pollAttempts + graceAfterClose;
          statusEl.textContent = 'Finalizing sign-in…';
        }

        pollAttempts++;

        fetch('/api/mcp-sources/' + encodeURIComponent(sourceId))
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (src) {
            if (state === 'DONE') return;
            if (src && src.has_access_token === true) {
              finalize(function () {
                if (!popup.closed) { try { popup.close(); } catch (e) { /* */ } }
                // Phase A re-POST. noAutoPopup defensive — if something
                // weird leaves Phase A still failing, retry UI surfaces
                // instead of looping.
                handleTestConnection(sourceId, container, testBtn, formData, onSuccess, { noAutoPopup: true });
              });
              return;
            }
            var hitOverallCap = pollAttempts >= maxPollAttempts;
            var hitGraceCap = attemptsCapAfterClose !== null && pollAttempts >= attemptsCapAfterClose;
            if (hitOverallCap || hitGraceCap) {
              finalize(function () {
                var label;
                if (hitGraceCap && !hitOverallCap) {
                  // Popup closed without tokens landing in the grace
                  // window — likely manual cancel or IdP rejection
                  // whose postMessage didn't reach us (cross-origin
                  // opener severed).
                  label = 'Sign-in did not complete.';
                } else {
                  label = 'Sign-in timed out — tokens did not persist within '
                    + (maxPollAttempts / 2) + 's.';
                }
                renderRetryUi(label);
                settle();
              });
            }
          })
          .catch(function () { /* transient fetch error; next tick retries */ });
      }, 500);
    }

    // F8 L4: send the operator's in-flight form values so Test connection
    // tests what's in the field, not what's in the DB. Backend mirrors PUT's
    // secrets-resolution (per-key __MASKED__ + OAuth-managed-key preservation).
    // Empty body falls back to persisted state — preserves the prior contract.
    var fetchOpts = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    };
    if (formData) {
      fetchOpts.body = JSON.stringify({
        type: formData.type,
        config: formData.config || {},
        secrets: formData.secrets || {},
      });
    }
    fetch('/api/mcp-sources/' + encodeURIComponent(sourceId) + '/test/connect', fetchOpts)
      .then(function (resp) {
        // F9 L2 vibing: defense-in-depth against non-JSON 500s. The backend
        // helpers now ship a catch-all envelope that converts unexpected
        // exceptions into 200 {status: "error"}, but if anything escapes
        // (FastAPI itself raising before our handler, an upstream proxy
        // returning HTML, etc.) we'd choke on resp.json() with "Unexpected
        // token <" and surface a useless message. Read the body as text on
        // !ok so the .catch handler renders something actionable.
        if (resp.ok) return resp.json();
        return resp.text().then(function (body) {
          var snippet = (body || '').trim().slice(0, 500);
          var err = new Error('Server error ' + resp.status + ' ' + resp.statusText +
                              (snippet ? ': ' + snippet : ''));
          err.serverStatus = resp.status;
          throw err;
        });
      })
      .then(function (data) {
        if (data.status === 'ok') {
          // Render summary + collapsible tool list. Cloudflare-class servers
          // ship verbose multi-paragraph descriptions; <details> keeps the
          // section scannable while preserving full content.
          // F8 L2: append capability-flags one-liner after the tools count.
          // F4 L7 (M08): LED moved up to the connection-actions row; the
          // status banner here keeps only the tool-count line. Update both
          // sites so the new LED reflects the post-/test/connect success.
          statusEl.innerHTML = (
            'Server exposes <strong>' + data.tools.length + '</strong> tool' +
            (data.tools.length === 1 ? '' : 's') + '.'
          );
          var ledEl = container.querySelector('[data-testid="mcp-connection-led"]');
          if (ledEl) {
            ledEl.className = 'indicator-led indicator-led--success';
            ledEl.setAttribute('data-state', 'success');
            ledEl.setAttribute('aria-label', 'Connected');
          }
          listEl.innerHTML = renderToolsListHtml(data.tools);
          listEl.hidden = false;
          // F9 L1 (vibing): backend just persisted last_updated to ~now;
          // mirror that locally so the displayed timestamp updates
          // immediately (the operator doesn't have to reload to see
          // "just now"). The exact server-side time is close enough.
          var luEl = container.querySelector('[data-testid="mcp-tools-last-updated"]');
          if (luEl) {
            luEl.textContent = 'Last updated: just now';
            luEl.hidden = false;
          }
          // F9 L1 (vibing follow-up): caller-supplied hook fires after
          // any successful /test/connect (Phase A or Phase 2). Used to
          // refetch source state for OAuth-state-dependent UI (Reset
          // button visibility) — see callsite in wireEditorEvents.
          if (typeof onSuccess === 'function') {
            try { onSuccess(); } catch (e) { /* swallow */ }
          }
          settle();
        } else if (data.status === 'auth_required') {
          if (noAutoPopup) {
            // Auto-run-after-create path: render an explicit "Sign in"
            // consent button instead of opening the popup directly.
            // Direct user-click on this button restores the gesture
            // context required for window.open() to bypass popup
            // blockers. The button is wired one-shot — clicking it
            // invokes launchConsentPopup() which opens the popup AND
            // wires the close-watcher → Phase 2 re-POST.
            statusEl.innerHTML = '';
            var prompt = document.createElement('span');
            prompt.textContent = 'This server requires authorization. ';
            statusEl.appendChild(prompt);
            var consentBtn = document.createElement('button');
            consentBtn.type = 'button';
            consentBtn.className = 'btn-outlined-primary';
            consentBtn.setAttribute('data-testid', 'mcp-consent-btn');
            consentBtn.textContent = 'Sign in';
            consentBtn.addEventListener('click', function () {
              launchConsentPopup(data.consent_url);
            });
            statusEl.appendChild(consentBtn);
            // Re-enable Refresh button so the operator can also retry
            // from there if they prefer; the consent button is the
            // primary affordance.
            settle();
          } else {
            // Manual-click path: the original Refresh click IS the user
            // gesture; open the popup immediately. Keep button disabled
            // across the popup-flow — re-enabled when Phase 2 re-POST
            // settles (in this same function).
            launchConsentPopup(data.consent_url);
          }
        } else {
          statusEl.innerHTML = '<span class="mcp-tools-error">✗ Error:</span> ' + escapeHtml(data.error || 'unknown');
          settle();
        }
      })
      .catch(function (err) {
        statusEl.innerHTML = '<span class="mcp-tools-error">✗ Network error:</span> ' + escapeHtml(err.message);
        settle();
      });
  }

  window.App.studio.renderMcpSourceEditor = renderMcpSourceEditor;
})();
