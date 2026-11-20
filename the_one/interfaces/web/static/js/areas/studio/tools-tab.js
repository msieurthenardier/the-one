// App.studio.renderToolsTab -- agent-editor Built-in tools tab (F5 leg 03, F6 leg 05;
// rebuilt on the control library in M31 F2 L08b, flight DD3/DD6).
//
//   var h = App.studio.renderToolsTab(panel, agent, callbacks)
//     -> { setAgent(agent, opts), setNotices(notices), fieldHandles(), openTool(name), destroy() }
//   setNotices(notices) redraws only each tool row's "{n} notice(s)" flag (sortie 07 L05,
//   DD11), from agent.notices; it never touches a field value.
//   fieldHandles() -> { tool: { field: handle } } for the loaded panels (App.toolConfigFields
//   agent-mode handles: isOwn(), ownValue(), reset(), rebase(), setError(), focus()); the
//   Save walk and the 422 mapping read them. openTool(name) opens a tool's panel and
//   resolves once its fields are rendered (rejects for a tool with no panel).
//   A field is the agent's own when its key is in the stored override, inherited otherwise
//   (sortie 07, DD9); the clipped-field line comes from agent.notices, and the paths note
//   from App.config.execution_sandbox.
//
// Built once per agent identity and patched through setAgent (DD6). One
// App.ui.groupTile per category (data-category on its root; a tristate master,
// dataset categoryMaster, aria-label "Enable all {Category} tools"; the count chip
// "N / M enabled") holding one App.ui.toolRow per tool (inputDataset tool: the
// checkbox collectFormData reads; a "Overrides" disclosure on every operator-enabled
// tool). The disclosure body is filled lazily on the first open from the tool's
// schema by App.toolConfigFields (js/areas/shared/tool-config-fields.js, agent mode).
//
// Save flows through agent-form-data.js::collectFormData: the checkboxes
// `input[type=checkbox][data-tool]` give enabled_tools/disabled_tools and the
// `[data-tool-override-tool][data-tool-override-field]` controls give tool_overrides.
// A tool whose body was never opened has no controls, so collectFormData omits it
// (squawk 0223: the stored entry survives).
//
// setAgent(agent, opts): updates every row's checked state, the masters and the
// counts from the agent. Loaded override bodies are KEPT (after a Save their values
// equal the stored ones, and an open disclosure with focus inside survives). With
// opts.revert (Cancel) every loaded body is dropped, the disclosure closed and the
// lazy load re-armed, so the next open renders the stored values. opts.disabledTools
// / opts.operatorConfigs / opts.fetchToolSchema refresh the operator state; a changed
// disabled set rebuilds the tab's own content.
//
// Dirty tracking: the library inputs are not seen by the editor's field-level
// listener sweep, so each master's and row's own onChange calls callbacks.onChange,
// and so does every override control.
//
// callbacks:
//   - toolCategories: {category: [tool_name, ...]}
//   - allTools: [{name, description}, ...]
//   - onChange: () -> void (the editor's dirty callback)
//   - disabledTools: Set<string> (operator-disabled tool names)
//   - operatorConfigs: {name: {enabled, config}} (the ceiling for Narrow widgets)
//   - fetchToolSchema: (name) -> Promise<{schema, ...}> (closure-cached by the controller)
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var INTRO_TEXT =
    'Built-in tools the agent can load. Enabling a tool adds it to the set ' +
    'the agent is allowed to use — the agent loads each tool on demand during ' +
    'a run, not all at once. The count shows how many in a category are enabled.';

  var TIME_NOTE =
    'Always available to the agent from the start of every conversation, ' +
    'even if you limit its other tools. Untick to remove it from this agent.';

  // Shell, Python and downloads are not limited by an agent's paths (sortie 07, DD10).
  var PATHS_NOTE_TOOLS = ['shell', 'python_exec', 'shell_session_start', 'download_file'];
  var PATH_FIELDS = ['path_allowlist', 'path_denylist'];
  var PATHS_NOTES = {
    bubblewrap:
      'Shell, Python and downloads don\'t use this agent\'s paths. Without host access, ' +
      'Shell and Python run in an empty sandbox; with host access, and for downloads, ' +
      'read_file\'s app-wide paths apply. Turn them off for this agent to keep it to ' +
      'these paths.',
    passthrough:
      'On this computer, Shell and Python aren\'t limited by any paths, and downloads use ' +
      'read_file\'s app-wide paths. Turn them off for this agent to keep it to these paths.'
  };

  function setKey(set) {
    var out = [];
    if (set && typeof set.forEach === 'function') set.forEach(function (n) { out.push(n); });
    return out.sort().join('\n');
  }

  function renderToolsTab(panel, agent, callbacks) {
    callbacks = callbacks || {};
    var ui = window.App.ui;
    var TOOL_CATEGORIES = callbacks.toolCategories || {};
    var allTools = callbacks.allTools || [];
    var disabledTools = callbacks.disabledTools || new window.Set();
    var operatorConfigs = callbacks.operatorConfigs || {};
    var fetchToolSchema = callbacks.fetchToolSchema || null;
    var currentAgent = agent;
    var whitelistExempt =
      (window.App.toolCategories && window.App.toolCategories.whitelistExempt) || [];

    var tiles = {};   // category -> { tile, names: [..] }
    var rows = {};    // tool name -> { row, category, overrides: {open, rebase, reset, destroy} | null }
    var panels = {};  // tool name -> the loaded-state of its override panel (byField handles)
    var listeners = [];
    var listContainer = null;

    function onChange() {
      if (typeof callbacks.onChange === 'function') callbacks.onChange();
    }

    function isDisabled(name) {
      return !!(disabledTools && typeof disabledTools.has === 'function' && disabledTools.has(name));
    }

    function findTool(name) {
      for (var i = 0; i < allTools.length; i++) {
        if (allTools[i].name === name) return allTools[i];
      }
      return null;
    }

    // Which tools the agent has enabled (mirrors AgentConfig.is_tool_enabled).
    function enabledSetFor(a) {
      var cfg = a || { enabled_tools: null, disabled_tools: [] };
      var set = {};
      for (var i = 0; i < allTools.length; i++) {
        var tn = allTools[i].name;
        if (whitelistExempt.indexOf(tn) >= 0) {
          set[tn] = (cfg.disabled_tools || []).indexOf(tn) < 0;
        } else if (cfg.enabled_tools !== null && cfg.enabled_tools !== undefined) {
          set[tn] = cfg.enabled_tools.indexOf(tn) >= 0;
        } else {
          set[tn] = (cfg.disabled_tools || []).indexOf(tn) < 0;
        }
      }
      return set;
    }

    function refreshCategory(cat) {
      var entry = tiles[cat];
      if (!entry) return;
      var enabled = 0;
      for (var i = 0; i < entry.names.length; i++) {
        if (rows[entry.names[i]].row.input.checked) enabled++;
      }
      entry.tile.setCount(enabled + ' / ' + entry.names.length + ' enabled');
      entry.tile.setMaster(
        enabled === entry.names.length ? 'on' : (enabled === 0 ? 'off' : 'mixed')
      );
    }

    // ── The override disclosure of one tool ──────────────────────────
    function loadingNode() {
      var p = document.createElement('p');
      p.className = 'loading';
      p.textContent = 'Loading…';
      return p;
    }

    function clearNode(node) {
      while (node.firstChild) node.removeChild(node.firstChild);
    }

    // The row flag (sortie 07 L05, DD11): a warning chip "{n} notice(s)" when the tool
    // has notices, drawn from agent.notices at build and on setNotices, so a tool whose
    // disclosure was never opened is still flagged. It never touches a field.
    function noticeCount(toolName) {
      var list = (currentAgent && currentAgent.notices) || [];
      var n = 0;
      for (var i = 0; i < list.length; i++) if (list[i].tool === toolName) n++;
      return n;
    }

    function flagNode(toolName) {
      var n = noticeCount(toolName);
      if (!n) return null;
      return ui.chip({
        label: n + (n === 1 ? ' notice' : ' notices'),
        tone: 'warning',
        size: 'sm',
        testid: 'tool-override-notice-flag'
      });
    }

    function updateFlags() {
      Object.keys(rows).forEach(function (n) {
        var count = noticeCount(n);
        if (rows[n].flagCount === count) return;
        rows[n].flagCount = count;
        rows[n].row.setFlag(flagNode(n));
      });
    }

    function noticeFor(toolName, fieldName) {
      var list = (currentAgent && currentAgent.notices) || [];
      for (var i = 0; i < list.length; i++) {
        if (list[i].tool === toolName && list[i].field === fieldName) return list[i];
      }
      return null;
    }

    // The note on every Allowed paths / Denied paths field (DD10): Shell, Python and
    // downloads are not limited by this agent's paths. Shown only while one of those
    // tools is on for the agent AND app-wide, for a posture the server reported.
    function pathsNoteText() {
      var cfg = window.App.config || {};
      var posture = cfg.execution_sandbox;
      if (posture !== 'bubblewrap' && posture !== 'passthrough') return null;
      var text = PATHS_NOTES[posture];
      var set = enabledSetFor(currentAgent);
      for (var i = 0; i < PATHS_NOTE_TOOLS.length; i++) {
        var t = PATHS_NOTE_TOOLS[i];
        var on = rows[t] ? !!rows[t].row.input.checked : !!set[t];
        var oc = operatorConfigs[t];
        var appWide = !isDisabled(t) && !(oc && oc.enabled === false);
        if (on && appWide) return text;
      }
      return null;
    }

    function updatePathsNotes() {
      var text = pathsNoteText();
      Object.keys(panels).forEach(function (tn) {
        var byField = panels[tn].byField;
        PATH_FIELDS.forEach(function (fn) {
          if (byField[fn]) byField[fn].setNote(text);
        });
      });
    }

    function attachOverrides(name, row) {
      var st = { status: 'unloaded', gen: 0, fields: [], byField: {}, promise: null };
      var body = row.body;
      body.appendChild(loadingNode());
      panels[name] = st;

      function destroyFields() {
        for (var i = 0; i < st.fields.length; i++) {
          if (st.fields[i].chips) st.fields[i].chips.destroy();
        }
        st.fields = [];
        st.byField = {};
      }

      function showFailure() {
        clearNode(body);
        var status = ui.status({ live: 'polite' });
        status.set('danger', 'Failed to load schema.');
        body.appendChild(status.el);
      }

      function renderFields(detail) {
        var schema = (detail && detail.schema) || {};
        var fields = window.App.toolConfigFields;
        var operatorRow = operatorConfigs[name] || {};
        var operatorConfig = operatorRow.config || {};
        var agentOverride = ((currentAgent && currentAgent.tool_overrides) || {})[name] || {};
        var fieldNames = Object.keys(schema.properties || {});
        clearNode(body);
        destroyFields();
        var rendered = 0;
        var dead = [];
        for (var i = 0; i < fieldNames.length; i++) {
          var fname = fieldNames[i];
          var prop = schema.properties[fname];
          if (!fields.allowed(prop)) {
            // A stale override on a field the schema no longer marks overridable
            // is surfaced to the console (the resolver will reject it).
            if (fname in agentOverride) {
              // A Save drops it (agent-form-data.js reads the flag below).
              dead.push(fname);
              // eslint-disable-next-line no-console
              console.warn('Agent "%s" has an override on tool "%s" field "%s" but the schema no longer marks that field as overridable; the resolver will reject this.', (currentAgent && currentAgent.name) || '?', name, fname);
            }
            continue;
          }
          var operatorVal = (fname in operatorConfig) ? operatorConfig[fname] : prop['default'];
          var hasOwn = (fname in agentOverride);
          var built = fields.render(fname, prop, fields.seedValue(prop, agentOverride, fname, operatorVal), {
            mode: 'agent',
            toolName: name,
            operatorValue: operatorVal,
            own: hasOwn,
            storedValue: hasOwn ? agentOverride[fname] : undefined,
            notice: noticeFor(name, fname),
            onChange: onChange
          });
          if (!built) continue;
          body.appendChild(built.el);
          st.fields.push(built);
          st.byField[fname] = built;
          rendered++;
        }
        updatePathsNotes();
        // The panel names itself and any stored override the schema no longer marks
        // overridable, for agent-form-data.js (see its tool_overrides walk).
        body.setAttribute('data-tool-override-panel', name);
        if (dead.length) body.setAttribute('data-tool-override-dead', dead.join(' '));
        else body.removeAttribute('data-tool-override-dead');
        if (rendered === 0) {
          body.appendChild(ui.emptyState({ title: 'No constraints to narrow.', titleTag: 'p' }));
        }
      }

      // -> a promise settled once this panel's fields are rendered (rejected when the
      // schema failed to load). The toggle path ignores a rejection.
      function load() {
        st.status = 'loading';
        var gen = ++st.gen;
        st.promise = new Promise(function (resolve, reject) {
          fetchToolSchema(name).then(function (detail) {
            if (gen !== st.gen) { resolve(); return; }
            st.status = 'loaded';
            renderFields(detail);
            resolve();
          }, function (err) {
            if (gen !== st.gen) { resolve(); return; }
            // Retry on the next open.
            st.status = 'failed';
            showFailure();
            reject(err || new Error('schema'));
          });
        });
        st.promise.catch(function () { /* shown in the panel */ });
        return st.promise;
      }

      function onToggle() {
        if (!row.el.open) return;
        if (st.status === 'unloaded' || st.status === 'failed') {
          if (st.status === 'failed') {
            clearNode(body);
            body.appendChild(loadingNode());
          }
          load();
        }
      }
      if (fetchToolSchema) {
        row.el.addEventListener('toggle', onToggle);
        listeners.push(function () { row.el.removeEventListener('toggle', onToggle); });
      }

      return {
        // Open the disclosure and resolve once its fields are rendered (the panel's
        // own load path, so the schema is fetched like a click would).
        open: function () {
          if (!fetchToolSchema) return Promise.reject(new Error('no schema source'));
          if (st.status === 'loaded') {
            row.setOpen(true);
            return Promise.resolve();
          }
          if (st.status === 'loading') {
            row.setOpen(true);
            return st.promise;
          }
          if (st.status === 'failed') {
            clearNode(body);
            body.appendChild(loadingNode());
          }
          var p = load();
          row.setOpen(true);
          return p;
        },
        // The stored override changed (a Save, a refresh): each loaded field takes the
        // new own/inherited state and notice, keeping any pending edit.
        rebase: function (a) {
          if (st.status !== 'loaded') return;
          var stored = ((a && a.tool_overrides) || {})[name] || {};
          Object.keys(st.byField).forEach(function (fn) {
            var has = (fn in stored);
            st.byField[fn].rebase({
              own: has,
              storedValue: has ? stored[fn] : undefined,
              notice: noticeFor(name, fn)
            });
          });
        },
        // Cancel: drop the loaded body, close the disclosure, re-arm the lazy load.
        reset: function () {
          if (st.status === 'unloaded' && !row.el.open) return;
          st.gen++;
          st.status = 'unloaded';
          destroyFields();
          clearNode(body);
          body.appendChild(loadingNode());
          row.setOpen(false);
        },
        destroy: function () {
          st.gen++;
          destroyFields();
          delete panels[name];
        }
      };
    }

    // ── Build ────────────────────────────────────────────────────────
    function build() {
      var enabledSet = enabledSetFor(currentAgent);
      clearNode(panel);
      tiles = {};
      rows = {};

      // M07 F10 lazy-discovery copy (M17 F5 L1): the CAN-load semantics.
      var intro = document.createElement('p');
      intro.className = 'tools-tab-intro';
      intro.textContent = INTRO_TEXT;
      panel.appendChild(intro);

      listContainer = document.createElement('div');
      listContainer.className = 'tools-categories-list';
      panel.appendChild(listContainer);

      Object.keys(TOOL_CATEGORIES).forEach(function (cat) {
        var toolNames = TOOL_CATEGORIES[cat];
        var tile = ui.groupTile({
          name: cat,
          count: '',
          dataset: { category: cat },
          master: {
            label: 'Enable all ' + cat + ' tools',
            state: 'off',
            dataset: { categoryMaster: cat },
            onChange: function (next) {
              // Every non-disabled row follows the master.
              for (var i = 0; i < toolNames.length; i++) {
                var r = rows[toolNames[i]].row;
                if (!r.input.disabled) r.setChecked(next);
              }
              refreshCategory(cat);
              updatePathsNotes();
              onChange();
            }
          },
          toolCount: toolNames.length
        });
        tiles[cat] = { tile: tile, names: toolNames };

        toolNames.forEach(function (tName) {
          var info = findTool(tName);
          var disabled = isDisabled(tName);
          var row = ui.toolRow({
            name: tName,
            description: info && info.description ? info.description : '',
            checked: !!enabledSet[tName],
            disabled: disabled,
            note: whitelistExempt.indexOf(tName) >= 0
              ? { text: TIME_NOTE, testid: 'time-tool-note' }
              : null,
            dataset: { tool: tName },
            inputDataset: { tool: tName },
            disclosure: disabled ? null : { label: 'Overrides' },
            flag: flagNode(tName),
            onChange: function () {
              refreshCategory(cat);
              updatePathsNotes();
              onChange();
            }
          });
          rows[tName] = {
            row: row,
            flagCount: noticeCount(tName),
            category: cat,
            overrides: (!disabled && row.body) ? attachOverrides(tName, row) : null
          };
          tile.body.appendChild(row.el);
        });

        listContainer.appendChild(tile.el);
        refreshCategory(cat);
      });
    }

    function teardown() {
      for (var i = 0; i < listeners.length; i++) listeners[i]();
      listeners = [];
      Object.keys(rows).forEach(function (n) {
        if (rows[n].overrides) rows[n].overrides.destroy();
        rows[n].row.destroy();
      });
      Object.keys(tiles).forEach(function (c) { tiles[c].tile.destroy(); });
    }

    build();

    return {
      setAgent: function (a, opts) {
        opts = opts || {};
        currentAgent = a;
        if (opts.operatorConfigs) operatorConfigs = opts.operatorConfigs;
        if (opts.fetchToolSchema) fetchToolSchema = opts.fetchToolSchema;
        if (opts.disabledTools && setKey(opts.disabledTools) !== setKey(disabledTools)) {
          // The operator's disabled set changed: the rows' struck-through look and
          // disclosures are built in, so the tab rebuilds its own content.
          teardown();
          disabledTools = opts.disabledTools;
          build();
          return;
        }
        var enabledSet = enabledSetFor(a);
        Object.keys(rows).forEach(function (n) {
          rows[n].row.setChecked(!!enabledSet[n]);
          if (rows[n].overrides) {
            if (opts.revert) rows[n].overrides.reset();
            else rows[n].overrides.rebase(a);
          }
        });
        Object.keys(tiles).forEach(refreshCategory);
        // The operator's app-wide switches may have changed with the refresh.
        updatePathsNotes();
        updateFlags();
      },
      // Only the notices changed (sortie 07 L05: the studio `agents` store hook): redraw
      // the rows' flags from them and touch nothing else, so a dirty form is untouched.
      // An open panel's clipped lines update on its next render, not live.
      setNotices: function (notices) {
        currentAgent = Object.assign({}, currentAgent || {}, { notices: notices || [] });
        updateFlags();
      },
      // The follow-through for an approved change (M36 F2 L8): plain getters and setters over the
      // rows' checked state, silent (no change event), touching no override panel.
      followMap: function () {
        var m = {};
        Object.keys(rows).forEach(function (n) { m[n] = !!rows[n].row.input.checked; });
        return m;
      },
      followMapFor: function (cfg) { return enabledSetFor(cfg); },
      followSet: function (map) {
        Object.keys(rows).forEach(function (n) {
          if (Object.prototype.hasOwnProperty.call(map, n)) rows[n].row.setChecked(!!map[n]);
        });
        Object.keys(tiles).forEach(refreshCategory);
        updatePathsNotes();
      },
      followPlace: function (name, note) {
        var r = rows[name];
        var host = r && r.row.el.parentNode;
        if (host) host.insertBefore(note, r.row.el.nextSibling);
      },
      // The loaded override fields: { tool: { field: handle } } (loaded panels only).
      // agent-form-data.js's Save walk and the 422 mapping read the handles here.
      fieldHandles: function () {
        var out = {};
        Object.keys(panels).forEach(function (tn) {
          if (panels[tn].status === 'loaded') out[tn] = panels[tn].byField;
        });
        return out;
      },
      // Open a tool's override panel and resolve once its fields are rendered; rejects
      // for a tool with no panel (unknown, or off app-wide) or a schema load failure.
      openTool: function (name) {
        var r = rows[name];
        if (!r || !r.overrides) return Promise.reject(new Error('No override panel for ' + name));
        return r.overrides.open();
      },
      destroy: function () {
        teardown();
      }
    };
  }

  window.App.studio.renderToolsTab = renderToolsTab;
})();
