// App.chat.drawerGroups -- the agent drawer's stateless group builders and tool-enable
// helpers (split out of agent-drawer.js, squawk 0386, to leave the module room under the
// 800-line rule). No state of its own: the drawer passes its data in. Every text goes
// through textContent (el's `text`) and `title`, never an HTML sink.
//
//   isToolEnabled(agent, name): AgentConfig.is_tool_enabled mirrored (the_one/agent/config.py;
//     parity pinned by tests/browser/test_flow_chat_drawer.py).
//   builtinGroups(agent, configs) -> [{label, enabled, total}] for the categories with at
//     least one effective tool.
//   group(id, label, items, status): one "What it can use" group ({name, meta} items, or
//     "None", "Loading…" or "Couldn't load").
//   rulesGroup(rulesState): the Rules group (M27 F1 L2, DD7). The enabled rules in order
//     (each text clamped to two lines by CSS, the full text in `title`), "{n} off" for the
//     disabled ones, "No rules" when none are enabled. Shown as SAVED.
//   notesGroup(notesState): the Notes group (M27 F2 L3 DD10 / F3 L2), READ-ONLY. Off: "Off"
//     and "{n} kept". On: the in-use notes, then (when the server knows the open chat's
//     prompt) a "Pending · used from the next chat" subheading and the notes that prompt
//     does not carry yet, muted.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // AgentConfig's UNGATED_TOOL_PREFIXES: exempt from the enabled_tools
  // whitelist (it gates built-ins only); disabled_tools is universal.
  var UNGATED_PREFIXES = (window.App.toolCategories && window.App.toolCategories.ungatedPrefixes) || [];

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  function arr(v) {
    return Array.isArray(v) ? v : [];
  }

  function isToolEnabled(agent, name) {
    var ungated = false;
    for (var i = 0; i < UNGATED_PREFIXES.length; i++) {
      if (String(name).indexOf(UNGATED_PREFIXES[i]) === 0) ungated = true;
    }
    var exempt = (window.App.toolCategories && window.App.toolCategories.whitelistExempt) || [];
    if (exempt.indexOf(name) !== -1) ungated = true;
    var whitelist = agent ? agent.enabled_tools : null;
    if (!ungated && whitelist !== null && whitelist !== undefined && arr(whitelist).indexOf(name) === -1) {
      return false;
    }
    if (arr(agent && agent.disabled_tools).indexOf(name) !== -1) return false;
    return true;
  }

  // The built-in categories the agent can use: per category, the tools that
  // are globally enabled (a /api/tools/configs row with enabled: false turns
  // one off; a missing row is enabled) AND enabled for the agent.
  function builtinGroups(agent, configs) {
    var off = {};
    var rows = arr(configs);
    for (var i = 0; i < rows.length; i++) {
      if (rows[i] && rows[i].enabled === false) off[rows[i].name] = true;
    }
    var by = App.toolCategories.byCategory;
    var labels = Object.keys(by);
    var out = [];
    for (var c = 0; c < labels.length; c++) {
      var names = by[labels[c]];
      var n = 0;
      for (var t = 0; t < names.length; t++) {
        if (!off[names[t]] && isToolEnabled(agent, names[t])) n += 1;
      }
      if (n) out.push({ label: labels[c], enabled: n, total: names.length });
    }
    return out;
  }

  // One "What it can use" group: a label and a list of {name, meta}
  // items, or "None", "Loading…" or "Couldn't load".
  function group(id, label, items, status) {
    var box = el('div', { className: 'chat-drawer-group', dataset: { group: id } }, [
      el('h4', { className: 'chat-drawer-group-label', text: label })
    ]);
    if (status === 'loading' || status === 'error') {
      box.appendChild(el('p', {
        className: 'chat-drawer-none',
        text: status === 'loading' ? 'Loading…' : 'Couldn\'t load'
      }));
      return box;
    }
    if (!items.length) {
      box.appendChild(el('p', { className: 'chat-drawer-none', text: 'None' }));
      return box;
    }
    var ul = el('ul', { className: 'chat-drawer-list' });
    for (var i = 0; i < items.length; i++) {
      ul.appendChild(el('li', null, [
        el('span', { className: 'chat-drawer-item-name', text: items[i].name }),
        items[i].meta ? el('span', { className: 'chat-drawer-item-meta', text: items[i].meta }) : null
      ]));
    }
    box.appendChild(ul);
    return box;
  }

  function rulesGroup(rulesState) {
    var box = el('div', { className: 'chat-drawer-group', dataset: { group: 'rules' } }, [
      el('h4', { className: 'chat-drawer-group-label', text: 'Rules' })
    ]);
    if (rulesState.status === 'ok') {
      var all = arr(rulesState.value);
      var on = [];
      for (var i = 0; i < all.length; i++) if (all[i] && all[i].enabled) on.push(all[i]);
      var off = all.length - on.length;
      if (!on.length) {
        box.appendChild(el('p', { className: 'chat-drawer-none', text: 'No rules' }));
      } else {
        var ol = el('ul', { className: 'chat-drawer-rules' });
        ol.setAttribute('role', 'list');
        ol.setAttribute('data-testid', 'chat-drawer-rules');
        for (var j = 0; j < on.length; j++) {
          var li = el('li', null, [el('span', { className: 'chat-drawer-rule-text', text: String(on[j].text) })]);
          li.setAttribute('title', String(on[j].text));
          li.setAttribute('data-testid', 'chat-drawer-rule');
          ol.appendChild(li);
        }
        box.appendChild(ol);
      }
      if (off > 0) {
        var offEl = el('p', { className: 'chat-drawer-rules-off', text: off + ' off' });
        offEl.setAttribute('data-testid', 'chat-drawer-rules-off');
        box.appendChild(offEl);
      }
      return box;
    }
    box.appendChild(el('p', {
      className: 'chat-drawer-none',
      text: rulesState.status === 'error' ? 'Couldn\'t load' : 'Loading…'
    }));
    return box;
  }

  function notesGroup(notesState) {
    var box = el('div', { className: 'chat-drawer-group', dataset: { group: 'notes' } }, [
      el('h4', { className: 'chat-drawer-group-label', text: 'Notes' })
    ]);
    if (notesState.status !== 'ok') {
      box.appendChild(el('p', {
        className: 'chat-drawer-none',
        text: notesState.status === 'error' ? 'Couldn\'t load' : 'Loading…'
      }));
      return box;
    }
    var enabled = !!(notesState.value && notesState.value.enabled);
    var all = arr(notesState.value && notesState.value.notes);
    if (!enabled) {
      var offEl = el('p', { className: 'chat-drawer-value', text: 'Off' });
      offEl.setAttribute('data-testid', 'chat-drawer-notes-off');
      box.appendChild(offEl);
      if (all.length) {
        var kept = el('p', { className: 'chat-drawer-notes-kept', text: all.length + ' kept' });
        kept.setAttribute('data-testid', 'chat-drawer-notes-kept');
        box.appendChild(kept);
      }
    } else if (!all.length) {
      var none = el('p', { className: 'chat-drawer-none', text: 'No notes yet' });
      none.setAttribute('data-testid', 'chat-drawer-notes-empty');
      box.appendChild(none);
    } else {
      var inUse = [];
      var pending = [];
      for (var i = 0; i < all.length; i++) (all[i].pending ? pending : inUse).push(all[i]);
      if (inUse.length) box.appendChild(App.chat.drawerParts.noteList(inUse, false));
      if (pending.length) {
        var head = el('p', {
          className: 'chat-drawer-notes-pending-head',
          text: 'Pending · used from the next chat'
        });
        head.setAttribute('data-testid', 'chat-drawer-notes-pending-head');
        box.appendChild(head);
        box.appendChild(App.chat.drawerParts.noteList(pending, true));
      }
    }
    return box;
  }

  window.App.chat.drawerGroups = {
    isToolEnabled: isToolEnabled,
    builtinGroups: builtinGroups,
    group: group,
    rulesGroup: rulesGroup,
    notesGroup: notesGroup
  };
})();
