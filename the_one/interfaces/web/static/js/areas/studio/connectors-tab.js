// App.studio.renderConnectorsTab — agent-editor Connectors tab
// (M10 F6 L5; semantic redesigned at L7 HAT).
//
// Mirrors mcps-tab.js shape: attach toggle per connector account + a
// collapsible details panel hosting the per-account ACL editor (peers
// + channels). Per axis the editor adapts to the account-scope state:
//
//   - account-scope axis has chips (subset narrowing): render a
//     CHECKBOX LIST of those chips. The operator's per-agent ACL is
//     captured as null (all checked = inherit), [] (all unchecked =
//     "no access" / DMs-only for channels), or [items] (some checked
//     = subset).
//   - account-scope axis is empty / absent (unrestricted): render a
//     free-form CHIP-LIST editor (current pattern). Empty = null
//     (inherit / unrestricted); non-empty = [items].
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
//   For per-agent ACL each axis carries one of two markup shapes:
//     .connector-acl-chiplist[data-connector-acl-account]
//                            [data-connector-acl-list]
//                            [data-connector-acl-mode="chips"]
//       → free chip-list mode (axis emits null when empty, [items]
//         otherwise)
//     .connector-acl-checkboxlist[data-connector-acl-account]
//                                 [data-connector-acl-list]
//                                 [data-connector-acl-mode="checkboxes"]
//       → checkbox-list mode (axis emits null when all checked, []
//         when all unchecked, [items] otherwise)
//
// L7 HAT tri-state semantic (per F6 leg-1c validator, redesigned):
//   - axis null: inherit account-scope (no per-agent narrowing on
//     this axis).
//   - axis []: explicit empty — peers means "no peer"; channels
//     means "DMs only" (F8-deferred; outbound fails closed until
//     F8 ships DM classification).
//   - axis [items]: narrow to those items (intersected with
//     account-scope).
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
    // L7 HAT — tri-state per-axis. Default missing entry to both-null
    // (inherit account-scope on both axes); preserve any per-axis null
    // explicitly so the checkbox-mode "all checked" initial state
    // matches.
    var rawAcl = aclsMap[account.id];
    var accountAcl;
    if (rawAcl == null) {
      accountAcl = { peers: null, channels: null };
    } else {
      accountAcl = {
        peers: (rawAcl.peers === undefined) ? null : rawAcl.peers,
        channels: (rawAcl.channels === undefined) ? null : rawAcl.channels
      };
    }
    // Account-scope reference (per-axis lists). Drive the
    // checkbox-vs-chip mode decision per axis.
    var accountScope = (account && account.config && account.config.allowlist) || null;
    var scopePeers = (accountScope && Array.isArray(accountScope.peers)) ? accountScope.peers : [];
    var scopeChannels = (accountScope && Array.isArray(accountScope.channels)) ? accountScope.channels : [];

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

    // ── ACL body (always visible; M10 F6 L7 HAT — drop the
    //    per-account chevron + collapsed-by-default details). The
    //    peers/channels editors render inline directly under the
    //    attach toggle row so the operator sees the per-agent state
    //    at a glance.
    var detailsBody = document.createElement('div');
    detailsBody.className = 'mcp-source-tile-tools connector-account-details-body';
    detailsBody.setAttribute('data-testid', 'connector-account-details-body-' + account.id);
    tile.appendChild(detailsBody);

    function _populateAclEditor() {
      detailsBody.innerHTML = '';

      var section = document.createElement('div');
      section.className = 'connector-account-acl-section';

      var helpers = window.App.adminFormHelpers;

      function _buildAxisRow(axis, scopeList, agentAxisValue) {
        // axis === 'peers' | 'channels'
        // scopeList: account-scope chip array on this axis ([] = unrestricted)
        // agentAxisValue: per-agent value on this axis (null / [] / [items])
        // Each axis is a chevron-button that toggles its checkbox-list
        // body — the same `.mcp-source-tile-expand-btn` shape used by
        // the MCPs tab's "N tools" expand. The count span shows the
        // live ACL summary ("3 peers", "DMs only", etc.).
        var axisLabel = axis === 'peers' ? 'Peers' : 'Channels';
        var details = document.createElement('div');
        details.className = 'connector-acl-axis';
        details.setAttribute('data-testid', 'connector-acl-axis-' + axis + '-' + account.id);

        var expandBtn = document.createElement('button');
        expandBtn.type = 'button';
        expandBtn.className = 'mcp-source-tile-expand-btn connector-acl-axis-toggle';
        expandBtn.setAttribute('aria-expanded', 'false');
        expandBtn.setAttribute('data-testid', 'connector-acl-axis-toggle-' + axis + '-' + account.id);
        var titleSpan = document.createElement('span');
        titleSpan.className = 'connector-acl-axis-title';
        titleSpan.textContent = axisLabel;
        var countSpan = document.createElement('span');
        countSpan.className = 'mcp-source-tile-tool-count';
        countSpan.setAttribute('data-testid', 'connector-acl-axis-count-' + axis + '-' + account.id);
        var chevron = document.createElement('span');
        chevron.className = 'mcp-source-tile-chevron';
        chevron.textContent = '▸';
        expandBtn.appendChild(titleSpan);
        expandBtn.appendChild(countSpan);
        expandBtn.appendChild(chevron);
        details.appendChild(expandBtn);

        var body = document.createElement('div');
        body.className = 'connector-acl-axis-body';
        body.hidden = true;
        details.appendChild(body);

        expandBtn.addEventListener('click', function () {
          var nextExpanded = expandBtn.getAttribute('aria-expanded') !== 'true';
          expandBtn.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
          body.hidden = !nextExpanded;
        });

        function _summarize() {
          // Live summary computed from current DOM state, so the
          // operator sees "2 of 3 peers" or "All channels" without
          // saving first.
          if (scopeList && scopeList.length > 0) {
            var boxes = body.querySelectorAll('input[type="checkbox"]');
            var total = boxes.length;
            var checked = 0;
            for (var i = 0; i < boxes.length; i++) {
              if (boxes[i].checked) checked++;
            }
            if (checked === total) {
              countSpan.textContent = 'All ' + axisLabel.toLowerCase() + ' (inheriting)';
            } else if (checked === 0) {
              countSpan.textContent = axis === 'channels'
                ? 'DMs only'
                : 'No ' + axisLabel.toLowerCase() + ' permitted';
            } else {
              countSpan.textContent = checked + ' of ' + total + ' ' + axisLabel.toLowerCase();
            }
          } else {
            // chips mode
            var chips = body.querySelectorAll('.chip');
            if (chips.length === 0) {
              countSpan.textContent = 'All ' + axisLabel.toLowerCase() + ' (no restriction)';
            } else {
              countSpan.textContent = chips.length + ' ' + axisLabel.toLowerCase();
            }
          }
        }

        if (scopeList && scopeList.length > 0) {
          // Account-scope axis has chips → checkbox mode.
          var checkboxWrap = _buildCheckboxList(account.id, axis, scopeList, agentAxisValue);
          body.appendChild(checkboxWrap);

          var warn = document.createElement('p');
          warn.className = 'form-hint connector-acl-checkbox-warn';
          warn.setAttribute('data-testid', 'connector-acl-checkbox-warn-' + axis + '-' + account.id);
          warn.textContent = axis === 'channels'
            ? 'No public channels permitted; agent will only receive DMs.'
            : 'No peers permitted for this agent on this account. Consider detaching instead.';
          warn.hidden = true;
          body.appendChild(warn);

          function _syncWarn() {
            var boxes = checkboxWrap.querySelectorAll('input[type="checkbox"]');
            var anyChecked = false;
            for (var i = 0; i < boxes.length; i++) {
              if (boxes[i].checked) { anyChecked = true; break; }
            }
            warn.hidden = anyChecked;
          }
          _syncWarn();
          checkboxWrap.addEventListener('change', function (e) {
            if (e && e.target && e.target.type === 'checkbox') {
              _syncWarn();
              _summarize();
              onChange();
            }
          });
        } else {
          // Account-scope axis is empty / absent → free chip-list mode.
          var initItems;
          if (Array.isArray(agentAxisValue)) {
            initItems = agentAxisValue;
          } else {
            initItems = [];
          }
          var chiplist = _buildChipList(account.id, axis, initItems);
          body.appendChild(chiplist);
          if (helpers && helpers.wireChipListEditor) {
            helpers.wireChipListEditor(chiplist, {
              onChange: function () { _summarize(); onChange(); }
            });
          }
        }

        // Initial summary line.
        _summarize();
        return details;
      }

      section.appendChild(_buildAxisRow('peers', scopePeers, accountAcl.peers));
      section.appendChild(_buildAxisRow('channels', scopeChannels, accountAcl.channels));

      detailsBody.appendChild(section);
    }

    // Wire the attach toggle → onChange (dirty tracking).
    checkbox.addEventListener('change', function () { onChange(); });

    // ACL editor is built eagerly (no per-account expand). The
    // attach toggle controls whether the row's data participates in
    // save (collectFormData reads only attached accounts via the
    // toggle state); the ACL chips are visible regardless so the
    // operator can see what would apply once they attach.
    _populateAclEditor();

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
    // L7 HAT — mode marker distinguishes chip-list-mode from
    // checkbox-list-mode at save-collection time.
    wrapper.setAttribute('data-connector-acl-mode', 'chips');
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

  // ── Checkbox-list factory (L7 HAT) ────────────────────────────────────
  //
  // Renders one labeled checkbox per account-scope chip. The initial
  // check state derives from the per-agent axis value:
  //   - null (inherit) → all checked
  //   - [] (explicit empty) → all unchecked
  //   - [items] (subset) → check the matching items only
  // studio.js::collectFormData reads each checkbox's value attribute
  // and emits the per-axis ACL accordingly (null / [] / [items]).

  function _buildCheckboxList(accountId, listKind, scopeList, agentAxisValue) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;

    var wrapper = document.createElement('div');
    wrapper.className = 'connector-acl-checkboxlist';
    wrapper.setAttribute('data-connector-acl-account', accountId);
    wrapper.setAttribute('data-connector-acl-list', listKind);
    wrapper.setAttribute('data-connector-acl-mode', 'checkboxes');
    wrapper.setAttribute('data-testid',
      'connector-acl-' + listKind + '-checkboxes-' + accountId);

    var initialAllChecked = (agentAxisValue == null);
    var initialAllUnchecked = (Array.isArray(agentAxisValue) && agentAxisValue.length === 0);
    var explicitItems = (!initialAllChecked && !initialAllUnchecked && Array.isArray(agentAxisValue))
      ? agentAxisValue
      : null;

    for (var i = 0; i < scopeList.length; i++) {
      var item = String(scopeList[i]);
      // Tile shape mirrors the MCPs tab tool-toggle rows
      // (.mcp-tool-toggle-label) — single-line flex row with bordered
      // tile + hover affordance. The .connector-acl-checkboxlist-row
      // class is preserved alongside for any future studio-scoped
      // overrides.
      var rowLabel = document.createElement('label');
      rowLabel.className = 'mcp-tool-toggle-label connector-acl-checkboxlist-row';
      rowLabel.setAttribute('data-testid',
        'connector-acl-' + listKind + '-checkbox-row-' + accountId + '-' + item);
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'checkbox-primary connector-acl-checkbox';
      cb.value = item;
      cb.setAttribute('data-connector-acl-account', accountId);
      cb.setAttribute('data-connector-acl-list', listKind);
      if (initialAllChecked) {
        cb.checked = true;
      } else if (initialAllUnchecked) {
        cb.checked = false;
      } else {
        cb.checked = (explicitItems && explicitItems.indexOf(item) !== -1);
      }
      rowLabel.appendChild(cb);
      var text = document.createElement('div');
      text.className = 'mcp-tool-text';
      var nameSpan = document.createElement('span');
      nameSpan.className = 'mcp-tool-toggle-name';
      nameSpan.textContent = item;
      text.appendChild(nameSpan);
      rowLabel.appendChild(text);
      wrapper.appendChild(rowLabel);
    }

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
