(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Settings > General > Date and time (M28 F2 L3, flight DD4). The operator
  // picks the time zone agents tell the time in and the app shows times in:
  // the machine's own zone, or one chosen from an inline searchable list.
  // Built with DOM APIs only; server text is placed with textContent.
  //
  // Saving happens on choice (no Save button, no dirty source). Every PUT and
  // every page load takes a generation from GEN, which is module-level and so
  // shared across mounts (admin._refresh re-runs renderContent and builds a new
  // instance): only the latest response is applied, and a response for a
  // page that is no longer in the document touches App.time alone. The page's
  // nodes are built once and patched in place, so focus never moves.

  var GEN = 0;

  var INTRO = 'Agents use this time zone when they tell the time, and the app shows times in it.';
  var NOTE = 'The time tool uses a new zone at once. A chat that is already open keeps the date ' +
    'it was last loaded with; the next chat or a reopened one gets the new one.';

  function el(tag, attrs, children) {
    return window.App.ui.util.el(tag, attrs, children);
  }

  function norm(s) {
    return String(s === undefined || s === null ? '' : s)
      .toLowerCase()
      .replace(/_/g, ' ')
      .replace(/−/g, '-')
      .trim();
  }

  function cityOf(name) {
    var parts = String(name).split('/');
    return parts[parts.length - 1].replace(/_/g, ' ');
  }

  function browserZone() {
    try {
      var z = Intl.DateTimeFormat().resolvedOptions().timeZone;
      return typeof z === 'string' && z ? z : null;
    } catch (e) {
      return null;
    }
  }

  function jsonOpts(method, body) {
    return { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  }

  function renderDateTimePage(container) {
    var state = { settings: null, zones: [], links: {}, zonesFailed: false };
    var byZone = {};
    var viewMode = 'system';
    var built = false;
    var radio = null;
    var list = null;
    var listbox = null;
    var slot = null;
    var nodes = {};

    var root = el('div', { className: 'date-time-page' });
    var loading = el('p', { className: 'admin-system-text', text: 'Loading…' });
    var loadError = el('p', { className: 'field-error date-time-load-error', role: 'alert' });
    loadError.hidden = true;
    root.appendChild(loading);
    root.appendChild(loadError);
    window.App.admin.renderPage(container, 'Date and time', null, [root]);

    // ── Pure helpers over state ───────────────────────────────────────

    function canon(name) {
      return (name && state.links[name]) || name;
    }

    function storedZone() {
      return (state.settings && state.settings.zone) || null;
    }

    function storedCanonical() {
      var z = storedZone();
      return z ? canon(z) : null;
    }

    function offsetFor(name) {
      var row = byZone[canon(name)];
      return row ? row.offset : '';
    }

    function metaFor(row) {
      var abbr = row.abbreviation || '';
      if (!abbr || /^[+\-−]?\d/.test(abbr)) return row.offset;
      return row.offset + ' · ' + abbr;
    }

    // 0 = no match, 1 = the city starts with the query, 2 = another match: a
    // path segment (or a path tail such as "europe/ber") starts with it, a word
    // of the city does, the offset text contains it (with or without "UTC"), or
    // the abbreviation starts with it. Never a mid-word substring of the path.
    function tierOf(q, city, path, offset, abbr) {
      var c = norm(city);
      if (c.indexOf(q) === 0) return 1;
      var parts = String(path).split('/');
      for (var i = 0; i < parts.length; i++) {
        if (norm(parts.slice(i).join('/')).indexOf(q) === 0) return 2;
      }
      var words = c.split(/[\s\-]+/);
      for (var w = 0; w < words.length; w++) {
        if (words[w] && words[w].indexOf(q) === 0) return 2;
      }
      if (offset && /^(utc|[+\-0-9])/.test(q)) {
        var o = norm(offset);
        if (o.indexOf(q) !== -1 || o.replace(/^utc/, '').indexOf(q) !== -1) return 2;
      }
      if (abbr && norm(abbr).indexOf(q) === 0) return 2;
      return 0;
    }

    function checkLead(on) {
      if (on) return window.App.ui.util.icon('check');
      return el('span', { className: 'date-time-lead-spacer' });
    }

    // The search list's source: groups by region in the server's order, a row
    // per canonical zone, plus (for a non-blank query) an item per alias
    // whose own text matches while its canonical row does not.
    function source(query) {
      var q = norm(query);
      var chosen = storedCanonical();
      var order = [];
      var regions = {};
      function bucket(region) {
        if (!regions[region]) {
          regions[region] = { id: region, label: region, tiers: { 1: [], 2: [] }, best: 2 };
          order.push(regions[region]);
        }
        return regions[region];
      }
      function add(region, tier, item) {
        var b = bucket(region);
        b.tiers[tier].push(item);
        if (tier < b.best) b.best = tier;
      }
      var matched = {};
      for (var i = 0; i < state.zones.length; i++) {
        var row = state.zones[i];
        var tier = q ? tierOf(q, row.city, row.zone, row.offset, row.abbreviation) : 2;
        if (!tier) continue;
        matched[row.zone] = true;
        add(row.region, tier, {
          id: row.zone,
          label: row.city,
          description: row.zone,
          meta: metaFor(row),
          metaMono: true,
          lead: checkLead(row.zone === chosen),
          dataset: { zone: row.zone }
        });
      }
      if (q) {
        var names = Object.keys(state.links).sort();
        for (var k = 0; k < names.length; k++) {
          var alias = names[k];
          var target = state.links[alias];
          var trow = byZone[target];
          if (!trow || matched[target]) continue;
          var city = cityOf(alias);
          var atier = tierOf(q, city, alias, '', '');
          if (!atier) continue;
          var first = alias.split('/')[0];
          var region = regions[first] ? first : trow.region;
          add(region, atier, {
            id: 'alias:' + alias,
            label: city,
            description: alias + ' · same clock as ' + target,
            meta: trow.offset,
            metaMono: true,
            lead: checkLead(false),
            dataset: { zone: alias }
          });
        }
      }
      var out = [];
      for (var n = 0; n < order.length; n++) order[n].pos = n;
      order.sort(function (x, y) { return x.best - y.best || x.pos - y.pos; });
      for (var m = 0; m < order.length; m++) {
        var g = order[m];
        out.push({ id: g.id, label: g.label, items: g.tiers[1].concat(g.tiers[2]) });
      }
      return out;
    }

    // ── Patching (never rebuilds) ─────────────────────────────────────

    function patchChosen() {
      var z = storedZone();
      nodes.chosen.textContent = '';
      if (!z) {
        nodes.chosen.textContent = 'Pick a zone below. Nothing changes until you do.';
        return;
      }
      var off = offsetFor(z);
      if (!off && state.settings.effective && state.settings.effective.zone === z) {
        off = state.settings.effective.offset || '';
      }
      nodes.chosen.appendChild(document.createTextNode('Selected: '));
      nodes.chosen.appendChild(el('strong', { text: cityOf(z) }));
      nodes.chosen.appendChild(document.createTextNode(' ' + z + (off ? ' · ' + off : '')));
    }

    function patchPreview() {
      var s = state.settings;
      var p = s.preview || {};
      nodes.previewTool.textContent = String(p.tool || '').split('\n')[0];
      var enabled = s.tool_enabled !== false;
      nodes.previewPrompt.textContent = enabled ? p.prompt : p.prompt_without_tool;
      nodes.promptMuted.hidden = enabled;
      nodes.previewClock.textContent = (p.clock || '') + ' in the Chats list and on messages';
    }

    function patchHint() {
      var s = state.settings;
      var b = browserZone();
      var ec = s.effective ? s.effective.canonical : null;
      var bc = b ? canon(b) : null;
      var show = !!b && (ec ? bc !== ec : true);
      nodes.hint.hidden = !show;
      if (!show) return;
      var inner = [];
      if (bc !== b) inner.push('same clock as ' + bc);
      var off = offsetFor(b);
      if (off) inner.push(off);
      var label = (s.effective && (s.effective.label || s.effective.zone)) || 'a different zone';
      nodes.hintText.textContent = '';
      nodes.hintText.appendChild(document.createTextNode('Your browser is in '));
      nodes.hintText.appendChild(el('strong', { text: b }));
      if (inner.length) nodes.hintText.appendChild(document.createTextNode(' (' + inner.join(', ') + ')'));
      if (s.mode === 'zone') {
        nodes.hintText.appendChild(document.createTextNode(', but agents are set to '));
        nodes.hintText.appendChild(el('strong', { text: label }));
        nodes.hintText.appendChild(document.createTextNode('.'));
      } else {
        nodes.hintText.appendChild(document.createTextNode(', but the machine running the-one reports '));
        nodes.hintText.appendChild(el('strong', { text: label }));
        nodes.hintText.appendChild(document.createTextNode(
          '. That happens under WSL, in a container or on another machine.'));
      }
      var known = !!(byZone[b] || state.links[b]);
      nodes.useBrowser.hidden = !known;
      nodes.useBrowserLabel(b);
    }

    function syncActive() {
      var id = storedCanonical();
      if (id) list.setActive(id);
    }

    function refreshList() {
      var top = listbox.scrollTop;
      list.refresh();
      listbox.scrollTop = top;
      syncActive();
    }

    function showSlot() {
      var on = viewMode === 'zone';
      slot.hidden = !on;
      if (on) syncActive();
    }

    function patch() {
      var s = state.settings;
      radio.setValue(viewMode);
      var sys = s.system || {};
      radio.setDescription('system',
        'Detected on the machine running the-one: ' + (sys.zone || 'no zone name detected') +
        ' · ' + (sys.offset || ''));
      patchChosen();
      nodes.zonesError.hidden = !state.zonesFailed;
      list.el.hidden = state.zonesFailed;
      refreshList();
      showSlot();
      patchPreview();
      patchHint();
    }

    function applySettings(r) {
      state.settings = r;
      viewMode = r.mode === 'zone' ? 'zone' : 'system';
      patch();
    }

    // ── Requests ──────────────────────────────────────────────────────

    function finish(g, r) {
      if (g !== GEN) return false;
      if (root.isConnected && built) applySettings(r);
      window.App.time.setZone(window.App.time.zoneFromSettings(r));
      return true;
    }

    function reload() {
      var g = ++GEN;
      window.App.api.fetchJson('/api/time-settings').then(function (r) {
        finish(g, r);
      }, function (err) {
        if (g !== GEN) return;
        if (root.isConnected && built) showError(err.message);
      });
    }

    function showError(msg) {
      nodes.status.textContent = '';
      nodes.error.textContent = msg;
      nodes.error.hidden = false;
    }

    function save(body) {
      var g = ++GEN;
      nodes.error.hidden = true;
      nodes.error.textContent = '';
      nodes.status.textContent = '';
      window.App.api.fetchJson('/api/time-settings', jsonOpts('PUT', body)).then(function (r) {
        if (g !== GEN) return;
        if (root.isConnected && built) {
          applySettings(r);
          nodes.status.textContent = 'Saved. Agents now use ' +
            (r.mode === 'zone' && r.zone ? r.zone : 'the system time zone') + '.';
        }
        window.App.time.setZone(window.App.time.zoneFromSettings(r));
      }, function (err) {
        if (g !== GEN) return;
        if (root.isConnected && built) showError(err.message);
        reload();
      });
    }

    // ── Building (once, after the first successful load) ──────────────

    function onMode(value) {
      viewMode = value;
      showSlot();
      nodes.error.hidden = true;
      if (value === 'system') {
        save({ mode: 'system', zone: storedZone() });
      } else if (storedZone()) {
        save({ mode: 'zone', zone: storedZone() });
      }
    }

    function onPick(item) {
      var name = item && item.dataset && item.dataset.zone;
      if (name) save({ mode: 'zone', zone: name });
    }

    function build() {
      nodes.chosen = el('p', {
        className: 'date-time-chosen',
        id: window.App.ui.util.uid('dt-chosen'),
        'data-testid': 'date-time-chosen'
      });
      list = window.App.ui.searchList({
        label: 'Search time zones',
        placeholder: 'Search by city, zone or offset: Tokyo, Europe/, +05:30',
        source: source,
        emptyText: function (q) { return 'No time zones match “' + q + '”.'; },
        onPick: onPick,
        inputTestid: 'date-time-search',
        rowTestid: 'date-time-zone-row'
      });
      listbox = list.el.querySelector('.ui-search-list-listbox');
      list.input.setAttribute('aria-describedby', nodes.chosen.id);
      nodes.zonesError = el('p', {
        className: 'field-error',
        text: 'The list of time zones could not be loaded.'
      });
      nodes.zonesError.hidden = true;

      radio = window.App.ui.radioGroup({
        legend: 'Time zone',
        legendHidden: true,
        name: 'time-zone-mode',
        testid: 'date-time-mode',
        value: 'system',
        onChange: onMode,
        options: [
          { value: 'system', label: 'Use the system time zone', testid: 'date-time-mode-system' },
          {
            value: 'zone',
            label: 'Choose a time zone',
            description: 'For a server, WSL or a container whose clock zone is not yours.',
            testid: 'date-time-mode-zone'
          }
        ]
      });
      slot = radio.optionEl('zone');
      slot.appendChild(nodes.chosen);
      slot.appendChild(list.el);
      slot.appendChild(nodes.zonesError);
      slot.hidden = true;

      // The mismatch hint.
      nodes.hintText = el('span', { className: 'date-time-mismatch-text' });
      nodes.useBrowser = window.App.ui.button({
        label: 'Use browser zone',
        variant: 'secondary',
        size: 'sm',
        testid: 'date-time-use-browser',
        onClick: function () {
          var b = browserZone();
          if (b) save({ mode: 'zone', zone: b });
        }
      });
      nodes.useBrowserLabel = function (b) { nodes.useBrowser.textContent = 'Use ' + b; };
      nodes.hint = el('div', {
        className: 'banner banner-info date-time-mismatch',
        role: 'note',
        'data-testid': 'date-time-mismatch'
      }, [nodes.hintText, nodes.useBrowser]);
      nodes.hint.hidden = true;

      nodes.status = el('p', {
        className: 'date-time-status',
        role: 'status',
        'aria-live': 'polite',
        'data-testid': 'date-time-status'
      });
      nodes.error = el('p', {
        className: 'field-error date-time-error',
        role: 'alert',
        'data-testid': 'date-time-error'
      });
      nodes.error.hidden = true;

      // What agents see.
      nodes.previewTool = el('code', { className: 'date-time-chip', 'data-testid': 'date-time-preview-tool' });
      nodes.previewPrompt = el('span', { className: 'date-time-preview-prompt', 'data-testid': 'date-time-preview-prompt' });
      nodes.promptMuted = el('span', {
        className: 'date-time-muted',
        text: 'The time tool is turned off in Built-in tools.'
      });
      nodes.promptMuted.hidden = true;
      nodes.previewClock = el('span', { className: 'date-time-preview-clock', 'data-testid': 'date-time-preview-clock' });
      function row(term, def) {
        return el('div', { className: 'date-time-preview-row' }, [
          el('dt', { text: term }),
          el('dd', null, def)
        ]);
      }

      loading.hidden = true;
      root.appendChild(el('p', { className: 'admin-system-text', text: INTRO }));
      root.appendChild(el('div', { className: 'section-title', text: 'Time zone' }));
      root.appendChild(nodes.hint);
      root.appendChild(radio.el);
      root.appendChild(nodes.status);
      root.appendChild(nodes.error);
      root.appendChild(el('div', { className: 'section-title', text: 'What agents see' }));
      root.appendChild(el('dl', { className: 'date-time-preview' }, [
        row('The time tool returns', [nodes.previewTool]),
        row('A new chat starts with', [nodes.previewPrompt, nodes.promptMuted]),
        row('Times in the app', [nodes.previewClock])
      ]));
      root.appendChild(el('p', { className: 'admin-system-text date-time-note', text: NOTE }));
      built = true;
    }

    function index(zonesBody) {
      state.zones = (zonesBody && zonesBody.zones) || [];
      state.links = (zonesBody && zonesBody.links) || {};
      state.zonesFailed = !zonesBody;
      byZone = {};
      for (var i = 0; i < state.zones.length; i++) byZone[state.zones[i].zone] = state.zones[i];
    }

    // ── First load ────────────────────────────────────────────────────

    var g0 = ++GEN;
    Promise.all([
      window.App.api.fetchJson('/api/time-settings'),
      window.App.api.fetchJson('/api/time-zones').then(function (z) { return z; }, function () { return null; })
    ]).then(function (res) {
      if (g0 !== GEN) return;
      var r = res[0];
      index(res[1]);
      if (root.isConnected) {
        build();
        applySettings(r);
      }
      window.App.time.setZone(window.App.time.zoneFromSettings(r));
    }, function (err) {
      if (g0 !== GEN || !root.isConnected) return;
      loading.hidden = true;
      loadError.textContent = 'The time settings could not be loaded: ' + err.message;
      loadError.hidden = false;
    });
  }

  window.App.admin.renderDateTimePage = renderDateTimePage;
})();
