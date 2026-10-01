// App.studio.renderKnowledgeTab — agent-editor Knowledge tab content
// (Mission 24, Flight 6, Leg 3; DD-2, DD-3, DD-4, L3-D1, L3-D2).
//
// Replaces the F5 stub. Attach-only surface: lists every existing
// knowledge base with a toggle, checked for ids already in the agent's
// `kb_ids`. Creating a knowledge base happens in Studio's Knowledge
// section (knowledge-section.js) — this tab never creates one (DD-2).
//
// Public API:
//   App.studio.renderKnowledgeTab(panel, agent, allKnowledgeBases, callbacks)
//     panel              — DOM element (the Knowledge tabpanel)
//     agent              — AgentConfig object (may be null for create-mode)
//     allKnowledgeBases  — array of KnowledgeBase objects (studio.js's
//                          self._allKnowledgeBases, refreshed on every
//                          agent-edit mount — L3-D1/DD-15)
//     callbacks          — { onChange, knowledgeBasesLoaded }
//                          `knowledgeBasesLoaded` is the explicit L3-D1
//                          load-success flag — NOT inferred from
//                          `allKnowledgeBases` being null/empty, because a
//                          populated array can be a stale cache kept after
//                          a failed refresh (DD-15).
//
// Save-flow selector (collected by studio.js::collectFormData):
//   [data-kb-toggle][data-kb-id]:checked → kb_ids
//   Gated on the root's `data-kb-list-loaded="true"` marker (DD-4), which
//   this module sets ONLY when `callbacks.knowledgeBasesLoaded === true`.
//   When the marker is absent, collectFormData omits `kb_ids` from the
//   PUT body entirely and the server-side preserve (Leg 2's AC-7) keeps
//   the stored value — this is what makes a failed refresh fail closed
//   instead of squawk 0050's `kb_ids: []` wipe.
//
// L3-D2 — the derived knowledge-base search tool name is READ from
// `agent.kb_tool_names[kb.id]` (Leg 2's server-computed field), never
// recomputed here. A knowledge base with no entry (not attached, or
// `agent` is null in create-mode) renders an explicit placeholder — never
// a guessed name.
//
// Built entirely via document.createElement + textContent/setAttribute —
// this is a brand-new file with no `tests/test_ui_guards.py` dynamic-sink
// baseline entry, so even a static-literal-concatenation innerHTML site
// (mcps-tab.js's empty-state precedent) would fail the guard here. Mirrors
// knowledge-section.js's `_el` helper rather than mcps-tab.js's innerHTML
// style.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function _el(tag, opts) {
    var e = document.createElement(tag);
    opts = opts || {};
    if (opts.className) e.className = opts.className;
    if (opts.text !== undefined) e.textContent = opts.text;
    return e;
  }

  function renderKnowledgeTab(panel, agent, allKnowledgeBases, callbacks) {
    callbacks = callbacks || {};
    var onChange = callbacks.onChange || function () {};
    var loaded = callbacks.knowledgeBasesLoaded === true;

    panel.textContent = '';

    var root = _el('div', { className: 'agent-knowledge-tab' });
    root.setAttribute('data-testid', 'agent-knowledge-tab');
    panel.appendChild(root);

    if (!loaded) {
      // L3-D1/DD-15: refuse to present stale attachment state as current.
      // No `data-kb-list-loaded` marker here — collectFormData reads its
      // absence and omits `kb_ids` from the save payload.
      var errEl = _el('div', {
        className: 'agent-knowledge-load-error',
        text: 'Couldn’t load knowledge bases. Saving will leave this agent’s attachments unchanged.'
      });
      errEl.setAttribute('data-testid', 'agent-knowledge-load-error');
      root.appendChild(errEl);
      return;
    }

    root.setAttribute('data-kb-list-loaded', 'true');

    var kbs = allKnowledgeBases || [];
    if (kbs.length === 0) {
      // Edge case: a genuinely empty inventory still sets the marker (the
      // fetch succeeded) so a save correctly sends `kb_ids: []`.
      var emptyEl = _el('div', {
        className: 'empty-state agent-knowledge-empty-state',
        text: 'No knowledge bases yet. '
      });
      emptyEl.setAttribute('data-testid', 'agent-knowledge-empty-state');
      var link = document.createElement('a');
      link.href = App.router.href({ destination: 'library', section: 'knowledge' });
      link.textContent = 'Create one in Knowledge.';
      emptyEl.appendChild(link);
      root.appendChild(emptyEl);
      return;
    }

    var attachedIds = {};
    if (agent && agent.kb_ids) {
      for (var a = 0; a < agent.kb_ids.length; a++) attachedIds[agent.kb_ids[a]] = true;
    }
    // L3-D2: the only read of the server-derived tool name. `agent` is
    // null in create-mode, so `toolNames` is `{}` and every row falls
    // back to the placeholder — correct, since a brand-new agent has no
    // stored attachments to derive a name from.
    var toolNames = (agent && agent.kb_tool_names) || {};

    var listEl = _el('div', { className: 'agent-knowledge-list' });
    listEl.setAttribute('data-testid', 'agent-knowledge-list');
    root.appendChild(listEl);

    for (var i = 0; i < kbs.length; i++) {
      (function (kb) {
        var row = _el('div', { className: 'agent-knowledge-row' });
        row.setAttribute('data-testid', 'agent-knowledge-row-' + kb.id);
        row.setAttribute('data-kb-id', kb.id);

        var toggleLabel = _el('label', { className: 'agent-knowledge-row-toggle' });
        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'tool-toggle';
        checkbox.setAttribute('data-kb-toggle', '');
        checkbox.setAttribute('data-kb-id', kb.id);
        checkbox.setAttribute('data-testid', 'agent-knowledge-toggle-' + kb.id);
        checkbox.checked = attachedIds[kb.id] === true;
        checkbox.addEventListener('change', function () { onChange(); });
        toggleLabel.appendChild(checkbox);

        var visualSwitch = _el('span', { className: 'tool-switch' });
        toggleLabel.appendChild(visualSwitch);

        var nameSpan = _el('span', { className: 'agent-knowledge-row-name', text: kb.name });
        toggleLabel.appendChild(nameSpan);

        row.appendChild(toggleLabel);

        var toolNameText = toolNames[kb.id];
        var toolNameSpan = _el('span', { className: 'agent-knowledge-row-tool-name' });
        toolNameSpan.setAttribute('data-testid', 'agent-knowledge-tool-name-' + kb.id);
        if (toolNameText) {
          toolNameSpan.textContent = toolNameText;
        } else {
          // L3-D2 / edge case: no fallback derivation — an explicit
          // placeholder, never a guessed name. Reached for an unattached
          // knowledge base, an attached one the server didn't resolve
          // (stale `kb_tool_names`), or any row in create-mode.
          toolNameSpan.classList.add('agent-knowledge-row-tool-name-placeholder');
          toolNameSpan.textContent = 'attach to see the tool name';
        }
        row.appendChild(toolNameSpan);

        listEl.appendChild(row);
      })(kbs[i]);
    }
  }

  window.App.studio.renderKnowledgeTab = renderKnowledgeTab;
})();
