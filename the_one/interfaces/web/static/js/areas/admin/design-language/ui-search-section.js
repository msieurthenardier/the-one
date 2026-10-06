(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.searchList (M25 F4 L1, DD14): the picker-shaped list. Twelve
  // sample agents: with an empty query, "Recently used" (five, in recency
  // order) then "All agents" (all twelve, A-Z, repeating the recent ones as
  // the reference draws); with a query, one "{n} matching" group A-Z. Each
  // row has a provider dot lead, a description and the model in mono. A
  // second list starts on a query that matches nothing, to show the empty
  // state. A pick is echoed in a caption; nothing navigates. Built twice
  // (one per theme pane), so no test ids here: the chooser demo in the modal
  // section carries the registered ones.
  var el = App.ui.util.el;

  var AGENTS = [
    { id: 'research', label: 'Research assistant', description: 'Finds and summarises papers.', model: 'claude-sonnet-4-5', type: 'anthropic-plan' },
    { id: 'reviewer', label: 'Code reviewer', description: 'Reviews diffs for correctness.', model: 'gpt-4.1-mini', type: 'openai' },
    { id: 'planner', label: 'Planner', description: 'Turns goals into a week of tasks.', model: 'llama3.1:8b', type: 'ollama' },
    { id: 'translator', label: 'Translator', description: 'Translates between eight languages.', model: 'claude-sonnet-4-5', type: 'anthropic-plan' },
    { id: 'sql', label: 'SQL helper', description: 'Writes and explains queries.', model: 'gpt-4.1-mini', type: 'openai' },
    { id: 'archivist', label: 'Archivist', description: 'Files notes into the team wiki.', model: 'llama3.1:8b', type: 'ollama' },
    { id: 'billing', label: 'Billing helper', description: 'Answers invoice questions.', model: 'claude-sonnet-4-5', type: 'anthropic-plan' },
    { id: 'copy', label: 'Copy editor', description: 'Tightens prose without changing meaning.', model: 'gpt-4.1-mini', type: 'openai' },
    { id: 'debugger', label: 'Debugger', description: 'Reads stack traces and suggests fixes.', model: 'llama3.1:8b', type: 'ollama' },
    { id: 'triage', label: 'Email triage', description: 'Sorts the inbox into four piles.', model: 'claude-sonnet-4-5', type: 'anthropic-plan' },
    { id: 'tutor', label: 'Tutor', description: 'Explains a topic step by step.', model: 'gpt-4.1-mini', type: 'openai' },
    { id: 'digest', label: 'Weekly digest', description: 'Writes the Friday summary.', model: 'llama3.1:8b', type: 'ollama' }
  ];
  var RECENT = ['translator', 'research', 'sql', 'planner', 'reviewer'];

  function byLabel(a, b) {
    return a.label.localeCompare(b.label);
  }

  function item(agent) {
    var dot = el('span', { className: 'badge badge--' + agent.type + ' badge-dot' });
    return {
      id: agent.id,
      label: agent.label,
      description: agent.description,
      meta: agent.model,
      metaMono: true,
      lead: dot
    };
  }

  function source(query) {
    var q = query.trim().toLowerCase();
    var i;
    if (!q) {
      var recent = [];
      for (i = 0; i < RECENT.length; i++) {
        for (var j = 0; j < AGENTS.length; j++) {
          if (AGENTS[j].id === RECENT[i]) recent.push(item(AGENTS[j]));
        }
      }
      return [
        { id: 'recent', label: 'Recently used', items: recent },
        { id: 'all', label: 'All agents', items: AGENTS.slice().sort(byLabel).map(item) }
      ];
    }
    var hits = [];
    for (i = 0; i < AGENTS.length; i++) {
      var a = AGENTS[i];
      var hay = (a.label + ' ' + a.model + ' ' + a.type + ' ' + a.description).toLowerCase();
      if (hay.indexOf(q) !== -1) hits.push(a);
    }
    return [{ id: 'matching', label: hits.length + ' matching', items: hits.sort(byLabel).map(item) }];
  }

  function emptyText(query) {
    return 'No agents match "' + query.trim() + '".';
  }

  function column(children, short) {
    var cls = 'design-language-ui-column design-language-ui-column--search';
    return el('div', { className: short ? cls + ' design-language-ui-column--short' : cls }, children);
  }

  function render(host) {
    var d = App.admin.designLanguage.uiDemo;

    d.demo(host, 'searchList', function (pane, theme) {
      var picked = el('span', { className: 'design-language-caption', text: 'Picked: nothing yet' });
      var list = App.ui.searchList({
        label: 'Find an agent (' + theme + ')',
        placeholder: 'Find an agent by name, model or provider',
        source: source,
        emptyText: emptyText,
        onPick: function (picked_) {
          picked.textContent = 'Picked: ' + picked_.label;
        }
      });
      pane.appendChild(d.caption('groups, active row, keyboard and pointer'));
      pane.appendChild(column([list.el]));
      pane.appendChild(picked);

      var none = App.ui.searchList({
        label: 'Find an agent, empty result (' + theme + ')',
        placeholder: 'Find an agent by name, model or provider',
        source: source,
        emptyText: emptyText
      });
      none.input.value = 'zzz';
      none.refresh();
      pane.appendChild(d.caption('empty result'));
      pane.appendChild(column([none.el], true));
    });
  }

  window.App.admin.designLanguage.uiSearchSection = { render: render };
})();
