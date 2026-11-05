// Sortie 10 mockup, round 2. Scratch copy only: never part of the product.
(function () {
  var PID = '65eb6d310d33', SID = '0180889542ec';
  var KEY_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5" fill="currentColor"/></svg>';
  var MASK = '***...';
  var SECRETS = [
    { name: 'Bank login', desc: 'Online banking sign-in.', agents: 0,
      pairs: [['bank_login', 'a8c1'], ['bank_password', '77d0']],
      tools: ['mcp__goldfinch__typeText'] },
    { name: 'Goldfinch vault key', desc: 'Master passphrase for the Goldfinch password vault.', agents: 1,
      pairs: [['goldfinch_vault_key', 'f3a9']],
      tools: ['mcp__goldfinch__vaultUnlock'] },
    { name: 'Home address', desc: 'Shipping address for online orders.', agents: 1,
      pairs: [['home_address', '4 St'], ['home_city', 'ourn'], ['home_postcode', '3000'], ['home_phone', '0190']],
      tools: ['mcp__goldfinch__typeText', 'mcp__goldfinch__vaultFill'] }
  ];
  var GOLDFINCH = ['activateTab', 'captureScreenshot', 'captureWindow', 'click', 'closeTab', 'dragPointer',
    'enumerateTabs', 'evaluate', 'findInPage', 'getHistory', 'goBack', 'goForward', 'navigate', 'openTab',
    'pressKey', 'readAxTree', 'readDom', 'reload', 'scroll', 'typeText', 'vaultAnswerAuth', 'vaultFill',
    'vaultList', 'vaultTotp', 'vaultUnlock'];
  var TOOLS = GOLDFINCH.map(function (t) { return { name: 'mcp__goldfinch__' + t, source: 'Goldfinch' }; });
  var st = { secret: null, variant: 'B' };

  function ui() { return window.App.ui; }
  function q(s) { return document.querySelector(s); }
  function meta(s) {
    var n = s.pairs.length;
    return n + (n === 1 ? ' value' : ' values') + ' · ' + s.agents + (s.agents === 1 ? ' agent' : ' agents');
  }
  function slug(name) {
    return String(name || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  }

  fetch('/api/tools', { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (list) {
    TOOLS = list.map(function (t) { return { name: t.name, source: 'Built-in' }; }).concat(TOOLS);
  }).catch(function () {});

  // ── Library list ────────────────────────────────────────────────
  function libraryGroup() {
    var body = q('[data-testid=library-list] .ui-list-pane-body');
    var groups = body.querySelectorAll('.ui-list-pane-group');
    var g = groups[0].cloneNode(true);
    g.setAttribute('data-s10-group', '');
    g.querySelector('.ui-list-pane-caption').textContent = 'Secrets';
    var ul = g.querySelector('ul'); var li0 = ul.querySelector('li'); ul.textContent = '';
    SECRETS.forEach(function (s, i) {
      var li = li0.cloneNode(true); var a = li.querySelector('a');
      a.setAttribute('data-testid', 'secret-card'); a.removeAttribute('aria-current'); a.href = '#library';
      a.querySelector('.ui-list-pane-icon').innerHTML = KEY_SVG;
      a.querySelector('.ui-list-pane-label').textContent = s.name;
      a.querySelector('.ui-list-pane-meta').textContent = meta(s);
      var b = a.querySelector('.ui-list-pane-badges'); if (b) b.remove();
      a.addEventListener('click', function (e) { e.preventDefault(); openSecret('edit', i); });
      ul.appendChild(li);
    });
    body.appendChild(g);
    var menu = q('[data-testid=library-add-connector]');
    if (menu && !q('[data-testid=library-add-secret]')) {
      var m = menu.cloneNode(true); m.setAttribute('data-testid', 'library-add-secret');
      m.querySelector('.ui-menu-item-label').textContent = 'Secret';
      m.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); openSecret('create', null); });
      menu.parentNode.appendChild(m);
    }
  }
  function markSelected() {
    document.querySelectorAll('[data-testid=library-list] [aria-current]').forEach(function (a) { a.removeAttribute('aria-current'); });
    document.querySelectorAll('[data-testid=secret-card]').forEach(function (a, i) {
      if (st.secret && st.secret.mode === 'edit' && i === st.secret.idx) a.setAttribute('aria-current', 'page');
    });
  }

  // ── Allowed tools: chips with search-ahead ──────────────────────
  function toolPicker(values, isCreate) {
    var U = ui(), util = U.util;
    var chips = U.chipList({ label: 'Allowed tools', values: values, placeholder: 'Search tools…', inputId: 'sf-tools' });
    var input = chips.input;
    var wrap = util.el('div', { className: 's10-picker' });
    wrap.style.position = 'relative';
    wrap.appendChild(chips.el);
    var pop = util.el('div', { className: 's10-pop', role: 'listbox' });
    pop.style.cssText = 'position:absolute;left:0;right:0;top:calc(100% + 4px);z-index:20;background:var(--surface-elevated);' +
      'border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow-popover);max-height:260px;overflow:auto;padding:4px;display:none';
    wrap.appendChild(pop);
    var items = [], active = 0;
    function render() {
      var term = input.value.trim().toLowerCase();
      var have = chips.values();
      var hits = term ? TOOLS.filter(function (t) {
        return have.indexOf(t.name) < 0 && t.name.toLowerCase().indexOf(term) >= 0;
      }).slice(0, 8) : [];
      pop.textContent = ''; items = hits; active = 0;
      if (!term) { pop.style.display = 'none'; return; }
      if (!hits.length) {
        pop.appendChild(util.el('div', { text: 'No tool matches “' + input.value.trim() + '”.' }));
        pop.lastChild.style.cssText = 'padding:8px 10px;color:var(--fg-tertiary);font-size:13px';
      }
      hits.forEach(function (t, i) {
        var row = util.el('div', { role: 'option' });
        row.style.cssText = 'display:flex;justify-content:space-between;gap:12px;padding:6px 10px;border-radius:6px;cursor:pointer;font-size:13px';
        var nm = util.el('span', { text: t.name }); nm.style.fontFamily = 'var(--font-mono, monospace)';
        var src = util.el('span', { text: t.source }); src.style.color = 'var(--fg-tertiary)';
        row.appendChild(nm); row.appendChild(src);
        row.addEventListener('mousedown', function (e) { e.preventDefault(); pick(i); });
        row.addEventListener('mouseenter', function () { active = i; paint(); });
        pop.appendChild(row);
      });
      pop.style.display = 'block';
      paint();
    }
    function paint() {
      Array.prototype.forEach.call(pop.querySelectorAll('[role=option]'), function (r, i) {
        r.style.background = i === active ? 'var(--accent-translucent)' : '';
        r.setAttribute('aria-selected', i === active ? 'true' : 'false');
      });
    }
    function pick(i) {
      var t = items[i]; if (!t) return;
      chips.setValues(chips.values().concat([t.name]));
      input.value = ''; render(); input.focus();
      if (field) field.setError(null);
    }
    input.addEventListener('input', render);
    input.addEventListener('focus', render);
    input.addEventListener('blur', function () { setTimeout(function () { pop.style.display = 'none'; }, 100); });
    input.addEventListener('keydown', function (e) {
      if (pop.style.display === 'none' || !items.length) return;
      if (e.key === 'ArrowDown') { active = (active + 1) % items.length; paint(); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.key === 'ArrowUp') { active = (active - 1 + items.length) % items.length; paint(); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.key === 'Enter') { pick(active); e.preventDefault(); e.stopImmediatePropagation(); }
      else if (e.key === 'Escape') { pop.style.display = 'none'; e.stopImmediatePropagation(); }
    }, true);
    var field = U.field({ label: 'Allowed tools', control: input, host: wrap,
      hint: 'Only these tools can receive this secret’s values. Type to search built-in and MCP tools.' });
    if (isCreate) field.setError('Choose at least one tool that may receive this secret.');
    return field;
  }

  // ── Library editor ──────────────────────────────────────────────
  function editor(mode, idx) {
    var U = ui(), util = U.util;
    var isCreate = mode === 'create';
    var s = isCreate ? { name: '', desc: '', pairs: [], tools: [], agents: 0 } : SECRETS[idx];
    var container = q('#main-content .studio-section-content');
    var shell = U.editorShell({
      breadcrumb: { label: 'Library', href: '#library', trail: ' / Secrets' },
      title: isCreate ? 'New secret' : s.name,
      actions: {
        cancel: { testid: 'cancel-secret-btn', enabledWhenClean: isCreate, onClick: function () { location.hash = '#library'; } },
        save: { label: isCreate ? 'Create' : 'Save', testid: 'save-secret-btn', onClick: function () {} }
      }
    });
    var nameInput = U.textInput({ id: 'sf-name', value: s.name, placeholder: 'Home address' });
    var name = U.field({ label: 'Name', control: nameInput });
    var descInput = U.textInput({ id: 'sf-desc', value: s.desc, placeholder: 'What it is and when to use it' });
    var desc = U.field({ label: 'Description', control: descInput,
      hint: 'Agents see the name, description and keys, never the values.' });
    var main = U.section({ title: 'Secret', children: [name.el, desc.el] });

    var rows = s.pairs.map(function (p) {
      return { key: p[0], value: MASK + p[1], _stored: MASK + p[1] };
    });
    if (isCreate) rows = [{ key: '', value: '', _stored: '' }];
    var table = U.keyValueTable({
      label: 'Values', testid: 'secret-kv-table', addTestid: 'secret-add-pair-btn', addLabel: '+ Add pair', keyColumn: 'key',
      columns: [
        { key: 'key', label: 'Key', placeholder: 'key_name', mono: true },
        { key: 'value', label: 'Value', placeholder: 'value', type: 'secret', storedKey: '_stored' }
      ],
      rows: rows,
      removeLabel: function (n, row) { return row.key ? 'Remove ' + row.key : 'Remove pair ' + n; },
      onChange: function () {}
    });
    // The first key follows the name until the operator edits it.
    var keyTouched = !isCreate;
    var firstKey = table.el.querySelector('tbody tr input');
    if (firstKey) firstKey.addEventListener('input', function () { keyTouched = true; });
    nameInput.addEventListener('input', function () {
      if (!keyTouched) table.setRow(0, { key: slug(nameInput.value) });
    });
    var values = U.section({
      title: 'Values', layout: 'stack', children: [table.el],
      description: 'Agents use each key as {{secret:key}} in a tool call; the value is filled in when the tool runs. Values are stored encrypted and never shown again, and are hidden wherever they appear in a tool’s output.'
    });

    var toolsField = toolPicker(s.tools, isCreate);
    var toolsSec = U.section({ title: 'Allowed tools', layout: 'stack', children: [toolsField.el],
      description: 'If an agent puts this secret in any other tool, the call is refused with an error that names the key, never its value.' });

    var parts = [shell.el, main.el, values.el, toolsSec.el];
    if (!isCreate) {
      var used;
      if (s.agents) {
        var a = util.el('a', { href: '#agents/browser-helper/tools', text: 'browser-helper' });
        used = util.el('p', { className: 'admin-pf-models-help' }, ['Granted to ', a, '. Grant or remove it in each agent’s Tools tab.']);
      } else {
        used = util.el('p', { className: 'admin-pf-models-help', text: 'No agent uses this secret yet. Grant it in an agent’s Tools tab.' });
      }
      parts.push(U.section({ title: 'Used by', children: [used] }).el);
      parts.push(U.dangerZone({ title: 'Danger zone', action: { label: 'Delete secret', testid: 'delete-secret-btn', onConfirm: function () {} }, notice: { testid: 's10-x' } }).el);
    }
    container.replaceChildren.apply(container, parts);
  }

  // ── Agent Tools tab ─────────────────────────────────────────────
  function toolsTab() {
    var U = ui(), util = U.util;
    var granted = ['Goldfinch vault key', 'Home address'];
    var list = util.el('div', { className: 'agent-knowledge-list' });
    SECRETS.forEach(function (s) {
      var row = util.el('div', { className: 'agent-knowledge-row' });
      var t = U.toggle({ label: s.name, checked: granted.indexOf(s.name) >= 0, onChange: function () {} });
      row.appendChild(t.el);
      var n = s.tools.length;
      row.appendChild(util.el('span', { className: 'agent-knowledge-row-tool-name',
        text: s.desc + '  ·  ' + n + (n === 1 ? ' tool' : ' tools') }));
      list.appendChild(row);
    });
    var intro = util.el('p', { className: 'admin-pf-models-help',
      text: 'Secrets this agent can pass to its tools. It never sees their values. Manage them in Library › Secrets.' });
    var section = U.section({ title: 'Secrets', titleTag: 'h2', testid: 'agent-tools-secrets-section', children: [intro, list] });
    var mcp = q('[data-testid=agent-tools-mcp-section]');
    mcp.parentNode.insertBefore(section.el, mcp);
  }

  // ── Chat drawer ─────────────────────────────────────────────────
  function leafWithText(root, text) {
    return Array.prototype.filter.call(root.querySelectorAll('*'), function (e) {
      return e.children.length === 0 && e.textContent.trim() === text;
    })[0];
  }
  function drawer() {
    var lab = leafWithText(q('#chat-drawer'), 'MCP servers'); if (!lab) return;
    var grp = lab.parentNode;
    while (grp && grp.parentNode && grp.parentNode.children.length < 3) grp = grp.parentNode;
    var c = grp.cloneNode(true);
    c.setAttribute('data-s10-drawer', '');
    var leaves = Array.prototype.filter.call(c.querySelectorAll('*'), function (e) { return e.children.length === 0; });
    leaves[0].textContent = 'Secrets';
    leaves[1].textContent = 'Goldfinch vault key';
    var extra = leaves[1].cloneNode(true); extra.textContent = 'Home address';
    leaves[1].parentNode.insertBefore(extra, leaves[1].nextSibling);
    grp.parentNode.insertBefore(c, grp.nextSibling);
  }

  // ── Routing glue ────────────────────────────────────────────────
  function openSecret(mode, idx) {
    st.secret = { mode: mode, idx: idx, rendered: false };
    var target = '#library/providers/' + PID;
    if (location.hash !== target) location.hash = target;
  }
  function ensure() {
    var h = location.hash || '';
    try {
      if (h.indexOf('#library') === 0 && q('[data-testid=library-list] .ui-list-pane-body .ui-list-pane-group') && !q('[data-s10-group]')) {
        libraryGroup(); markSelected();
      }
      if (st.secret && h === '#library/providers/' + PID && q('#main-content .studio-section-content .editor-title')) {
        if (!st.secret.rendered || !q('[data-testid=save-secret-btn]')) {
          editor(st.secret.mode, st.secret.idx); st.secret.rendered = true; markSelected();
        }
      } else if (st.secret && h !== '#library/providers/' + PID) { st.secret = null; markSelected(); }
      if (/^#agents\/[^/]+\/tools/.test(h) && q('[data-testid=agent-tools-mcp-section]') && !q('[data-testid=agent-tools-secrets-section]')) {
        toolsTab();
      }
      if (h.indexOf('#chats/') === 0 && q('#chat-drawer') && !q('[data-s10-drawer]')) drawer();
    } catch (e) { console.warn('s10 mockup', e); }
  }
  function panel() {
    var p = document.createElement('div');
    p.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:9999;background:var(--surface);border:1px solid var(--border);' +
      'border-radius:8px;padding:10px 12px;box-shadow:var(--shadow-popover);font-size:12px;display:flex;flex-direction:column;gap:6px;max-width:220px';
    var t = document.createElement('strong'); t.textContent = 'Sortie 10 mockup · round 2'; p.appendChild(t);
    function b(label, fn) { var x = document.createElement('button'); x.type = 'button'; x.className = 'btn-secondary btn-sm'; x.textContent = label; x.onclick = fn; p.appendChild(x); }
    b('Secret: Home address', function () { openSecret('edit', 2); });
    b('Secret: new (refused)', function () { openSecret('create', null); });
    b('Agent Tools tab', function () { location.hash = '#agents/browser-helper/tools'; });
    b('Chat transcript + drawer', function () { location.hash = '#chats/' + SID; });
    b('Toggle light/dark', function () { var r = document.documentElement; r.setAttribute('data-theme', r.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'); });
    document.body.appendChild(p);
  }
  function start() { panel(); setInterval(ensure, 300); }
  if (document.readyState === 'complete') start(); else window.addEventListener('load', start);
  window.S10M = { openSecret: openSecret };
})();
