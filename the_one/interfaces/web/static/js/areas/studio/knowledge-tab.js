// App.studio.renderKnowledgeTab — agent-editor Knowledge tab content
// (Mission 24, Flight 6, Leg 3; rebuilt on the control library in M31 F2 L07a).
//
// Attach-only surface: lists every existing knowledge base with an App.ui.toggle
// (a native checkbox with role=switch, reachable by role and by Tab; squawk 0094),
// checked for ids already in the agent's `kb_ids`. Creating a knowledge base
// happens in the Library — this tab never creates one (DD-2).
//
// Public API:
//   var h = App.studio.renderKnowledgeTab(panel, agent, allKnowledgeBases, callbacks)
//     panel              — the Knowledge tabpanel
//     agent              — AgentConfig (null in create mode)
//     allKnowledgeBases  — array of KnowledgeBase objects
//     callbacks          — { onChange, knowledgeBasesLoaded }
//                          `onChange` is the editor's dirty callback, called from each
//                          switch's own onChange (the editor's field-level listener
//                          sweep does not see library inputs).
//                          `knowledgeBasesLoaded` is the explicit L3-D1 load-success flag
//                          (NOT inferred from the array: a populated array can be a stale
//                          cache kept after a failed refresh, DD-15).
//   h = { setAgent(agent, opts), destroy() }. Mounted once per agent identity;
//   setAgent patches in place: each switch's checked state from `agent.kb_ids` and
//   each tool-name node from `agent.kb_tool_names`; it does not rebuild. `opts`
//   ({allKnowledgeBases, knowledgeBasesLoaded}) lets a refreshed inventory in: only
//   when the loaded flag or the set of knowledge-base ids differs from what is built
//   does the tab rebuild its own content (the list itself changed).
//
// Save-flow selector (collected by agent-form-data.js):
//   [data-kb-toggle][data-kb-id]:checked → kb_ids, on the input.
//   Gated on the root's `data-kb-list-loaded="true"` marker (DD-4), set ONLY when the
//   load flag is true. Without it `kb_ids` is omitted from the PUT body and the server
//   keeps the stored value, so a failed refresh fails closed (squawk 0050).
//
// L3-D2 — the derived search tool name is READ from `agent.kb_tool_names[kb.id]`,
// never recomputed here; a knowledge base with no entry shows an explicit placeholder.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var PLACEHOLDER = 'attach to see the tool name';

  function renderKnowledgeTab(panel, agent, allKnowledgeBases, callbacks) {
    callbacks = callbacks || {};
    var ui = window.App.ui;
    var onChange = callbacks.onChange || function () {};
    var rows = {};     // kb id -> { toggle, toolNameEl }
    var builtIds = null;
    var builtLoaded = null;

    function ids(list) {
      var out = [];
      for (var i = 0; i < (list || []).length; i++) out.push(list[i].id);
      return out.join('\n');
    }

    function setToolName(el, name) {
      if (name) {
        el.textContent = name;
        el.classList.remove('agent-knowledge-row-tool-name-placeholder');
      } else {
        // L3-D2 / edge case: no fallback derivation, an explicit placeholder.
        el.textContent = PLACEHOLDER;
        el.classList.add('agent-knowledge-row-tool-name-placeholder');
      }
    }

    function patchRows(a) {
      var attached = {};
      var kbIds = (a && a.kb_ids) || [];
      for (var i = 0; i < kbIds.length; i++) attached[kbIds[i]] = true;
      var names = (a && a.kb_tool_names) || {};
      Object.keys(rows).forEach(function (id) {
        rows[id].toggle.setChecked(attached[id] === true);
        setToolName(rows[id].toolNameEl, names[id]);
      });
    }

    function build(a, kbs, loaded) {
      panel.textContent = '';
      rows = {};
      builtIds = ids(kbs);
      builtLoaded = loaded;

      var root = document.createElement('div');
      root.className = 'agent-knowledge-tab';
      root.setAttribute('data-testid', 'agent-knowledge-tab');
      panel.appendChild(root);

      if (!loaded) {
        // L3-D1/DD-15: refuse to present stale attachment state as current. No
        // `data-kb-list-loaded` marker: the form data omits `kb_ids` from the save.
        var err = ui.status({ testid: 'agent-knowledge-load-error' });
        err.set('danger',
          'Couldn’t load knowledge bases. Saving will leave this agent’s attachments unchanged.');
        root.appendChild(err.el);
        return;
      }

      root.setAttribute('data-kb-list-loaded', 'true');

      if (!kbs || kbs.length === 0) {
        // A genuinely empty inventory still sets the marker (the fetch succeeded), so
        // a save correctly sends `kb_ids: []`.
        var link = document.createElement('a');
        link.href = App.router.href({ destination: 'library' });
        link.textContent = 'Create one in Knowledge.';
        root.appendChild(ui.emptyState({
          title: 'No knowledge bases yet.',
          titleTag: 'p',
          action: link,
          testid: 'agent-knowledge-empty-state'
        }));
        return;
      }

      var listEl = document.createElement('div');
      listEl.className = 'agent-knowledge-list';
      listEl.setAttribute('data-testid', 'agent-knowledge-list');
      root.appendChild(listEl);

      kbs.forEach(function (kb) {
        var row = document.createElement('div');
        row.className = 'agent-knowledge-row';
        row.setAttribute('data-testid', 'agent-knowledge-row-' + kb.id);
        row.setAttribute('data-kb-id', kb.id);

        var toggle = ui.toggle({
          label: kb.name,
          dataset: { kbToggle: '', kbId: kb.id },
          testid: 'agent-knowledge-toggle-' + kb.id,
          onChange: function () { onChange(); }
        });
        row.appendChild(toggle.el);

        var toolNameEl = document.createElement('span');
        toolNameEl.className = 'agent-knowledge-row-tool-name';
        toolNameEl.id = ui.util.uid('kbtool');
        toolNameEl.setAttribute('data-testid', 'agent-knowledge-tool-name-' + kb.id);
        toggle.control.setAttribute('aria-describedby', toolNameEl.id);
        row.appendChild(toolNameEl);

        rows[kb.id] = { toggle: toggle, toolNameEl: toolNameEl };
        listEl.appendChild(row);
      });
      patchRows(a);
    }

    build(agent, allKnowledgeBases, callbacks.knowledgeBasesLoaded === true);

    return {
      setAgent: function (a, opts) {
        var kbs = allKnowledgeBases;
        var loaded = callbacks.knowledgeBasesLoaded === true;
        if (opts) {
          if (opts.allKnowledgeBases !== undefined) kbs = opts.allKnowledgeBases;
          if (opts.knowledgeBasesLoaded !== undefined) loaded = opts.knowledgeBasesLoaded === true;
        }
        allKnowledgeBases = kbs;
        callbacks.knowledgeBasesLoaded = loaded;
        if (loaded !== builtLoaded || ids(kbs) !== builtIds) {
          build(a, kbs, loaded);
          return;
        }
        patchRows(a);
      },
      // The follow-through for an approved change (M36 F2 L8). followMap is null while the list
      // has not loaded: nothing is set and the next load takes the stored value.
      followMap: function () {
        if (!builtLoaded) return null;
        var m = {};
        Object.keys(rows).forEach(function (id) { m[id] = !!rows[id].toggle.control.checked; });
        return m;
      },
      followMapFor: function (cfg) {
        var on = {};
        ((cfg && cfg.kb_ids) || []).forEach(function (id) { on[id] = true; });
        var m = {};
        Object.keys(rows).forEach(function (id) { m[id] = on[id] === true; });
        return m;
      },
      followSet: function (map, names) {
        Object.keys(rows).forEach(function (id) {
          if (Object.prototype.hasOwnProperty.call(map, id)) rows[id].toggle.setChecked(!!map[id]);
          if (names) setToolName(rows[id].toolNameEl, names[id]);
        });
      },
      followPlace: function (id, note) {
        var r = rows[id];
        var row = r && r.toggle.el.parentNode;
        if (row && row.parentNode) row.parentNode.insertBefore(note, row.nextSibling);
      },
      destroy: function () { panel.textContent = ''; rows = {}; }
    };
  }

  window.App.studio.renderKnowledgeTab = renderKnowledgeTab;
})();
