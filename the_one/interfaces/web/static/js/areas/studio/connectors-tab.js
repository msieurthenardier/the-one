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

  // M11 F7 L11: listen for account-level master changes to grey-out
  // per-account toggles in real time. Mirrors F4 / F5 listener pattern
  // for the existing two CustomEvents (``connector-account-pool-warmed`` +
  // ``connector-account-discoverable-refresh-requested``). Registered
  // ONCE at module init — registering inside ``_renderAccountTile``
  // would leak handlers on every re-render of the Connectors tab.
  // Safe-by-construction: the handler runs a single DOM querySelector
  // per dispatch and is a no-op when the matching toggle is absent
  // (e.g. the agent editor's Connectors tab isn't open).
  //
  // TODO(routine-maintenance): see the matching TODO above the dispatch
  // in ``connector-account-editor.js`` — n=3 inline CustomEvent strings
  // in Studio triggers the F4 R13 studio-event-bus lift candidate;
  // defer the lift per F7 recon discipline.
  App.studio.eventBus.on('connector-account-always-listen-changed', function (event) {
    var accountId = event && event.detail && event.detail.accountId;
    var enabled = !!(event && event.detail && event.detail.enabled);
    if (!accountId) return;
    var toggle = document.querySelector(
      '[data-field="connector_always_listen"][data-account-id="' + CSS.escape(accountId) + '"]'
    );
    if (toggle) {
      toggle.disabled = !enabled;
      if (!enabled) toggle.checked = false; // master OFF → force per-agent off
    }
  });

  // ── Main entry point ──────────────────────────────────────────────────────

  function renderConnectorsTab(panel, agent, allAccounts, callbacks) {
    panel.innerHTML = '';
    callbacks = callbacks || {};
    var onChange = callbacks.onChange || function () {};

    var attached = _attachedAccountIds(agent);
    var acls = (agent && agent.connector_acls) || {};
    // M11 F7 L11: per-account "Always Listen" dict (per-agent capability
    // switch). Default to {} when the field is absent on the agent so the
    // per-tile lookup short-circuits to false.
    var alwaysListen = (agent && agent.connector_always_listen) || {};

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
      _renderAccountTile(listContainer, rendered[j], attached, acls, alwaysListen, onChange);
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

  function _renderAccountTile(listContainer, account, attachedMap, aclsMap, alwaysListenMap, onChange) {
    var isAttached = attachedMap[account.id] === true;
    // L7 HAT — tri-state per-axis. Default missing entry to both-null
    // (inherit account-scope on both axes); preserve any per-axis null
    // explicitly so the checkbox-mode "all checked" initial state
    // matches.
    var rawAcl = aclsMap[account.id];
    var accountAcl;
    if (rawAcl == null) {
      // M11 F10 L3: include admit_dms in the canonical shape so the
      // _buildAdmitDmsRow helper can read it (undefined ⇒ inherit).
      accountAcl = { peers: null, channels: null, admit_dms: undefined };
    } else {
      accountAcl = {
        peers: (rawAcl.peers === undefined) ? null : rawAcl.peers,
        channels: (rawAcl.channels === undefined) ? null : rawAcl.channels,
        // M11 F10 L3: preserve admit_dms through normalization.
        // Without this, a persisted opt-out (admit_dms: false) is
        // dropped here and the per-agent toggle re-renders as CHECKED
        // (inherit) on page reload, silently losing the operator's
        // opt-out. Pinned by test #4 in
        // test_flow_studio_per_agent_admit_dms.py.
        admit_dms: rawAcl.admit_dms
      };
    }
    // Account-scope reference (per-axis lists). Drive the
    // checkbox-vs-chip mode decision per axis.
    var accountScope = (account && account.config && account.config.allowlist) || null;
    var scopePeers = (accountScope && Array.isArray(accountScope.peers)) ? accountScope.peers : [];
    var scopeChannels = (accountScope && Array.isArray(accountScope.channels)) ? accountScope.channels : [];
    // M11 F10 L3: account-scope dm_admission gates whether the
    // per-agent admit_dms toggle is interactive. "none" disables the
    // toggle (structurally inert — no DMs reach the dispatcher anyway);
    // "allowlisted-peers-only" / "all" leave it interactive. Defensive
    // default mirrors L1's validator behavior when accountScope is
    // null or the key is absent.
    var scopeDmAdmission = (accountScope && accountScope.dm_admission) || 'allowlisted-peers-only';

    // A2 (M11 F4 L3) — lazy per-tile label cache for checkbox-mode rows.
    // Discord and similar live-data connector accounts expose
    // ``enumerate_discoverable_entities`` via the L4 cache; the cache
    // resolves Discord snowflake IDs to friendly labels (``#general``
    // etc.) so the per-agent overlay's checkbox-mode does not surface
    // raw IDs. Stub-type / cold-pool / network-error all fall back to
    // the raw-id render preserved by the initial DOM mount.
    var _labelCache = null;
    var _labelCachePromise = null;

    function _ensureLabelCache() {
      if (_labelCachePromise) return _labelCachePromise;
      var url = '/api/connector-accounts/' +
        encodeURIComponent(account.id) +
        '/discoverable-entities';
      _labelCachePromise = fetch(url).then(function (response) {
        if (!response.ok) {
          _labelCache = {};
          return _labelCache;
        }
        return response.json().then(function (body) {
          var map = {};
          var ents = (body && body.entities) || {};
          var axes = ['peers', 'channels', 'groups', 'roles'];
          for (var a = 0; a < axes.length; a++) {
            var list = ents[axes[a]] || [];
            for (var i = 0; i < list.length; i++) {
              var e = list[i];
              if (e && e.id && e.label) map[String(e.id)] = e.label;
            }
          }
          _labelCache = map;
          return _labelCache;
        });
      }).catch(function (err) {
        _labelCache = {};
        try { console.error('connectors-tab label-cache fetch failed:', err); }
        catch (logErr) { /* console missing */ }
        return _labelCache;
      });
      return _labelCachePromise;
    }

    function _applyLabelsToCheckboxes(bodyEl) {
      if (!_labelCache) return;
      var rows = bodyEl.querySelectorAll('.connector-acl-checkboxlist-row');
      for (var i = 0; i < rows.length; i++) {
        var cb = rows[i].querySelector('input[type="checkbox"]');
        if (!cb) continue;
        var label = _labelCache[String(cb.value)];
        if (!label) continue;
        var nameSpan = rows[i].querySelector('.mcp-tool-toggle-name');
        if (nameSpan) nameSpan.textContent = label;
      }
    }

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

      // M11 F10 L3: per-agent admit_dms opt-out row.
      //
      // Boolean field with tri-state inheritance over the persisted
      // value at ``agent.connector_acls[account.id].admit_dms``:
      //   - admit_dms absent / null / true → inherit account-scope
      //     (rendered as CHECKED — the operator-friendly "DMs are
      //     admitted as the account configures" default)
      //   - admit_dms === false → explicit opt-out (UNCHECKED)
      //
      // True is structurally redundant with absent (both inherit) and
      // the UI never emits it — the collect path at studio.js emits
      // ONLY ``admit_dms: false`` for unchecked, and emits nothing for
      // checked. Keeps the persisted shape clean.
      //
      // Disabled state: when account-scope ``dm_admission === "none"``
      // the toggle is structurally inert (no DMs reach the dispatcher
      // anyway). Render disabled + visually-checked so the operator
      // sees the field exists; collect path skips disabled inputs (the
      // intentional cleanup posture documented in the leg artifact).
      //
      // Row classes mirror the always-listen row at lines 484-520 for
      // visual parity; the row sits BETWEEN always-listen and the
      // peers/channels axis rows.
      function _buildAdmitDmsRow() {
        var row = document.createElement('div');
        row.className = 'field-row admin-pf-row connector-account-admit-dms-row';
        row.setAttribute('data-testid',
          'agent-connector-admit-dms-row-' + account.id);

        var label = document.createElement('label');
        label.className = 'connector-account-admit-dms-label';
        label.htmlFor = 'agent-admit-dms-' + account.id;
        label.textContent = 'Allow DMs';
        row.appendChild(label);

        var disabled = (scopeDmAdmission === 'none');
        // M11 F10 L5 HAT polish: the only hint we keep is the
        // disabled-state explanation. Operator dropped the redundant
        // "uncheck to deny" copy — the toggle's affordance is self-
        // evident when the account permits DMs.
        var hint = null;
        if (disabled) {
          hint = document.createElement('span');
          hint.className = 'form-hint connector-account-admit-dms-hint';
          hint.setAttribute('data-testid',
            'agent-connector-admit-dms-hint-' + account.id);
          hint.textContent = 'Account denies all DMs; per-agent override does not apply.';
          row.appendChild(hint);
        }

        // Tri-state initial: absent / null / true → checked;
        // strict false → unchecked.
        var currentAdmitDms = accountAcl ? accountAcl.admit_dms : undefined;
        var initiallyChecked = (currentAdmitDms !== false);

        var sw = document.createElement('label');
        sw.className = 'tool-enable-switch';
        var input = document.createElement('input');
        input.type = 'checkbox';
        input.id = 'agent-admit-dms-' + account.id;
        input.className = 'field-input agent-connector-admit-dms-toggle';
        input.setAttribute('data-field', 'admit_dms');
        input.setAttribute('data-account-id', account.id);
        input.setAttribute('data-testid', 'agent-connector-admit-dms-' + account.id);
        // Disabled-and-visually-checked when account scope is "none";
        // otherwise reflect the tri-state inheritance above.
        input.checked = disabled ? true : initiallyChecked;
        input.disabled = disabled;
        input.addEventListener('change', function () { onChange(); });
        sw.appendChild(input);
        var track = document.createElement('span');
        track.className = 'tool-enable-switch-track';
        track.setAttribute('aria-hidden', 'true');
        sw.appendChild(track);
        row.appendChild(sw);

        return row;
      }

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
          // A2: lazy label resolution for checkbox-mode rows. Fires once
          // per tile (single-flight promise); collapse-then-re-expand
          // reuses the cache.
          if (nextExpanded && scopeList && scopeList.length > 0) {
            _ensureLabelCache().then(function () {
              _applyLabelsToCheckboxes(body);
            });
          }
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
          //
          // M11 F3 L6b — per-agent overlay dispatch: for connector
          // types whose registry entry exposes
          // ``renderDiscoverableDropdown`` (Discord today), the
          // chip-list editor is replaced with the live-data dropdown.
          // The dropdown's getter is installed as
          // ``_overlayChipValues`` on the wrapper so studio.js's
          // collect path consults it before falling back to the
          // text-node walk. Stub-type / no-entry accounts fall back
          // to the existing chip-list editor.
          var initItems;
          if (Array.isArray(agentAxisValue)) {
            initItems = agentAxisValue;
          } else {
            initItems = [];
          }
          var chiplist = _buildChipList(account.id, axis, initItems);
          body.appendChild(chiplist);

          var overlayRegistry = (window.App && window.App.studio
            && window.App.studio.connectorFormRegistry) || null;
          var overlayEntry = (overlayRegistry && account && account.type)
            ? overlayRegistry.get(account.type)
            : null;
          var mounted = false;
          if (overlayEntry && typeof overlayEntry.renderDiscoverableDropdown === 'function') {
            var overlayState = { values: initItems.slice() };
            // Per-agent overlay axes are ``peers``/``channels`` — these
            // already match the API axis names (no storage→API
            // translation needed at this surface; the storage→API
            // mapping for ``guilds``→``groups`` is allowlist-only).
            var dropdownEl = overlayEntry.renderDiscoverableDropdown(
              account,
              axis,
              overlayState.values,
              null,  // vocab — per-agent overlay surface stays neutral
              function onOverlayChange(newValues) {
                overlayState.values = (newValues || []).slice();
                _summarize();
                onChange();
              }
            );
            if (dropdownEl) {
              // Wholesale replace the chip-list shell's children with
              // the dropdown. The wrapper still carries the
              // ``data-connector-acl-*`` attributes the collect path
              // looks up; the ``_overlayChipValues`` getter is the
              // canonical bridge so studio.js reads the dropdown's
              // selected ids (not its internal chip DOM).
              chiplist.innerHTML = '';
              chiplist.appendChild(dropdownEl);
              chiplist._overlayChipValues = function () {
                return overlayState.values.slice();
              };
              mounted = true;
            }
          }
          if (!mounted && helpers && helpers.wireChipListEditor) {
            helpers.wireChipListEditor(chiplist, {
              onChange: function () { _summarize(); onChange(); }
            });
          }
        }

        // Initial summary line.
        _summarize();
        return details;
      }

      // M11 F7 L11: per-account "Always Listen" toggle.
      // Greyed-out when account.config.always_listen is False (no semantic
      // effect anyway since the master is OFF; UI mirrors the data layer's
      // structural inertness). The save-path collection lives in
      // studio.js::collectFormData (mirrors the connector_acls precedent;
      // see Studio area for the dict assembly into ``connector_always_listen``).
      var alwaysListenForAccount = !!(alwaysListenMap && alwaysListenMap[account.id]);
      var accountAlwaysListenMaster = !!(account.config && account.config.always_listen);
      var alwaysListenRow = document.createElement('div');
      alwaysListenRow.className = 'field-row admin-pf-row connector-account-always-listen-row';
      var alwaysListenLabel = document.createElement('label');
      alwaysListenLabel.htmlFor = 'agent-always-listen-' + account.id;
      alwaysListenLabel.textContent = 'Always listen';
      alwaysListenRow.appendChild(alwaysListenLabel);
      // M11 F7 L12 hotfix: wrap the input in a `tool-enable-switch` label +
      // track span so the toggle renders with the styled iOS-style chrome
      // (the canonical primitive defined in admin.css:197-264, also consumed
      // by tools-editor.js / tools-grid.js / mcp-server-editor.js). Without
      // this wrapper the input rendered as a ~13px raw native checkbox,
      // perceptually invisible against the dark theme. Uses the `-track`
      // sibling class (which has real CSS rules) rather than the `-slider`
      // variant referenced in connector-account-editor.js — only `-track` is
      // styled.
      var alwaysListenSwitch = document.createElement('label');
      alwaysListenSwitch.className = 'tool-enable-switch';
      var alwaysListenInput = document.createElement('input');
      alwaysListenInput.type = 'checkbox';
      alwaysListenInput.id = 'agent-always-listen-' + account.id;
      alwaysListenInput.className = 'field-input agent-connector-always-listen-toggle';
      alwaysListenInput.setAttribute('data-field', 'connector_always_listen');
      alwaysListenInput.setAttribute('data-account-id', account.id);
      alwaysListenInput.setAttribute('data-testid', 'agent-connector-always-listen-' + account.id);
      alwaysListenInput.checked = alwaysListenForAccount;
      alwaysListenInput.disabled = !accountAlwaysListenMaster;
      // M11 F7 L11 (cycle-1 review): wire onChange() for dirty-tracking.
      // Mirrors the attach-toggle wiring at connectors-tab.js:452 — without
      // this, toggling the per-agent switch leaves the Save button disabled.
      alwaysListenInput.addEventListener('change', function () { onChange(); });
      alwaysListenSwitch.appendChild(alwaysListenInput);
      var alwaysListenTrack = document.createElement('span');
      alwaysListenTrack.className = 'tool-enable-switch-track';
      alwaysListenTrack.setAttribute('aria-hidden', 'true');
      alwaysListenSwitch.appendChild(alwaysListenTrack);
      alwaysListenRow.appendChild(alwaysListenSwitch);
      section.appendChild(alwaysListenRow);

      // M11 F10 L3: per-agent admit_dms opt-out row, slotted between
      // always-listen and the peers/channels axis rows. Both
      // always-listen and admit_dms are per-agent boolean overrides
      // keyed by account_id — they belong together visually, ahead of
      // the per-axis ACL editors.
      section.appendChild(_buildAdmitDmsRow());

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
