// App.studio.mcpEditor.serverInfo — the MCP source editor's Server section and Tools
// list, DOM-built on the control library and updated in place (M31 F5 L09).
//
// create({cache}) builds, once per mount, two sections and returns
// {serverEl, toolsEl, update, setTools, destroy}:
//   serverEl  App.ui.section "Server" (testid mcp-server-info-section), hidden while the
//             cache has nothing to show: an identity row (icon, title, name subtitle),
//             App.ui.facts (Version, Protocol, Offers, Website, only the rows with a
//             value), a warning note (testid mcp-server-protocol-fallback) shown only when
//             the cache has a Protocol and protocol_fallback is "no_answer" (the connection
//             fell back to an older protocol for lack of an answer), an Instructions
//             disclosure and a Metadata disclosure holding a
//             code block.
//   toolsEl   App.ui.section "Tools" (testid mcp-tools-section) holding the empty hint
//             and [data-testid=mcp-tools-list], one bordered disclosure per tool.
// update(cache) repaints the Server section in place (squawk 0102); setTools(tools|null)
// reconciles the tool list by name, so an open tool panel stays open across a Test that
// returns the same tools (null = no tools loaded: the hint shows).
//
// Everything the server supplied (titles, versions, instructions, tool names and
// descriptions, schemas, URLs) is untrusted: it is set with textContent only, and the
// icon and website URLs go through App.safeUrl, which fails closed (squawk 0010): a
// rejected icon is not rendered, a rejected website is inert text.
// Exposes: create, cacheHasServerInfo.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var SPEC_CAPABILITY_KEYS = window.App.studio.mcpEditor.shared.SPEC_CAPABILITY_KEYS;
  var DESC_CUT = 100;

  // Mount-time gate for the Server section.
  function cacheHasServerInfo(cache) {
    return !!(cache && (cache.server_info || cache.instructions ||
      cache.capabilities || cache.meta || cache.protocol_version));
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function capitalise(word) {
    return word.charAt(0).toUpperCase() + word.slice(1);
  }

  // The fields of the Server section, read defensively: all are spec-optional.
  function readInfo(cache) {
    cache = cache || {};
    var info = cache.server_info || {};
    var icons = Array.isArray(info.icons) ? info.icons : [];
    var meta = cache.meta && typeof cache.meta === 'object' && Object.keys(cache.meta).length > 0
      ? cache.meta : null;
    return {
      title: info.title || info.name || '',
      subtitle: (info.title && info.name && info.title !== info.name) ? info.name : '',
      version: info.version || '',
      website: info.websiteUrl || '',
      iconSrc: (icons[0] && icons[0].src) ? icons[0].src : '',
      protocol: cache.protocol_version || '',
      fallback: cache.protocol_fallback === 'no_answer',
      instructions: cache.instructions || '',
      capabilities: cache.capabilities || null,
      meta: meta
    };
  }

  function hasContent(f) {
    return !!(f.title || f.version || f.website || f.iconSrc || f.protocol ||
      f.instructions || f.capabilities || f.meta);
  }

  function offersText(capabilities) {
    var present = SPEC_CAPABILITY_KEYS.filter(function (k) {
      var v = capabilities[k];
      return v !== null && v !== undefined;
    });
    return present.length ? present.map(capitalise).join(', ') : 'Nothing announced';
  }

  function create(opts) {
    var destroyed = false;

    // ── The Server section ────────────────────────────────────────────

    var server = App.ui.section({
      title: 'Server', layout: 'stack', testid: 'mcp-server-info-section'
    });
    server.el.hidden = true;

    var identityEl = el('div', 'mcp-info-identity');
    identityEl.setAttribute('data-testid', 'mcp-server-header');
    var iconEl = null;
    var textEl = el('div', 'mcp-info-identity-text');
    var titleEl = el('div', 'mcp-info-title');
    titleEl.setAttribute('data-testid', 'mcp-server-title');
    var subtitleEl = el('div', 'mcp-info-subtitle');
    subtitleEl.setAttribute('data-testid', 'mcp-server-subtitle');
    textEl.appendChild(titleEl);
    textEl.appendChild(subtitleEl);
    identityEl.appendChild(textEl);

    var facts = App.ui.facts({ testid: 'mcp-server-facts' });

    var insBody = el('div', 'mcp-info-instructions');
    insBody.setAttribute('data-testid', 'mcp-server-instructions-text');
    var instructions = App.ui.disclosure({
      variant: 'plain', summary: 'Instructions', testid: 'mcp-server-instructions'
    });
    instructions.body.appendChild(insBody);
    instructions.el.hidden = true;

    var metaBlock = App.ui.codeBlock({
      label: 'Metadata', maxHeight: 'short', testid: 'mcp-server-meta-content'
    });
    var meta = App.ui.disclosure({
      variant: 'plain', summary: 'Metadata', testid: 'mcp-server-meta',
      onToggle: function (open) { if (open) metaBlock.refresh(); }
    });
    meta.body.appendChild(metaBlock.el);
    meta.el.hidden = true;

    server.body.appendChild(identityEl);
    // Shown when the stored record says the connection fell back to an older protocol
    // for lack of an answer (sortie 19); the section's own hidden state covers the rest.
    var fallbackNote = App.ui.banner({
      tone: 'warning', role: 'note', hidden: true, testid: 'mcp-server-protocol-fallback',
      text: 'This server did not answer the newer-protocol check in time, so this ' +
        'connection uses an older protocol and may offer fewer tools. Press Test again ' +
        'once the server has started.'
    });

    server.body.appendChild(facts.el);
    server.body.appendChild(fallbackNote.el);
    server.body.appendChild(instructions.el);
    server.body.appendChild(meta.el);

    // The icon is the server's own: an https image, or nothing.
    function syncIcon(src) {
      var safe = src ? App.safeUrl(src) : null;
      if (!safe) {
        if (iconEl) { iconEl.remove(); iconEl = null; }
        return;
      }
      if (!iconEl) {
        iconEl = document.createElement('img');
        iconEl.className = 'mcp-info-icon';
        iconEl.setAttribute('alt', '');
        iconEl.setAttribute('loading', 'lazy');
        iconEl.setAttribute('decoding', 'async');
        iconEl.setAttribute('data-testid', 'mcp-server-icon');
        identityEl.insertBefore(iconEl, textEl);
      }
      if (iconEl.getAttribute('src') !== safe) iconEl.setAttribute('src', safe);
    }

    function websiteValue(url) {
      var safe = App.safeUrl(url);
      if (!safe) return document.createTextNode(url); // inert: what the server claimed
      var a = document.createElement('a');
      a.setAttribute('href', safe);
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener noreferrer');
      a.textContent = url;
      return a;
    }

    function update(cache) {
      if (destroyed) return;
      var f = readInfo(cache);
      if (!hasContent(f)) {
        server.el.hidden = true;
        return;
      }
      server.el.hidden = false;

      syncIcon(f.iconSrc);
      titleEl.textContent = f.title;
      titleEl.hidden = !f.title;
      subtitleEl.textContent = f.subtitle;
      subtitleEl.hidden = !f.subtitle;
      identityEl.hidden = !f.title && !iconEl;

      var rows = [];
      if (f.version) {
        rows.push({ label: 'Version', value: f.version, testid: 'mcp-server-version' });
      }
      if (f.protocol) {
        rows.push({
          label: 'Protocol', value: f.protocol, mono: true, testid: 'mcp-server-protocol'
        });
      }
      if (f.capabilities) {
        rows.push({
          label: 'Offers', value: offersText(f.capabilities), testid: 'mcp-server-offers'
        });
      }
      if (f.website) {
        rows.push({
          label: 'Website', value: websiteValue(f.website), testid: 'mcp-server-website'
        });
      }
      facts.set(rows);
      facts.el.hidden = rows.length === 0;

      if (f.protocol && f.fallback) fallbackNote.show();
      else fallbackNote.hide();

      insBody.textContent = f.instructions;
      instructions.el.hidden = !f.instructions;

      if (f.meta) metaBlock.set(JSON.stringify(f.meta, null, 2));
      meta.el.hidden = !f.meta;
    }

    // ── The Tools section ─────────────────────────────────────────────

    var tools = App.ui.section({
      title: 'Tools', layout: 'stack', testid: 'mcp-tools-section'
    });
    var hintEl = el('p', 'mcp-tools-empty', "Press Test to load this server's tools.");
    hintEl.setAttribute('data-testid', 'mcp-tools-empty');
    var listEl = el('div', 'mcp-tools-list');
    listEl.setAttribute('data-testid', 'mcp-tools-list');
    tools.body.appendChild(hintEl);
    tools.body.appendChild(listEl);

    var entries = {}; // key -> {ctl, descEl, schemaBlock, sig}

    function subLabel(text) {
      return el('div', 'mcp-info-label', text);
    }

    // Fill a tool's body; replaces only the children of the disclosure's own body.
    function fillBody(entry, tool) {
      var desc = descOf(tool);
      var body = entry.ctl.body;
      var nodes = [];
      var needsDesc = !desc || desc.length > DESC_CUT || desc.indexOf('\n') !== -1;
      if (needsDesc) {
        var d = el('div', 'mcp-info-field');
        d.appendChild(subLabel('Description'));
        var text = el('div', desc ? 'mcp-info-text' : 'mcp-info-text mcp-info-empty',
          desc || 'No description provided.');
        text.setAttribute('data-testid', 'mcp-tool-description');
        d.appendChild(text);
        nodes.push(d);
      }
      var s = el('div', 'mcp-info-field');
      s.appendChild(subLabel('Input schema'));
      entry.schemaBlock = null;
      if (tool.input_schema && Object.keys(tool.input_schema).length > 0) {
        entry.schemaBlock = App.ui.codeBlock({
          text: JSON.stringify(tool.input_schema, null, 2), label: 'Input schema',
          maxHeight: 'tall', testid: 'mcp-tool-schema'
        });
        s.appendChild(entry.schemaBlock.el);
      } else {
        s.appendChild(el('div', 'mcp-info-text mcp-info-empty', 'No input schema.'));
      }
      nodes.push(s);
      body.replaceChildren.apply(body, nodes);
    }

    function descOf(tool) {
      var d = tool.description;
      return d === undefined || d === null ? '' : String(d);
    }

    function shortOf(desc) {
      return desc.length > DESC_CUT ? desc.slice(0, DESC_CUT) + '…' : desc;
    }

    function buildEntry(tool) {
      var entry = { sig: null, schemaBlock: null, metaEl: null, ctl: null };
      entry.metaEl = el('span', 'mcp-info-tool-desc');
      entry.ctl = App.ui.disclosure({
        variant: 'bordered', summary: tool.name, meta: [entry.metaEl],
        className: 'mcp-info-tool', testid: 'mcp-tool-item',
        onToggle: function (open) {
          if (open && entry.schemaBlock) entry.schemaBlock.refresh();
        }
      });
      return entry;
    }

    function setTools(list) {
      if (destroyed) return;
      if (!Array.isArray(list)) {
        listEl.replaceChildren();
        entries = {};
        listEl.hidden = true;
        hintEl.hidden = false;
        return;
      }
      var seen = {};
      var next = {};
      var nodes = [];
      for (var i = 0; i < list.length; i++) {
        var tool = list[i];
        if (!tool || typeof tool !== 'object') continue;
        var name = String(tool.name === undefined || tool.name === null ? '' : tool.name);
        seen[name] = (seen[name] || 0) + 1;
        var key = name + '\u0000' + seen[name];
        var entry = entries[key] || buildEntry(tool);
        var desc = descOf(tool);
        var sig = JSON.stringify([desc, tool.input_schema || null]);
        if (entry.sig !== sig) {
          entry.sig = sig;
          entry.metaEl.textContent = shortOf(desc);
          entry.metaEl.hidden = !desc;
          fillBody(entry, tool);
        }
        entry.ctl.setSummary(name);
        next[key] = entry;
        nodes.push(entry.ctl.el);
      }
      Object.keys(entries).forEach(function (k) {
        if (!next[k]) entries[k].ctl.destroy();
      });
      entries = next;
      App.ui.util.syncChildren(listEl, nodes);
      listEl.hidden = false;
      hintEl.hidden = true;
    }

    var cache = opts && opts.cache;
    update(cache);
    setTools(cache && Array.isArray(cache.tools) ? cache.tools : null);

    return {
      serverEl: server.el,
      toolsEl: tools.el,
      update: update,
      setTools: setTools,
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        Object.keys(entries).forEach(function (k) { entries[k].ctl.destroy(); });
        instructions.destroy();
        meta.destroy();
        entries = {};
      }
    };
  }

  window.App.studio.mcpEditor.serverInfo = {
    create: create,
    cacheHasServerInfo: cacheHasServerInfo
  };
})();
