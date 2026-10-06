(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.listPane: groups, selection, filter, badges, count, density
  // regular and compact, and the empty state; plus (M25 F3 L1) an Agents-style
  // pane (title count, filter, the agents row style, a name suffix, 32 rows in
  // a scrolling 300px column) and a Library-style pane (intro, the library row
  // style, three groups with ids and one empty, and -- M25 F3 L4a -- a button
  // that calls scrollToGroup('connectors')). Rows are buttons (onSelect), so the
  // page never navigates. App.ui.rail and App.ui.navGroups are demonstrated
  // here too (links to the in-page skip target, so the demos never route).
  // M25 F4 L1 (DD5): a Chats-style pane -- rowStyle 'chats' (title and time,
  // agent name and a platform badge), the New chat button in the header block
  // slot, a pending row (no action, data-pending), and a per-row delete action
  // driving App.confirmDelete; a confirmed delete removes the row.
  function noop() {}

  var CHATS = [
    { group: 'Today', id: 'c-pending', label: 'New chat', time: 'now', meta: 'Research assistant', pending: true },
    { group: 'Today', id: 'c-1', label: 'Summarise the Q3 paper backlog', time: '10:42', meta: 'Research assistant' },
    { group: 'Today', id: 'c-2', label: 'Review the session-store diff', time: '09:15', meta: 'Code reviewer' },
    { group: 'Yesterday', id: 'c-3', label: '#help: install on Windows', time: 'Sun', meta: 'Support drafter',
      badge: 'discord' },
    { group: 'Last 7 days', id: 'c-4', label: 'Plan the release week', time: 'Fri', meta: 'Planner' },
    { group: 'Last 7 days', id: 'c-5', label: 'A very long conversation title that has to ellipsize in the column',
      time: 'Thu', meta: 'Translator' }
  ];

  function chatGroups(rows, onDelete) {
    var order = ['Today', 'Yesterday', 'Last 7 days'];
    var groups = [];
    for (var g = 0; g < order.length; g++) {
      var items = [];
      for (var i = 0; i < rows.length; i++) {
        var r = rows[i];
        if (r.group !== order[g]) continue;
        var it = { id: r.id, label: r.label, time: r.time, meta: r.meta, onSelect: noop,
          dataset: r.pending ? { id: r.id, pending: 'true' } : { id: r.id } };
        if (r.badge) it.badges = [r.badge];
        if (!r.pending) it.action = { label: 'Delete chat: ' + r.label, icon: 'trash', onClick: onDelete };
        items.push(it);
      }
      if (items.length) groups.push({ id: order[g], label: order[g], items: items });
    }
    return groups;
  }

  var AGENT_NAMES = [
    'Archivist', 'Billing helper', 'Brainstormer', 'Calendar keeper', 'Changelog writer',
    'Code reviewer', 'Copy editor', 'Data wrangler', 'Debugger', 'Doc searcher',
    'Email triage', 'Grant writer', 'Incident scribe', 'Interview prep', 'Lab notebook',
    'Legal reader', 'Meeting notes', 'Migration planner', 'Onboarding guide', 'Paper summariser',
    'Planner', 'Proofreader', 'Release captain', 'Research assistant', 'Recipe scaler',
    'SQL helper', 'Support drafter', 'Test author', 'Translator', 'Travel planner',
    'Tutor', 'Weekly digest'
  ];
  var MODELS = [
    { model: 'claude-sonnet-4-5', provider: 'Claude Max', type: 'anthropic-plan' },
    { model: 'gpt-4.1-mini', provider: 'OpenAI', type: 'openai' },
    { model: 'llama3.1:8b', provider: 'Local Ollama', type: 'ollama' }
  ];

  // The Agents-style rows: the provider dot as item.lead (aria-hidden), the
  // model id as meta, the provider named only in the accessible name
  // (nameSuffix, with a trailing separator so the name reads "name, provider,
  // model"), sorted A-Z as the Agents list is (M25 F3 L3).
  function agentItems() {
    var out = [];
    for (var i = 0; i < AGENT_NAMES.length; i++) {
      var m = MODELS[i % MODELS.length];
      var dot = App.ui.util.el('span', { className: 'badge badge--' + m.type + ' badge-dot' });
      dot.setAttribute('aria-hidden', 'true');
      out.push({ id: 'agent-' + i, label: AGENT_NAMES[i], meta: m.model,
        nameSuffix: ', ' + m.provider + ',', lead: dot, onSelect: noop });
    }
    return out.sort(function (a, b) { return a.label.localeCompare(b.label); });
  }

  function column(modifier, children) {
    return App.ui.util.el('div', {
      className: 'design-language-ui-column' + (modifier ? ' design-language-ui-column--' + modifier : '')
    }, children);
  }

  function items(prefix) {
    return [
      { id: prefix + '-a', label: 'Alpha', meta: 'First row', onSelect: noop,
        badges: [{ text: 'openai', kind: 'openai' }], count: 3 },
      { id: prefix + '-b', label: 'Beta', meta: 'Second row', onSelect: noop,
        badges: ['plain'], count: 12 },
      { id: prefix + '-c', label: 'Gamma', onSelect: noop }
    ];
  }

  function render(host) {
    var d = App.admin.designLanguage.uiDemo;
    var ui = App.ui;

    d.demo(host, 'listPane', function (pane, theme) {
      var regular = ui.listPane({
        title: 'Regular (' + theme + ')',
        filter: { label: 'Filter regular list', placeholder: 'Filter' },
        selectedId: 'r-b',
        items: items('r')
      });
      pane.appendChild(regular.el);

      var grouped = ui.listPane({
        title: 'Grouped (' + theme + ')',
        density: 'compact',
        selectedId: 'g-1',
        groups: [
          { label: 'Group one', items: [
            { id: 'g-1', label: 'Selected row', onSelect: noop, count: 2 },
            { id: 'g-2', label: 'Another row', onSelect: noop }
          ] },
          { label: 'Group two', items: [
            { id: 'g-3', label: 'Third row', onSelect: noop,
              badges: [{ text: 'approved', kind: 'approved' }] }
          ] }
        ]
      });
      pane.appendChild(grouped.el);

      var empty = ui.listPane({
        title: 'Empty (' + theme + ')',
        emptyText: 'No items yet',
        items: []
      });
      pane.appendChild(empty.el);

      var agents = ui.listPane({
        title: 'Agents (' + theme + ')',
        count: true,
        rowStyle: 'agents',
        actions: [ui.button({ label: 'New', size: 'sm', icon: 'plus' })],
        filter: { label: 'Filter agents-style list (' + theme + ')',
          placeholder: 'Filter by name, model or provider' },
        emptyText: 'No agents match',
        selectedId: 'agent-23',
        items: agentItems()
      });
      pane.appendChild(column('list', [agents.el]));

      // The Library list's icons: database, server and plug (M25 F3 L4a).
      var kbItems = [];
      var KB_NAMES = ['Design docs', 'Handbook', 'Incident log', 'Release notes', 'Research papers',
        'Support archive', 'Team wiki'];
      for (var k = 0; k < KB_NAMES.length; k++) {
        kbItems.push({ id: 'kb-' + k, label: KB_NAMES[k], meta: (k + 1) + ' agents', icon: 'database',
          onSelect: noop });
      }
      var library = ui.listPane({
        title: 'Library (' + theme + ')',
        intro: 'Things agents can use. Attach them from an agent\'s Knowledge and MCPs tabs.',
        rowStyle: 'library',
        actions: [ui.button({ label: 'Add', size: 'sm', icon: 'plus' })],
        selectedId: 'kb-5',
        groups: [
          { id: 'knowledge', label: 'Knowledge bases', emptyText: 'No knowledge bases yet.', items: kbItems },
          { id: 'mcp', label: 'MCP servers', emptyText: 'No MCP servers yet.', items: [] },
          { id: 'connectors', label: 'Connectors', emptyText: 'No connectors yet.', items: [
            { id: 'cn-1', label: 'Team chat', meta: '1 agent', icon: 'plug', onSelect: noop }
          ] }
        ]
      });
      var toGroup = ui.button({
        label: 'Scroll to Connectors',
        size: 'sm',
        onClick: function () { library.scrollToGroup('connectors'); }
      });
      pane.appendChild(column('list', [library.el]));
      pane.appendChild(toGroup);

      var rows = CHATS.slice();
      var chats = null;
      function onDelete(item, actionEl, li) {
        App.confirmDelete(li, function () {
          rows = rows.filter(function (r) { return r.id !== item.id; });
          chats.setItems(chatGroups(rows, onDelete));
        });
      }
      chats = ui.listPane({
        title: 'Chats (' + theme + ')',
        rowStyle: 'chats',
        block: ui.button({ label: 'New chat', variant: 'primary', size: 'lg', icon: 'square-pen' }),
        selectedId: 'c-pending',
        groups: chatGroups(rows, onDelete)
      });
      pane.appendChild(column('list', [chats.el]));
    });

    // App.ui.rail: a non-routing demo. Every href is the in-page skip target
    // (#main-content, which the link interceptor leaves to the browser), the
    // second item is shown current statically, and the brand image carries
    // its accessible name. M25 F4 L7: the `footer` slot holds a 44px ghost
    // icon-only button pinned to the bottom (the shell's Jump to control);
    // here it does nothing. The rail stands in a 360px frame so the pinning
    // shows.
    d.demo(host, 'rail', function (pane, theme) {
      var rail = ui.rail({
        label: 'Rail demo (' + theme + ')',
        brand: { src: '/static/brand/topbar-icon-24.png', alt: 'GleepGlorp AI' },
        currentId: 'agents',
        items: [
          { id: 'chats', label: 'Chats', icon: 'chat', href: '#main-content' },
          { id: 'agents', label: 'Agents', icon: 'studio', href: '#main-content' },
          { id: 'library', label: 'Library', icon: 'database', href: '#main-content' },
          { id: 'settings', label: 'Settings', icon: 'admin', href: '#main-content' }
        ],
        footer: [ui.button({ variant: 'ghost', icon: 'search', iconOnly: true, ariaLabel: 'Jump to (demo)' })]
      });
      rail.el.style.height = '360px';
      pane.appendChild(d.row([rail.el]));
    });

    // App.ui.navGroups: the Settings nav's four groups with one item selected,
    // in a 260px column carrying the host padding. Every href is the in-page
    // skip target, so the demo never routes.
    d.demo(host, 'navGroups', function (pane, theme) {
      var nav = ui.navGroups({
        label: 'Settings demo (' + theme + ')',
        heading: 'Settings',
        selectedId: 'providers',
        groups: [
          { label: 'General', items: [
            { id: 'appearance', label: 'Appearance', href: '#main-content' },
            { id: 'prompts', label: 'Prompts', href: '#main-content' },
            { id: 'encryption', label: 'Encryption', href: '#main-content' }
          ] },
          { label: 'Models', items: [
            { id: 'providers', label: 'Providers', href: '#main-content' }
          ] },
          { label: 'Defaults for agents', items: [
            { id: 'tools', label: 'Built-in tools', href: '#main-content' },
            { id: 'knowledge-indexing', label: 'Knowledge indexing', href: '#main-content' }
          ] },
          { label: 'Developer', items: [
            { id: 'design-language', label: 'Design language', href: '#main-content' }
          ] }
        ]
      });
      pane.appendChild(column('nav', [nav.el]));
    });
  }

  window.App.admin.designLanguage.uiListsSection = { render: render };
})();
