// App.studio.renderSelfConfigurationTab — agent-editor Self-configuration
// tab content (M21 F01 L02; approval mode + revision queue M21 F02 L02).
//
// A single enable/disable control + status line. Enabling mints a
// per-agent credential and creates a `streamable-http` MCP source row that
// the agent's own client presents to reach a loopback endpoint the
// platform serves itself — off by default for every agent (mission
// constraint). This tab is the ONLY place that toggles it; the row's
// attach checkbox on the MCPs tab renders checked-and-disabled (see
// mcps-tab.js) so the operator's per-tool controls still govern individual
// capabilities from there.
//
// M21 F02 L02 adds two operator controls below the enable toggle:
//   - an approval-mode toggle (immediate-post, like enable — NOT a
//     collectFormData() field): when ON, an agent's self-revision is held
//     in the queue as `pending` instead of applied.
//   - a pending-revision queue: approve/dismiss cards, each showing
//     base→proposed; clean approve is one-click; a staleness 409 renders
//     current-vs-proposed with an explicit override/confirm button. A
//     per-agent pending count is shown. On any action, we rely on
//     `_refreshAgentAfterSelfConfigurationChange` (studio.js) to re-render
//     the whole tab — the resolved row leaves the pending list naturally,
//     so there is no in-place badge swap to maintain.
//
// Public API:
//   App.studio.renderSelfConfigurationTab(panel, agent, callbacks)
//     panel      — DOM element (the Self-configuration tabpanel)
//     agent      — AgentConfig object, or null in create-mode
//     callbacks  — { fetchStatus(name) -> Promise<{enabled, requires_approval, ...}>,
//                    onEnable(name) -> Promise<{enabled, ...}>,
//                    onDisable(name) -> Promise<{enabled, ...}>,
//                    onSetApprovalMode(name, bool) -> Promise<{requires_approval}>,
//                    fetchRevisions(name) -> Promise<Array<revision>>,
//                    fetchPendingCount(name) -> Promise<{count}>,
//                    onApproveRevision(name, id, override) ->
//                       Promise<{applied:true}|{stale:true, detail}>,
//                    onDismissRevision(name, id) -> Promise<revision>,
//                    onRestoreRevision(name, id, side) -> Promise<revision> }
//
// M21 F02 L03 adds a revision-HISTORY section below the pending queue: the
// full revisions list (newest-first) — each entry shows field, before→after,
// timestamp, source (self/restore) and status. Restore is operator-direct
// (applies immediately regardless of approval mode). To make "restore any
// earlier value" literally true with NO duplicate buttons, the history
// renders one Restore control per DISTINCT value-node — the dedup of
// base_value + proposed_value across all `applied` rows — each restoring via
// an appropriate (revision_id, side). This surfaces the original (earliest
// base_value, side=base), each self-revised value (side=proposed) and any
// out-of-band operator-set value (a mid-row base_value) for free. On restore
// studio.js re-renders the whole tab, so the new restore row appears in the
// history with nothing to update in place.
//
// Save-flow note: unlike every other tab, these controls do NOT participate
// in collectFormData()/dirty-tracking — enable/disable and the approval-mode
// toggle are immediate API calls (mirrors the Danger Zone's Delete/Purge
// buttons), not form fields staged for the Save button.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Cross-render action-announcement bridge (a11y fix — SC 2.4.3 focus /
  // SC 4.1.3 status messages). Every action on this tab (enable/disable,
  // approval-mode toggle, approve/override/dismiss, restore) resolves
  // through studio.js's `_refreshAgentAfterSelfConfigurationChange`, which
  // tears down and rebuilds this whole panel (doSelect -> renderEditor)
  // BEFORE the action's own `.then()` callback runs here — so by the time
  // that callback fires, the clicked control no longer exists and the
  // browser has already reverted focus to document.body. Each action
  // handler stashes a short human-readable summary here (keyed by agent
  // name) right before invoking its callback; the next render of this tab
  // — if the action actually caused one; a stale-detected or failed action
  // does not — picks it up and moves focus there; the focus move alone
  // reliably conveys the summary (no live region, to avoid double
  // announcement), so a keyboard/screen-reader user working a queue of
  // several pending revisions isn't bounced to the top of the document
  // after every action.
  var pendingAction = null;

  function renderSelfConfigurationTab(panel, agent, callbacks) {
    callbacks = callbacks || {};
    panel.innerHTML = '';

    if (!agent) {
      var notice = document.createElement('p');
      notice.className = 'empty-state';
      notice.setAttribute('data-testid', 'self-configuration-save-first');
      notice.textContent = 'Save the agent first to enable self-configuration.';
      panel.appendChild(notice);
      return;
    }

    // Focus target + announcement for the just-completed action (see
    // `pendingAction` above). Also doubles as the fix for the history
    // list's over-announcing live region — a single concise summary here
    // replaces re-announcing the whole rebuilt history on every action.
    var actionStatus = document.createElement('p');
    actionStatus.className = 'self-configuration-action-status';
    actionStatus.setAttribute('data-testid', 'self-configuration-action-status');
    actionStatus.tabIndex = -1;
    panel.appendChild(actionStatus);

    var section = document.createElement('div');
    section.className = 'editor-section';

    var title = document.createElement('div');
    title.className = 'section-title';
    title.textContent = 'Self-configuration';
    section.appendChild(title);

    var description = document.createElement('p');
    description.className = 'self-configuration-description';
    description.textContent = 'When enabled, this agent can read its own configuration ' +
      'and revise its own description and system prompt through a dedicated MCP source. ' +
      'The operator’s per-tool controls on the MCPs tab still govern which capabilities ' +
      'the agent can actually use.';
    section.appendChild(description);

    var statusLine = document.createElement('p');
    statusLine.className = 'self-configuration-status';
    statusLine.setAttribute('data-testid', 'self-configuration-status');
    statusLine.setAttribute('role', 'status');
    statusLine.setAttribute('aria-live', 'polite');
    statusLine.textContent = 'Loading…';
    section.appendChild(statusLine);

    var errorLine = document.createElement('p');
    errorLine.className = 'self-configuration-error';
    errorLine.setAttribute('data-testid', 'self-configuration-error');
    errorLine.setAttribute('role', 'alert');
    errorLine.hidden = true;
    section.appendChild(errorLine);

    var toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'btn-outlined-primary self-configuration-toggle-btn';
    toggleBtn.setAttribute('data-testid', 'self-configuration-toggle-btn');
    toggleBtn.disabled = true;
    toggleBtn.textContent = '…';
    section.appendChild(toggleBtn);

    panel.appendChild(section);

    // ── M21 F02 L02 — approval-mode section ─────────────────────────────
    var approvalSection = document.createElement('div');
    approvalSection.className = 'editor-section self-configuration-approval-section';

    var approvalTitle = document.createElement('div');
    approvalTitle.className = 'section-title';
    approvalTitle.textContent = 'Approval mode';
    approvalSection.appendChild(approvalTitle);

    var approvalDesc = document.createElement('p');
    approvalDesc.className = 'self-configuration-description';
    approvalDesc.textContent = 'When approval mode is on, a revision this agent proposes to ' +
      'its own description or system prompt is held for your review instead of taking effect. ' +
      'You approve or dismiss each proposal below.';
    approvalSection.appendChild(approvalDesc);

    var approvalStatus = document.createElement('p');
    approvalStatus.className = 'self-configuration-status';
    approvalStatus.setAttribute('data-testid', 'approval-mode-status');
    approvalStatus.setAttribute('role', 'status');
    approvalStatus.setAttribute('aria-live', 'polite');
    approvalStatus.textContent = 'Loading…';
    approvalSection.appendChild(approvalStatus);

    var approvalError = document.createElement('p');
    approvalError.className = 'self-configuration-error';
    approvalError.setAttribute('data-testid', 'approval-mode-error');
    approvalError.setAttribute('role', 'alert');
    approvalError.hidden = true;
    approvalSection.appendChild(approvalError);

    var approvalBtn = document.createElement('button');
    approvalBtn.type = 'button';
    approvalBtn.className = 'btn-outlined-primary approval-mode-toggle-btn';
    approvalBtn.setAttribute('data-testid', 'approval-mode-toggle-btn');
    approvalBtn.disabled = true;
    approvalBtn.textContent = '…';
    approvalSection.appendChild(approvalBtn);

    panel.appendChild(approvalSection);

    // ── M21 F02 L02 — pending revision queue ────────────────────────────
    var queueSection = document.createElement('div');
    queueSection.className = 'editor-section self-configuration-queue-section';

    var queueTitle = document.createElement('div');
    queueTitle.className = 'section-title';
    queueTitle.textContent = 'Pending revisions';
    queueSection.appendChild(queueTitle);

    var countLine = document.createElement('p');
    countLine.className = 'self-configuration-pending-count';
    countLine.setAttribute('data-testid', 'pending-count');
    countLine.setAttribute('role', 'status');
    countLine.setAttribute('aria-live', 'polite');
    countLine.textContent = 'Loading…';
    queueSection.appendChild(countLine);

    var queueList = document.createElement('div');
    queueList.className = 'self-configuration-pending-queue';
    queueList.setAttribute('data-testid', 'pending-queue');
    queueSection.appendChild(queueList);

    panel.appendChild(queueSection);

    // ── M21 F02 L03 — revision history + restore ────────────────────────
    var historySection = document.createElement('div');
    historySection.className = 'editor-section self-configuration-history-section';

    var historyTitle = document.createElement('div');
    historyTitle.className = 'section-title';
    historyTitle.textContent = 'Revision history';
    historySection.appendChild(historyTitle);

    var historyDesc = document.createElement('p');
    historyDesc.className = 'self-configuration-description';
    historyDesc.textContent = 'Every change to this agent’s description and system prompt, ' +
      'newest first. Restore returns a field to any earlier value it held — it applies ' +
      'immediately (your restore is never held for approval) and is recorded as a new entry.';
    historySection.appendChild(historyDesc);

    // Restore controls: one per distinct value the fields have held.
    var restoreControls = document.createElement('div');
    restoreControls.className = 'self-configuration-restore-controls';
    restoreControls.setAttribute('data-testid', 'revision-restore-controls');
    restoreControls.setAttribute('role', 'group');
    restoreControls.setAttribute('aria-label', 'Restore an earlier value');
    historySection.appendChild(restoreControls);

    // The full timeline (all statuses). This is a data view the user
    // browses, not an append-only log — it is entirely rebuilt on every
    // load AND after every action elsewhere on the tab, so it must NOT be
    // a live region (that would re-announce the whole history on every
    // action). `role="group"` keeps it a named, focusable-by-AT region
    // without triggering announcements; the concise per-action summary
    // lives in `actionStatus` above instead.
    var historyList = document.createElement('div');
    historyList.className = 'self-configuration-history-list';
    historyList.setAttribute('data-testid', 'revision-history');
    historyList.setAttribute('role', 'group');
    historyList.setAttribute('aria-label', 'Revision history');
    historyList.textContent = 'Loading…';
    historySection.appendChild(historyList);

    panel.appendChild(historySection);

    // Consume any cross-render action announcement (see `pendingAction`
    // above) now that the whole panel has been (re)built — `actionStatus`
    // is attached to the DOM at this point, so focusing it works and the
    // browser's focus event announces its new text to screen readers.
    if (pendingAction && pendingAction.agentName === agent.name) {
      actionStatus.textContent = pendingAction.message;
      pendingAction = null;
      actionStatus.focus();
    }

    // ── enable/disable state machine ────────────────────────────────────
    function renderState(enabled) {
      statusLine.textContent = enabled
        ? 'Self-configuration is enabled for this agent.'
        : 'Self-configuration is disabled for this agent.';
      toggleBtn.textContent = enabled ? 'Disable' : 'Enable';
      toggleBtn.disabled = false;
      errorLine.hidden = true;
      errorLine.textContent = '';
      toggleBtn.onclick = function () {
        var action = enabled ? callbacks.onDisable : callbacks.onEnable;
        if (!action) return;
        pendingAction = {
          agentName: agent.name,
          message: enabled ? 'Disabled self-configuration.' : 'Enabled self-configuration.'
        };
        toggleBtn.disabled = true;
        action(agent.name).then(function (result) {
          renderState(!!(result && result.enabled));
        }).catch(function (err) {
          pendingAction = null;
          errorLine.hidden = false;
          errorLine.textContent = 'Failed to ' + (enabled ? 'disable' : 'enable') +
            ' self-configuration: ' + (err && err.message ? err.message : String(err));
          toggleBtn.disabled = false;
        });
      };
    }

    // ── approval-mode toggle (immediate-post, like enable) ──────────────
    function renderApprovalState(requiresApproval) {
      approvalStatus.textContent = requiresApproval
        ? 'Approval mode is on — this agent’s self-revisions require your approval.'
        : 'Approval mode is off — this agent’s self-revisions take effect without approval.';
      approvalBtn.textContent = requiresApproval ? 'Turn off approval mode' : 'Turn on approval mode';
      approvalBtn.disabled = false;
      approvalError.hidden = true;
      approvalError.textContent = '';
      approvalBtn.onclick = function () {
        if (!callbacks.onSetApprovalMode) return;
        pendingAction = {
          agentName: agent.name,
          message: requiresApproval ? 'Turned off approval mode.' : 'Turned on approval mode.'
        };
        approvalBtn.disabled = true;
        // On success studio.js re-renders the whole tab (the flag lives
        // outside the Save flow), so the fresh render reflects the new
        // value — no local state update needed here.
        callbacks.onSetApprovalMode(agent.name, !requiresApproval).catch(function (err) {
          pendingAction = null;
          approvalError.hidden = false;
          approvalError.textContent = 'Failed to change approval mode: ' +
            (err && err.message ? err.message : String(err));
          approvalBtn.disabled = false;
        });
      };
    }

    // ── pending queue rendering ─────────────────────────────────────────
    function renderCard(revision) {
      var card = document.createElement('div');
      card.className = 'self-configuration-revision-card';
      card.setAttribute('data-testid', 'revision-card');
      card.setAttribute('data-revision-id', revision.id);

      var fieldLabel = document.createElement('div');
      fieldLabel.className = 'revision-field';
      fieldLabel.setAttribute('data-testid', 'revision-field');
      fieldLabel.textContent = revision.field === 'system_prompt'
        ? 'System prompt' : 'Description';
      card.appendChild(fieldLabel);

      // base → proposed shown on the clean path too (for a non-stale row
      // base_value == current, so "see what would change" is satisfied on
      // the one-click path, not only the 409 path).
      var baseBlock = document.createElement('div');
      baseBlock.className = 'revision-base';
      var baseHdr = document.createElement('div');
      baseHdr.className = 'revision-value-label';
      baseHdr.textContent = 'Current';
      var baseVal = document.createElement('pre');
      baseVal.className = 'revision-value';
      baseVal.setAttribute('data-testid', 'revision-base');
      baseVal.textContent = revision.base_value;
      baseBlock.appendChild(baseHdr);
      baseBlock.appendChild(baseVal);
      card.appendChild(baseBlock);

      var proposedBlock = document.createElement('div');
      proposedBlock.className = 'revision-proposed';
      var proposedHdr = document.createElement('div');
      proposedHdr.className = 'revision-value-label';
      proposedHdr.textContent = 'Proposed';
      var proposedVal = document.createElement('pre');
      proposedVal.className = 'revision-value';
      proposedVal.setAttribute('data-testid', 'revision-proposed');
      proposedVal.textContent = revision.proposed_value;
      proposedBlock.appendChild(proposedHdr);
      proposedBlock.appendChild(proposedVal);
      card.appendChild(proposedBlock);

      var actionError = document.createElement('p');
      actionError.className = 'self-configuration-error';
      actionError.setAttribute('data-testid', 'revision-error');
      actionError.setAttribute('role', 'alert');
      actionError.hidden = true;
      card.appendChild(actionError);

      var actions = document.createElement('div');
      actions.className = 'revision-actions';

      // A short snippet of the proposed value distinguishes this card's
      // Approve/Dismiss from every other card's for a screen-reader rotor
      // (SC 2.4.6) — plain "Approve"/"Dismiss" is identical across cards.
      var snippet = revision.proposed_value ? revision.proposed_value : '(empty)';
      if (snippet.length > 40) snippet = snippet.slice(0, 40) + '…';
      var fieldLower = fieldName(revision.field).toLowerCase();

      var approveBtn = document.createElement('button');
      approveBtn.type = 'button';
      approveBtn.className = 'btn-filled-primary revision-approve-btn';
      approveBtn.setAttribute('data-testid', 'revision-approve-btn');
      approveBtn.setAttribute('aria-label', 'Approve ' + fieldLower + ' revision: “' + snippet + '”');
      approveBtn.textContent = 'Approve';

      var dismissBtn = document.createElement('button');
      dismissBtn.type = 'button';
      dismissBtn.className = 'btn-outlined-primary revision-dismiss-btn';
      dismissBtn.setAttribute('data-testid', 'revision-dismiss-btn');
      dismissBtn.setAttribute('aria-label', 'Dismiss ' + fieldLower + ' revision: “' + snippet + '”');
      dismissBtn.textContent = 'Dismiss';

      actions.appendChild(approveBtn);
      actions.appendChild(dismissBtn);
      card.appendChild(actions);

      // Staleness panel (rendered only on a 409 response) — current vs
      // proposed with an explicit override/confirm button.
      var stalePanel = document.createElement('div');
      stalePanel.className = 'revision-stale';
      stalePanel.setAttribute('data-testid', 'revision-stale');
      stalePanel.hidden = true;
      card.appendChild(stalePanel);

      function setBusy(busy) {
        approveBtn.disabled = busy;
        dismissBtn.disabled = busy;
      }

      function showActionError(err) {
        actionError.hidden = false;
        actionError.textContent = 'Action failed: ' +
          (err && err.message ? err.message : String(err));
        setBusy(false);
      }

      function renderStale(detail) {
        // The row drifted since the agent proposed. Show what re-approving
        // would overwrite and require an explicit override confirm.
        stalePanel.hidden = false;
        stalePanel.textContent = '';

        var warn = document.createElement('p');
        warn.className = 'revision-stale-warning';
        warn.setAttribute('role', 'alert');
        warn.textContent = 'This value has changed since the agent proposed its revision. ' +
          'Approving will overwrite the current value below.';
        stalePanel.appendChild(warn);

        var curHdr = document.createElement('div');
        curHdr.className = 'revision-value-label';
        curHdr.textContent = 'Current value now';
        var curVal = document.createElement('pre');
        curVal.className = 'revision-value';
        curVal.setAttribute('data-testid', 'revision-current');
        curVal.textContent = detail.current_value;
        stalePanel.appendChild(curHdr);
        stalePanel.appendChild(curVal);

        var propHdr = document.createElement('div');
        propHdr.className = 'revision-value-label';
        propHdr.textContent = 'Proposed value';
        var propVal = document.createElement('pre');
        propVal.className = 'revision-value';
        propVal.setAttribute('data-testid', 'revision-stale-proposed');
        propVal.textContent = detail.proposed_value;
        stalePanel.appendChild(propHdr);
        stalePanel.appendChild(propVal);

        var overrideBtn = document.createElement('button');
        overrideBtn.type = 'button';
        overrideBtn.className = 'btn-filled-primary revision-override-btn';
        overrideBtn.setAttribute('data-testid', 'revision-override-btn');
        overrideBtn.setAttribute('aria-label',
          'Overwrite and approve ' + fieldLower + ' revision: “' + snippet + '”');
        overrideBtn.textContent = 'Overwrite and approve';
        overrideBtn.onclick = function () {
          if (!callbacks.onApproveRevision) return;
          pendingAction = {
            agentName: agent.name,
            message: 'Approved the ' + fieldLower + ' revision, overwriting the current value.'
          };
          setBusy(true);
          overrideBtn.disabled = true;
          callbacks.onApproveRevision(agent.name, revision.id, true).then(function (result) {
            // Override should apply (re-captures base_value). On success
            // studio.js re-renders the tab; nothing more to do here.
            if (result && result.stale) {
              // Extremely unlikely (drifted again between calls) — re-render.
              pendingAction = null;
              renderStale(result.detail);
              overrideBtn.disabled = false;
            }
          }).catch(function (err) {
            pendingAction = null;
            showActionError(err);
          });
        };
        stalePanel.appendChild(overrideBtn);
        setBusy(false);
      }

      approveBtn.onclick = function () {
        if (!callbacks.onApproveRevision) return;
        pendingAction = { agentName: agent.name, message: 'Approved the ' + fieldLower + ' revision.' };
        setBusy(true);
        callbacks.onApproveRevision(agent.name, revision.id, false).then(function (result) {
          if (result && result.stale) {
            // No refresh happened for a stale detection — the card stays
            // mounted and gains the override panel in place, so there is
            // nothing to announce/focus yet (the override click above
            // covers the actual apply).
            pendingAction = null;
            renderStale(result.detail);
          }
          // On applied, studio.js re-renders the whole tab (the resolved
          // row leaves the pending list) — no local removal needed.
        }).catch(function (err) {
          pendingAction = null;
          showActionError(err);
        });
      };

      dismissBtn.onclick = function () {
        if (!callbacks.onDismissRevision) return;
        pendingAction = { agentName: agent.name, message: 'Dismissed the ' + fieldLower + ' revision.' };
        setBusy(true);
        callbacks.onDismissRevision(agent.name, revision.id).catch(function (err) {
          pendingAction = null;
          showActionError(err);
        });
      };

      return card;
    }

    function renderQueue(revisions) {
      queueList.innerHTML = '';
      var pending = (revisions || []).filter(function (r) { return r.status === 'pending'; });
      countLine.textContent = pending.length === 1
        ? '1 revision awaiting your approval.'
        : pending.length + ' revisions awaiting your approval.';
      if (pending.length === 0) {
        var empty = document.createElement('p');
        empty.className = 'empty-state';
        empty.setAttribute('data-testid', 'pending-queue-empty');
        empty.textContent = 'No revisions are awaiting approval.';
        queueList.appendChild(empty);
        return;
      }
      pending.forEach(function (rev) {
        queueList.appendChild(renderCard(rev));
      });
    }

    // ── M21 F02 L03 — revision history + restore rendering ──────────────
    function fieldName(field) {
      return field === 'system_prompt' ? 'System prompt' : 'Description';
    }

    function renderHistory(revisions) {
      revisions = revisions || [];

      // ── the full timeline (newest-first, all statuses) ──
      historyList.innerHTML = '';
      if (revisions.length === 0) {
        var emptyHist = document.createElement('p');
        emptyHist.className = 'empty-state';
        emptyHist.setAttribute('data-testid', 'revision-history-empty');
        emptyHist.textContent = 'No revisions yet.';
        historyList.appendChild(emptyHist);
      } else {
        revisions.forEach(function (rev) {
          var entry = document.createElement('div');
          entry.className = 'self-configuration-history-entry';
          entry.setAttribute('data-testid', 'revision-history-entry');
          entry.setAttribute('data-revision-id', rev.id);
          entry.setAttribute('data-field', rev.field);
          entry.setAttribute('data-status', rev.status);
          entry.setAttribute('data-source', rev.source);

          var head = document.createElement('div');
          head.className = 'history-entry-head';
          var fieldTag = document.createElement('span');
          fieldTag.className = 'history-entry-field';
          fieldTag.textContent = fieldName(rev.field);
          head.appendChild(fieldTag);
          var meta = document.createElement('span');
          meta.className = 'history-entry-meta';
          // source + status + timestamp, human-readable and attributable.
          var sourceLabel = rev.source === 'restore' ? 'restored' : 'self-revised';
          meta.textContent = sourceLabel + ' · ' + rev.status + ' · ' + rev.created_at;
          head.appendChild(meta);
          entry.appendChild(head);

          var change = document.createElement('div');
          change.className = 'history-entry-change';
          var beforeVal = document.createElement('pre');
          beforeVal.className = 'revision-value history-entry-before';
          beforeVal.textContent = rev.base_value;
          var arrow = document.createElement('span');
          arrow.className = 'history-entry-arrow';
          arrow.setAttribute('aria-label', 'changed to');
          arrow.textContent = '→';
          var afterVal = document.createElement('pre');
          afterVal.className = 'revision-value history-entry-after';
          afterVal.textContent = rev.proposed_value;
          change.appendChild(beforeVal);
          change.appendChild(arrow);
          change.appendChild(afterVal);
          entry.appendChild(change);

          historyList.appendChild(entry);
        });
      }

      // ── restore controls: one per DISTINCT value-node ──
      // Dedup base_value + proposed_value across all `applied` rows, PER
      // FIELD. `description` and `system_prompt` are independent (DD1) and
      // both default to empty string, so a raw-value-only dedup key would
      // let one field's node claim a value the other field also held,
      // silently dropping that field's restore control (e.g. two untouched
      // fields both showing "" as their original). Scoping the key by
      // `rev.field` keeps each field's value-space independent. Walk
      // oldest-first so the first (kept) occurrence of each (field, value)
      // is its earliest holder — the earliest base_value is the ORIGINAL.
      // Each node carries a (revision_id, side) that reinstates it; any one
      // works if a value recurs within the same field. Non-applied rows
      // contribute no node.
      restoreControls.innerHTML = '';
      var applied = revisions.filter(function (r) { return r.status === 'applied'; });
      var oldestFirst = applied.slice().reverse();
      var seen = Object.create(null);
      var nodes = [];
      oldestFirst.forEach(function (rev) {
        [['base', rev.base_value], ['proposed', rev.proposed_value]].forEach(function (pair) {
          var side = pair[0];
          var value = pair[1];
          // JSON-encode the pair rather than concatenating with a plain
          // separator — avoids any (however unlikely) boundary ambiguity
          // between a field name and an arbitrary value string.
          var key = JSON.stringify([rev.field, value]);
          if (Object.prototype.hasOwnProperty.call(seen, key)) return;
          seen[key] = true;
          nodes.push({ value: value, side: side, revisionId: rev.id, field: rev.field });
        });
      });

      if (nodes.length === 0) {
        var emptyNodes = document.createElement('p');
        emptyNodes.className = 'empty-state';
        emptyNodes.setAttribute('data-testid', 'revision-restore-empty');
        emptyNodes.textContent = 'No earlier values to restore.';
        restoreControls.appendChild(emptyNodes);
        return;
      }

      nodes.forEach(function (node) {
        var row = document.createElement('div');
        row.className = 'self-configuration-restore-node';
        row.setAttribute('data-testid', 'revision-restore-node');
        row.setAttribute('data-field', node.field);
        row.setAttribute('data-side', node.side);

        var preview = document.createElement('pre');
        preview.className = 'revision-value restore-node-value';
        preview.textContent = node.value;
        row.appendChild(preview);

        var nodeError = document.createElement('p');
        nodeError.className = 'self-configuration-error';
        nodeError.setAttribute('data-testid', 'revision-restore-error');
        nodeError.setAttribute('role', 'alert');
        nodeError.hidden = true;
        row.appendChild(nodeError);

        // A short snippet of this node's own value distinguishes it from
        // every other Restore button for a screen-reader rotor (SC 2.4.6)
        // — plain "Restore this description value" repeats verbatim across
        // nodes. Nodes are already deduped per-field (see above), so the
        // snippet is unique among a field's own nodes.
        var nodeSnippet = node.value ? node.value : '(empty)';
        if (nodeSnippet.length > 40) nodeSnippet = nodeSnippet.slice(0, 40) + '…';

        var restoreBtn = document.createElement('button');
        restoreBtn.type = 'button';
        restoreBtn.className = 'btn-outlined-primary revision-restore-btn';
        restoreBtn.setAttribute('data-testid', 'revision-restore-btn');
        restoreBtn.setAttribute('data-revision-id', node.revisionId);
        restoreBtn.setAttribute('data-side', node.side);
        // Labelled for assistive tech — names the field it restores and a
        // snippet of the value, so it reads distinctly from sibling nodes.
        restoreBtn.setAttribute('aria-label',
          'Restore this ' + fieldName(node.field).toLowerCase() + ' value: “' + nodeSnippet + '”');
        restoreBtn.textContent = 'Restore';
        restoreBtn.onclick = function () {
          if (!callbacks.onRestoreRevision) return;
          pendingAction = {
            agentName: agent.name,
            message: 'Restored ' + fieldName(node.field).toLowerCase() + ' to an earlier value.'
          };
          restoreBtn.disabled = true;
          nodeError.hidden = true;
          nodeError.textContent = '';
          // On success studio.js re-renders the whole tab — the new restore
          // row appears in the history; nothing to update in place.
          callbacks.onRestoreRevision(agent.name, node.revisionId, node.side)
            .catch(function (err) {
              pendingAction = null;
              nodeError.hidden = false;
              nodeError.textContent = 'Restore failed: ' +
                (err && err.message ? err.message : String(err));
              restoreBtn.disabled = false;
            });
        };
        row.appendChild(restoreBtn);

        restoreControls.appendChild(row);
      });
    }

    // ── initial load ────────────────────────────────────────────────────
    if (!callbacks.fetchStatus) {
      renderState(false);
      renderApprovalState(false);
    } else {
      callbacks.fetchStatus(agent.name).then(function (status) {
        renderState(!!(status && status.enabled));
        renderApprovalState(!!(status && status.requires_approval));
      }).catch(function () {
        statusLine.textContent = 'Unable to load self-configuration status.';
        approvalStatus.textContent = 'Unable to load approval-mode status.';
      });
    }

    if (callbacks.fetchRevisions) {
      // One fetch feeds both views: the queue is the `pending` subset, the
      // history is the whole list.
      callbacks.fetchRevisions(agent.name).then(function (revisions) {
        renderQueue(revisions);
        renderHistory(revisions);
      }).catch(function () {
        countLine.textContent = 'Unable to load pending revisions.';
        historyList.textContent = 'Unable to load revision history.';
      });
    } else {
      renderQueue([]);
      renderHistory([]);
    }
  }

  window.App.studio.renderSelfConfigurationTab = renderSelfConfigurationTab;
})();
