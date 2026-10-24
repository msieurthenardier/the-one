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
  // every page load takes a token from `gen`, one module-level latest() shared
  // across mounts (admin._refresh re-runs renderContent and builds a new
  // instance): only the latest response is applied, and a response for a
  // page that is no longer in the document touches App.time alone. The page's
  // nodes are built once and patched in place, so focus never moves (the one
  // exception is "Use {zone}", which hides the hint that holds its own button:
  // focus is moved to the chosen-zone line first, DD8-13). Since M31 F4 L09 the
  // page is built from the library: pageHeader (through renderPage), section,
  // banner, status, facts and the inline searchList.

  var gen = window.App.ui.util.latest();

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
    return App.time.browserZone();
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
    var slot = null;
    var nodes = {};
    var centrePending = true;

    var root = el('div', { className: 'date-time-page' });
    var loading = el('p', { className: 'admin-system-text', text: 'Loading…' });
    var loadError = window.App.ui.status({ state: 'danger', role: 'alert', textTone: true });
    loadError.el.hidden = true;
    root.appendChild(loading);
    root.appendChild(loadError.el);
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
      // The server already returns '' for a numeric or UTC-offset abbreviation.
      var abbr = row.abbreviation || '';
      return abbr ? row.offset + ' · ' + abbr : row.offset;
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
          selected: row.zone === chosen,
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
            selected: alias === storedZone(),
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
      // B8: the id and offset use the list's mono font, as in the rows.
      nodes.chosen.appendChild(document.createTextNode(' '));
      nodes.chosen.appendChild(el('span', {
        className: 'date-time-chosen-id',
        text: z + (off ? ' · ' + off : '')
      }));
    }

    function patchPreview() {
      var s = state.settings;
      var p = s.preview || {};
      nodes.previewTool.textContent = String(p.tool || '').split('\n')[0];
      var enabled = s.tool_enabled !== false;
      nodes.previewPrompt.textContent = enabled ? p.prompt : p.prompt_without_tool;
      nodes.promptMuted.hidden = enabled;
      // Drawn client-side with the app's own formatter, so the claim that it matches the Chats
      // list and message times is true by construction (squawk 0182). p.clock stays in the API.
      var clock = p.clock || '';
      try {
        window.App.time.applySettings(s);
        clock = window.App.time.formatClock(new Date());
      } catch (err) { /* keep the server's text */ }
      nodes.previewClock.textContent = clock + ' in the Chats list and on messages';
    }

    // B9: a place as a person says it. The zone is canonicalised first, so an alias such as
    // Asia/Calcutta reads "Kolkata"; a zone with no city (UTC, Etc/GMT+5) keeps its id. Two
    // cities of the same name are not told apart (the raw ids are in the banner's title).
    function placeOf(name) {
      var c = canon(name);
      if (!c) return null;
      if (c.indexOf('/') === -1 || c.indexOf('Etc/') === 0) return name;
      return cityOf(c);
    }

    function patchHint() {
      var s = state.settings;
      var b = browserZone();
      var ec = s.effective ? s.effective.canonical : null;
      var bc = b ? canon(b) : null;
      var show = !!b && (ec ? bc !== ec : true);
      if (!show) {
        nodes.hint.hide();
        return;
      }
      var eff = (s.effective && (s.effective.zone || s.effective.label)) || '';
      var ePlace = placeOf(eff) || (s.effective && s.effective.label) || 'a different zone';
      var off = offsetFor(b);
      var text = 'Your browser is in ' + placeOf(b) + (off ? ' (' + off + ')' : '');
      if (s.mode === 'zone') {
        text += '; agents use ' + ePlace + '.';
      } else {
        text += '; the machine running the-one reports ' + ePlace +
          '. That happens under WSL, in a container or on another machine.';
      }
      nodes.hintText.textContent = text;
      nodes.hint.el.setAttribute('title', 'Your browser: ' + b + '. Agents: ' + (eff || ePlace) + '.');
      var known = !!(byZone[b] || state.links[b]);
      nodes.useBrowser.hidden = !known;
      nodes.useBrowser.textContent = 'Use ' + b;
      nodes.hint.show();
    }

    // The stored zone's row is the list's active row (it carries aria-selected; an unfocused
    // list paints no active row). Page code, because the variant does not know the stored
    // zone. It centres the row once - the first time the list is shown, or when the stored
    // zone changed from outside the list (another tab, a reload) - and never after a pick:
    // the row the user just clicked is already where they want it, and typing never calls it.
    function syncActive() {
      var visible = !slot.hidden;
      var mode = centrePending && visible ? 'center' : 'none';
      // An alias item exists only while its canonical row is out of the results, so at
      // most one of the two targets is present; setActive ignores an absent id.
      var z = storedZone();
      if (z && state.links[z]) list.setActive('alias:' + z, { scroll: mode });
      var id = storedCanonical();
      if (id) list.setActive(id, { scroll: mode });
      if (centrePending && visible && (id || z)) centrePending = false;
    }

    function refreshList() {
      // keepScroll restores scrollTop and the active row for an unchanged query.
      list.refresh();
      syncActive();
    }

    function showSlot() {
      var on = viewMode === 'zone';
      slot.hidden = !on;
      if (on) syncActive();
    }

    function patch(opts) {
      var s = state.settings;
      radio.setValue(viewMode);
      var sys = s.system || {};
      radio.setDescription('system',
        'Detected on the machine running the-one: ' + (sys.zone || 'no zone name detected') +
        ' · ' + (sys.offset || ''));
      patchChosen();
      nodes.zonesError.el.hidden = !state.zonesFailed;
      list.el.hidden = state.zonesFailed;
      refreshList();
      showSlot();
      patchPreview();
      // DD8-13: "Use {zone}" hides the hint that holds its own focused button. Move focus
      // to the chosen-zone line (now shown, in the slot) BEFORE the hint hides.
      if (opts && opts.focusChosen && !slot.hidden) nodes.chosen.focus();
      patchHint();
    }

    function applySettings(r, opts) {
      var prior = state.settings ? storedZone() : undefined;
      state.settings = r;
      viewMode = r.mode === 'zone' ? 'zone' : 'system';
      // A stored zone that changed from outside this page's own picks is centred again.
      if (opts && opts.external && prior !== undefined && prior !== storedZone()) {
        centrePending = true;
      }
      patch(opts);
    }

    // ── Requests ──────────────────────────────────────────────────────

    function finish(token, r) {
      if (!gen.isCurrent(token)) return false;
      if (root.isConnected && built) applySettings(r, { external: true });
      window.App.time.applySettings(r);
      return true;
    }

    function reload() {
      var token = gen.next();
      window.App.api.fetchJson('/api/time-settings').then(function (r) {
        finish(token, r);
      }, function (err) {
        if (!gen.isCurrent(token)) return;
        if (root.isConnected && built) showError(err.message);
      });
    }

    function showError(msg) {
      clearStatus();
      nodes.errorStatus.set('danger', msg);
      nodes.error.hidden = false;
    }

    function clearError() {
      nodes.error.hidden = true;
      nodes.errorStatus.set('danger', '');
    }

    // The status is a persistent role=status region (a hidden-toggled live region announces
    // unreliably) that holds one App.ui.status only while there is something to say, so it
    // takes no height when empty (B10).
    function clearStatus() {
      nodes.status.textContent = '';
    }

    function showSaved(text) {
      clearStatus();
      nodes.status.appendChild(
        window.App.ui.status({ state: 'success', text: text, live: 'off' }).el);
    }

    function save(body, opts) {
      var token = gen.next();
      clearError();
      clearStatus();
      window.App.api.fetchJson('/api/time-settings', jsonOpts('PUT', body)).then(function (r) {
        if (!gen.isCurrent(token)) return;
        if (root.isConnected && built) {
          // The user's own pick: the row they chose is where they want it, never re-centre.
          centrePending = false;
          applySettings(r, { focusChosen: !!(opts && opts.focusChosen) });
          showSaved('Saved. Agents now use ' +
            (r.mode === 'zone' && r.zone ? r.zone : 'the system time zone') + '.');
        }
        window.App.time.applySettings(r);
      }, function (err) {
        if (!gen.isCurrent(token)) return;
        if (root.isConnected && built) showError(err.message);
        reload();
      });
    }

    // ── Building (once, after the first successful load) ──────────────

    function onMode(value) {
      viewMode = value;
      showSlot();
      clearError();
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
        tabindex: '-1',
        'data-testid': 'date-time-chosen'
      });
      list = window.App.ui.searchList({
        label: 'Search time zones',
        placeholder: 'Search by city, zone or offset: Tokyo, Europe/, +05:30',
        source: source,
        emptyText: function (q) { return 'No time zones match “' + q + '”.'; },
        onPick: onPick,
        inputTestid: 'date-time-search',
        rowTestid: 'date-time-zone-row',
        inline: true,
        keepScroll: true,
        describedBy: nodes.chosen,
        scrollActive: 'center'
      });
      nodes.zonesError = window.App.ui.status({
        state: 'danger',
        text: 'The list of time zones could not be loaded.',
        textTone: true,
        live: 'off'
      });
      nodes.zonesError.el.hidden = true;

      radio = window.App.ui.radioGroup({
        legend: 'Time zone',
        legendHidden: true,
        name: 'time-zone-mode',
        testid: 'date-time-mode',
        value: 'system',
        onChange: onMode,
        slotIndent: 'label',
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
      slot.appendChild(nodes.zonesError.el);
      slot.hidden = true;

      // The mismatch hint: a banner, the text then the "Use {zone}" button (last child).
      nodes.hintText = el('span', { className: 'date-time-mismatch-text' });
      nodes.useBrowser = window.App.ui.button({
        label: 'Use browser zone',
        variant: 'secondary',
        size: 'sm',
        testid: 'date-time-use-browser',
        onClick: function () {
          var b = browserZone();
          if (b) save({ mode: 'zone', zone: b }, { focusChosen: true });
        }
      });
      nodes.hint = window.App.ui.banner({
        tone: 'info',
        role: 'note',
        className: 'date-time-mismatch',
        testid: 'date-time-mismatch',
        children: [nodes.hintText, nodes.useBrowser],
        hidden: true
      });

      nodes.status = el('div', { role: 'status', 'data-testid': 'date-time-status' });
      nodes.errorStatus = window.App.ui.status({
        state: 'danger',
        role: 'alert',
        textTone: true,
        testid: 'date-time-error'
      });
      nodes.error = nodes.errorStatus.el;
      nodes.error.hidden = true;

      // What agents see: the library's facts list, values placed in place by patchPreview.
      nodes.previewTool = el('span', {});
      nodes.previewPrompt = el('span', { 'data-testid': 'date-time-preview-prompt' });
      nodes.promptMuted = el('span', {
        className: 'date-time-muted',
        text: 'The time tool is turned off in Built-in tools.',
        'data-testid': 'date-time-prompt-muted'
      });
      nodes.promptMuted.hidden = true;
      nodes.previewClock = el('span', {});
      var facts = window.App.ui.facts({
        rows: [
          { label: 'The time tool returns', value: nodes.previewTool, mono: true,
            valueTestid: 'date-time-preview-tool' },
          { label: 'A new chat starts with', value: [nodes.previewPrompt, nodes.promptMuted] },
          { label: 'Times in the app', value: nodes.previewClock,
            valueTestid: 'date-time-preview-clock' }
        ]
      });

      loading.hidden = true;
      var App = window.App;
      root.appendChild(el('p', { className: 'admin-system-text', text: INTRO }));
      root.appendChild(App.ui.section({
        title: 'Time zone',
        layout: 'stack',
        inset: 'none',
        children: [nodes.hint.el, radio.el, nodes.status, nodes.error]
      }).el);
      root.appendChild(App.ui.section({
        title: 'What agents see',
        layout: 'stack',
        inset: 'none',
        children: [
          facts.el,
          el('p', { className: 'admin-system-text date-time-note', text: NOTE })
        ]
      }).el);
      root.setAttribute('data-built', '');
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

    var token0 = gen.next();
    Promise.all([
      window.App.api.fetchJson('/api/time-settings'),
      window.App.api.fetchJson('/api/time-zones').then(function (z) { return z; }, function () { return null; })
    ]).then(function (res) {
      if (!gen.isCurrent(token0)) return;
      var r = res[0];
      index(res[1]);
      if (root.isConnected) {
        build();
        applySettings(r);
      }
      window.App.time.applySettings(r);
    }, function (err) {
      if (!gen.isCurrent(token0) || !root.isConnected) return;
      loading.hidden = true;
      loadError.set('danger', 'The time settings could not be loaded: ' + err.message);
      loadError.el.hidden = false;
    });
  }

  window.App.admin.renderDateTimePage = renderDateTimePage;
})();
