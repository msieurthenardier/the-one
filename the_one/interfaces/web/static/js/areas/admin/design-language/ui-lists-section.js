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
  function noop() {}

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
    });

    // App.ui.rail: a non-routing demo. Every href is the in-page skip target
    // (#main-content, which the link interceptor leaves to the browser), the
    // second item is shown current statically, and the brand image carries
    // its accessible name.
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
        ]
      });
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
