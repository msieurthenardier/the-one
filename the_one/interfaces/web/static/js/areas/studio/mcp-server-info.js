// App.studio.mcpEditor.serverInfo — the MCP source editor's Server section and
// tools-list markup (M31 F5 L02, split out of mcp-server-editor.js, moved
// verbatim).
//
// Holds: renderToolsListHtml (the collapsible per-tool list), renderCapabilityFlags,
// renderServerInfoSection (identity, protocol version, instructions, capabilities,
// _meta), cacheHasServerInfo and syncServerInfoSection (the in-place repaint
// after a Refresh). String builders plus one targeted DOM repaint.
// Exposes: renderToolsListHtml, renderCapabilityFlags, renderServerInfoSection,
// cacheHasServerInfo, syncServerInfoSection.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var SPEC_CAPABILITY_KEYS = window.App.studio.mcpEditor.shared.SPEC_CAPABILITY_KEYS;

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

  window.App.studio.mcpEditor.serverInfo = {
    renderToolsListHtml: renderToolsListHtml,
    renderCapabilityFlags: renderCapabilityFlags,
    renderServerInfoSection: renderServerInfoSection,
    cacheHasServerInfo: cacheHasServerInfo,
    syncServerInfoSection: syncServerInfoSection
  };
})();
