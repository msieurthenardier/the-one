// App.studio.renderConnectorsTab — agent-editor Connectors tab (M10 F6 L5).
//
// Mirrors mcps-tab.js shape: attach toggle per connector account + a
// collapsible details panel hosting the per-account ACL editor (peers
// list + channels list, each rendered via the standard chip-list-editor
// helper from admin/tools-form-helpers.js). When an attached account
// has empty (or absent) per-account ACL, an inline label reads
// "no restrictions — inherits account-scope" so the operator can
// visually distinguish "inherit" from "narrowing" before saving.
//
// Public API:
//   App.studio.renderConnectorsTab(panel, agent, allAccounts, callbacks)
//     panel       — DOM element (the Connectors tabpanel)
//     agent       — AgentConfig object (may be null for create-mode)
//     allAccounts — array of ConnectorAccount objects from
//                   /api/connector-accounts
//     callbacks   — { onChange }
//
// Save-flow selectors (collected by studio.js::collectFormData):
//   [data-connector-account-toggle][data-connector-account-id]:checked
//     → connector_account_ids
//   .connector-acl-chiplist[data-connector-acl-account][data-connector-acl-list]
//     → connector_acls[id].peers / [id].channels
//
// Empty-ACL semantic (per F6 leg-1c validator): an account entry with
// both lists empty is OMITTED from the serialized payload by
// collectFormData; absent === empty-lists === "inherit account-scope"
// to the resolver. The Studio UI labels both shapes identically for
// operator clarity.
//
// Stale connector_account_ids (operator deleted the account on the
// connector-accounts surface, but it remains pinned on the agent) are
// surfaced as a row with a "(missing — account deleted)" badge; the
// operator must explicitly uncheck to prune. Mirrors the
// MCP-source-deletion defensive pattern.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // ── Main entry point ──────────────────────────────────────────────────────

  function renderConnectorsTab(panel, agent, allAccounts, callbacks) {
    panel.innerHTML = '';
    callbacks = callbacks || {};
    var onChange = callbacks.onChange || function () {};

    var attached = _attachedAccountIds(agent);
    var acls = (agent && agent.connector_acls) || {};

    // Synthesize "missing — deleted" placeholders for any pinned id
    // that no longer exists in allAccounts. Operator must explicitly
    // un-toggle to prune; mirrors the MCP-source-deletion behavior.
    var byId = {};
    var rendered = [];
    for (var i = 0; i < (allAccounts || []).length; i++) {
      byId[allAccounts[i].id] = allAccounts[i];
      rendered.push(allAccounts[i]);
    }
    for (var aid in attached) {
      if (!byId[aid]) {
        rendered.push({ id: aid, name: aid, type: '', _missing: true });
      }
    }

    if (rendered.length === 0) {
      _renderEmptyState(panel);
      return;
    }

    var listContainer = document.createElement('div');
    listContainer.className = 'mcp-sources-list connector-accounts-list';
    listContainer.setAttribute('data-testid', 'connector-accounts-list');

    for (var j = 0; j < rendered.length; j++) {
      _renderAccountTile(listContainer, rendered[j], attached, acls, onChange);
    }

    panel.appendChild(listContainer);
  }

  // ── Empty state ───────────────────────────────────────────────────────────

  function _renderEmptyState(panel) {
    var div = document.createElement('div');
    div.className = 'mcp-empty-state connector-accounts-empty-state';
    div.setAttribute('data-testid', 'connector-accounts-empty-state');
    div.innerHTML = 'No connector accounts registered yet. ' +
      '<a href="#studio/connectors">Add one in Connectors.</a>';
    panel.appendChild(div);
  }

  // ── Per-account tile ──────────────────────────────────────────────────────
  //
  // Visual parity with mcps-tab.js per-source tile: glass tile with row1
  // (toggle + name + type badge), an expand button for the details body,
  // and a collapsible details body that hosts the peers + channels ACL
  // editors.

  function _renderAccountTile(listContainer, account, attachedMap, aclsMap, onChange) {
    var isAttached = attachedMap[account.id] === true;
    var accountAcl = aclsMap[account.id] || { peers: [], channels: [] };

    var tile = document.createElement('div');
    tile.className = 'mcp-source-tile connector-account-tile';
    tile.setAttribute('data-connector-account-id', account.id);
    tile.setAttribute('data-testid', 'connector-account-row-' + account.id);
    tile.setAttribute('aria-expanded', 'false');

    // ── Row 1: toggle + name + type badge (+ missing badge if stale) ──
    var row1 = document.createElement('div');
    row1.className = 'mcp-source-tile-row1';

    var toggleLabel = document.createElement('label');
    toggleLabel.className = 'mcp-source-tile-toggle';

    var checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'tool-toggle connector-account-toggle';
    checkbox.setAttribute('data-connector-account-toggle', '');
    checkbox.setAttribute('data-connector-account-id', account.id);
    checkbox.setAttribute('data-testid', 'connector-account-toggle-' + account.id);
    checkbox.checked = isAttached;
    toggleLabel.appendChild(checkbox);

    var visualSwitch = document.createElement('span');
    visualSwitch.className = 'tool-switch';
    toggleLabel.appendChild(visualSwitch);

    row1.appendChild(toggleLabel);

    var nameSpan = document.createElement('span');
    nameSpan.className = 'mcp-source-tile-name';
    nameSpan.textContent = account.name || account.id;
    row1.appendChild(nameSpan);

    if (account._missing) {
      var missingBadge = document.createElement('span');
      missingBadge.className = 'mcp-source-tile-protocol connector-account-missing-badge';
      missingBadge.setAttribute('data-testid', 'connector-account-missing-' + account.id);
      missingBadge.textContent = 'missing — account deleted';
      row1.appendChild(missingBadge);
    } else if (account.type) {
      var typeBadge = document.createElement('span');
      typeBadge.className = 'mcp-source-tile-protocol connector-account-type-badge';
      typeBadge.textContent = account.type;
      row1.appendChild(typeBadge);
    }

    tile.appendChild(row1);

    // ── Expand button: chevron only (no per-account "tool count") ─────
    var expandBtn = document.createElement('button');
    expandBtn.type = 'button';
    expandBtn.className = 'mcp-source-tile-expand-btn';
    expandBtn.setAttribute('aria-expanded', 'false');
    expandBtn.setAttribute('data-testid', 'connector-account-expand-' + account.id);

    var countSpan = document.createElement('span');
    countSpan.className = 'mcp-source-tile-tool-count';
    countSpan.textContent = 'ACL';
    var chevron = document.createElement('span');
    chevron.className = 'mcp-source-tile-chevron';
    chevron.textContent = '▸';
    expandBtn.appendChild(countSpan);
    expandBtn.appendChild(chevron);
    tile.appendChild(expandBtn);

    // ── Details body (collapsed by default; holds the ACL editor) ────
    var detailsBody = document.createElement('div');
    detailsBody.className = 'mcp-source-tile-tools connector-account-details-body';
    detailsBody.setAttribute('data-testid', 'connector-account-details-body-' + account.id);
    detailsBody.hidden = true;
    tile.appendChild(detailsBody);

    function _populateAclEditor() {
      detailsBody.innerHTML = '';

      var section = document.createElement('div');
      section.className = 'connector-account-acl-section';

      // Inherit-affordance label — visible whenever both lists are
      // currently empty. The label re-syncs on each chip change so it
      // disappears as soon as the operator narrows.
      var inheritLabel = document.createElement('p');
      inheritLabel.className = 'connector-account-acl-inherit-label';
      inheritLabel.setAttribute('data-testid', 'connector-account-acl-inherit-' + account.id);
      inheritLabel.textContent = 'no restrictions — inherits account-scope';
      section.appendChild(inheritLabel);

      // Peers list.
      var peersWrap = document.createElement('div');
      peersWrap.className = 'connector-account-acl-fieldrow';
      var peersLabel = document.createElement('label');
      peersLabel.className = 'connector-account-acl-fieldlabel';
      peersLabel.textContent = 'Peers';
      peersWrap.appendChild(peersLabel);
      var peersChiplist = _buildChipList(account.id, 'peers', accountAcl.peers || []);
      peersWrap.appendChild(peersChiplist);
      section.appendChild(peersWrap);

      // Channels list.
      var channelsWrap = document.createElement('div');
      channelsWrap.className = 'connector-account-acl-fieldrow';
      var channelsLabel = document.createElement('label');
      channelsLabel.className = 'connector-account-acl-fieldlabel';
      channelsLabel.textContent = 'Channels';
      channelsWrap.appendChild(channelsLabel);
      var channelsChiplist = _buildChipList(account.id, 'channels', accountAcl.channels || []);
      channelsWrap.appendChild(channelsChiplist);
      section.appendChild(channelsWrap);

      detailsBody.appendChild(section);

      var helpers = window.App.adminFormHelpers;
      function _syncInheritLabel() {
        var pc = peersChiplist.querySelectorAll('.chip').length;
        var cc = channelsChiplist.querySelectorAll('.chip').length;
        inheritLabel.hidden = (pc > 0 || cc > 0);
      }
      _syncInheritLabel();

      if (helpers && helpers.wireChipListEditor) {
        helpers.wireChipListEditor(peersChiplist, {
          onChange: function () { _syncInheritLabel(); onChange(); }
        });
        helpers.wireChipListEditor(channelsChiplist, {
          onChange: function () { _syncInheritLabel(); onChange(); }
        });
      }
    }

    // Wire the attach toggle → onChange (dirty tracking).
    checkbox.addEventListener('change', function () { onChange(); });

    // Expand toggles the details panel. The ACL editor is built lazily
    // on first expand to avoid wiring listeners for accounts the
    // operator never opens.
    var loadedOnce = false;
    expandBtn.addEventListener('click', function () {
      var nextExpanded = expandBtn.getAttribute('aria-expanded') !== 'true';
      tile.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
      expandBtn.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
      detailsBody.hidden = !nextExpanded;
      if (nextExpanded && !loadedOnce) {
        loadedOnce = true;
        _populateAclEditor();
      }
    });

    listContainer.appendChild(tile);
  }

  // ── Chip-list factory ─────────────────────────────────────────────────────
  //
  // Builds a chip-list-editor wrapper carrying the per-account ACL data
  // attributes so studio.js::collectFormData can group chips by account
  // id + list kind without re-parsing label text. Visual parity with
  // the admin chip-list pattern (renderChipListEditor) — the only
  // divergence is the data attributes (account ACLs don't fit the
  // tool-override schema).

  function _buildChipList(accountId, listKind, items) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;

    var wrapper = document.createElement('div');
    wrapper.className = 'chip-list-editor connector-acl-chiplist';
    wrapper.setAttribute('data-connector-acl-account', accountId);
    wrapper.setAttribute('data-connector-acl-list', listKind);
    wrapper.setAttribute('data-testid',
      'connector-acl-' + listKind + '-' + accountId);

    for (var i = 0; i < (items || []).length; i++) {
      var v = String(items[i]);
      var chip = document.createElement('span');
      chip.className = 'chip';
      chip.appendChild(document.createTextNode(v));
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chip-remove';
      btn.setAttribute('aria-label', 'Remove ' + v);
      btn.textContent = '×';
      chip.appendChild(btn);
      wrapper.appendChild(chip);
    }

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'chip-list-input';
    input.placeholder = listKind === 'peers' ? 'Add peer…' : 'Add channel…';
    input.setAttribute('aria-label',
      listKind === 'peers' ? 'Add peer' : 'Add channel');
    wrapper.appendChild(input);

    // No-op references to defeat unused-var lints in non-eval contexts.
    void escapeAttr; void escapeHtml;
    return wrapper;
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _attachedAccountIds(agent) {
    var ids = {};
    if (!agent) return ids;
    var pinned = agent.connector_account_ids || [];
    for (var i = 0; i < pinned.length; i++) ids[pinned[i]] = true;
    return ids;
  }

  window.App.studio.renderConnectorsTab = renderConnectorsTab;
})();
