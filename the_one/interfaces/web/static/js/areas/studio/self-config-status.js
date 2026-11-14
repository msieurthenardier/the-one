// App.studio.selfConfigStatus — the Self-configuration tab's frame and status
// logic: the action-status focus target, the page eyebrow with the Agent prompt card
// (M33 F4 L06: `ctx.cardsHost`, `ctx.cards.prompt`; the card holds the enable and
// approval-mode switches and their status lines), the status and revisions refetches,
// and the handle's setAgent / destroy (M31 F2 L10b: split out of
// self-configuration-tab.js). `build(ctx)` appends the action status and the eyebrow
// section to `ctx.panel` (the entry builds the queue and history bodies, the Routines
// card and the External access section after it) and publishes
// `ctx.announce`, `ctx.refetchStatus`, `ctx.refetchRevisions`, `ctx.setAgent` and
// `ctx.destroy`. Per-mount state (`agent`, `destroyed`, the sequence counters,
// `approvalReady`) lives on `ctx`, never at module level; the cross-module renderers
// (`ctx.renderQueue`, `ctx.renderHistory`, `ctx.renderExternalState`,
// `ctx.hideTokenReveal`) are read at call time.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function build(ctx) {
    var panel = ctx.panel;
    var callbacks = ctx.callbacks;

    // Focus target + announcement for the just-completed action (see
    // `announce` below). Also doubles as the fix for the history
    // list's over-announcing live region — a single concise summary here
    // replaces re-announcing the whole rebuilt history on every action.
    var actionStatus = document.createElement('p');
    actionStatus.className = 'self-configuration-action-status';
    actionStatus.setAttribute('data-testid', 'self-configuration-action-status');
    actionStatus.tabIndex = -1;
    panel.appendChild(actionStatus);

    // The page eyebrow ("What this agent can change") holds the two item cards; the External
    // access section follows it at the bottom of the tab (M33 F4 L06, mockup SC2).
    var page = App.ui.section({
      title: 'What this agent can change',
      titleTag: 'h2',
      className: 'self-config-items-section'
    });
    panel.appendChild(page.el);
    ctx.cardsHost = page.body;
    ctx.cards = {};

    // The Agent prompt card: the enable switch, title, "Require approval" switch and the
    // one-line description; its two expanders are filled by the revisions and history modules.
    var card = window.App.studio.selfConfigCard.create({
      key: 'prompt',
      title: 'Agent prompt',
      description: 'Edit its own description and system prompt.',
      enableLabel: 'Let this agent edit its description and system prompt',
      approvalLabel: 'Require approval for prompt edits'
    });
    // The card sets no test ids (the registry guard reads literals): this item's own.
    card.el.setAttribute('data-testid', 'self-config-card-prompt');
    card.enable.control.setAttribute('data-testid', 'self-configuration-toggle-btn');
    card.approval.control.setAttribute('data-testid', 'approval-mode-toggle-btn');
    card.queue.details.el.setAttribute('data-testid', 'self-config-prompt-waiting');
    card.queue.details.summary.setAttribute('data-testid', 'self-config-prompt-waiting-summary');
    card.queue.chip.setAttribute('data-testid', 'pending-count');
    card.queue.zero.setAttribute('data-testid', 'pending-queue-empty');
    card.history.details.el.setAttribute('data-testid', 'revision-history-details');
    card.history.details.summary.setAttribute('data-testid', 'revision-history-details-summary');
    ctx.cards.prompt = card;
    page.body.appendChild(card.el);

    // Error and status lines are App.ui.status without an LED (the words alone, as
    // before); the class on the root keeps the tab's own size, ink and spacing.
    var statusLine = App.ui.status({
      state: 'idle', text: 'Loading…', led: false, live: 'off', testid: 'self-configuration-status'
    });
    statusLine.el.classList.add('self-configuration-status');
    // The switch shows the state; the words stay for assistive technology, not as static text.
    statusLine.el.classList.add('visually-hidden');
    card.statusHost.appendChild(statusLine.el);

    var errorLine = App.ui.status({
      state: 'danger', led: false, role: 'alert', testid: 'self-configuration-error'
    });
    errorLine.el.classList.add('self-configuration-error');
    errorLine.el.hidden = true;
    card.statusHost.appendChild(errorLine.el);

    // Enable/disable is a 2-state immediate-post control: the card's switch (an App.ui.toggle).
    // The testid is on the native input, which stays the interactive control; it is inert until
    // the status resolves.
    var toggleCtl = card.enable;
    var toggleInput = toggleCtl.control;

    var approvalStatus = App.ui.status({
      state: 'idle', text: 'Loading…', led: false, live: 'off', testid: 'approval-mode-status'
    });
    approvalStatus.el.classList.add('self-configuration-status');
    approvalStatus.el.classList.add('visually-hidden');
    card.statusHost.appendChild(approvalStatus.el);

    var approvalError = App.ui.status({
      state: 'danger', led: false, role: 'alert', testid: 'approval-mode-error'
    });
    approvalError.el.classList.add('self-configuration-error');
    approvalError.el.hidden = true;
    card.statusHost.appendChild(approvalError.el);

    // Same switch treatment as the enable control above: 2-state, immediate-post.
    var approvalCtl = card.approval;
    var approvalInput = approvalCtl.control;

    function showError(line, message) {
      line.el.hidden = false;
      line.set('danger', message);
    }
    function clearError(line) {
      line.el.hidden = true;
      line.set('danger', '');
    }

    // Write the just-completed action's summary to `actionStatus` and move focus
    // there. Called on success BEFORE the refetch (see the comment at the top).
    function announce(message) {
      if (ctx.destroyed) return;
      actionStatus.textContent = message;
      actionStatus.focus();
    }

    // The record this mount shows (setAgent replaces it; handlers read it at call
    // time). The enabled flag is NOT on it: that comes from the status fetch.
    ctx.approvalReady = false;

    // ── enable/disable state machine ────────────────────────────────────
    function renderState(enabled) {
      statusLine.set('idle', enabled
        ? 'Self-configuration is enabled for this agent.'
        : 'Self-configuration is disabled for this agent.');
      toggleCtl.setChecked(enabled);
      toggleCtl.setDisabled(false);
      passiveRevisionsError = false;
      clearError(errorLine);
      // `change` fires after the browser has already flipped `.checked` to
      // the new (opposite of `enabled`) state — that IS the "flip on
      // change" immediate-post behavior the switch preserves from the old
      // button's onclick. On failure, revert to the pre-click state.
      toggleInput.onchange = function () {
        var action = enabled ? callbacks.onDisable : callbacks.onEnable;
        if (!action) { toggleCtl.setChecked(enabled); return; }
        toggleCtl.setDisabled(true);
        action(ctx.agent.name).then(function (result) {
          if (ctx.destroyed) return;
          announce(enabled ? 'Disabled self-configuration.' : 'Enabled self-configuration.');
          var nowEnabled = !!(result && result.enabled);
          // The status line, approval state and External access follow the status
          // fetch; the result is the fallback when it fails. On disable the
          // External access section hides any token reveal (the credentials were
          // revoked). The revisions are refetched too: disable supersedes the
          // pending ones.
          refetchStatus({ external: true, fallbackEnabled: nowEnabled });
          // Disable supersedes the pending revisions: the count drops at once.
          if (!nowEnabled) ctx.setWaitingCount('prompt', 0);
          refetchRevisions();
        }).catch(function (err) {
          passiveRevisionsError = false;
          showError(errorLine, 'Failed to ' + (enabled ? 'disable' : 'enable') +
            ' self-configuration: ' + (err && err.message ? err.message : String(err)));
          toggleCtl.setChecked(enabled);
          toggleCtl.setDisabled(false);
        });
      };
    }

    // ── approval-mode toggle (immediate-post, like enable) ──────────────
    function renderApprovalState(requiresApproval) {
      approvalStatus.set('idle', requiresApproval
        ? 'Approval mode is on — this agent’s self-revisions require your approval.'
        : 'Approval mode is off — this agent’s self-revisions take effect without approval.');
      approvalCtl.setChecked(requiresApproval);
      approvalCtl.setDisabled(false);
      ctx.approvalReady = true;
      clearError(approvalError);
      approvalInput.onchange = function () {
        if (!callbacks.onSetApprovalMode) { approvalCtl.setChecked(requiresApproval); return; }
        approvalCtl.setDisabled(true);
        // The flag lives outside the Save flow; on success the local status is
        // refetched (the editor also patches this tab through setAgent).
        callbacks.onSetApprovalMode(ctx.agent.name, !requiresApproval).then(function () {
          if (ctx.destroyed) return;
          announce(requiresApproval ? 'Turned off approval mode.' : 'Turned on approval mode.');
          refetchStatus({ external: false, fallbackApproval: !requiresApproval });
        }).catch(function (err) {
          showError(approvalError, 'Failed to change approval mode: ' +
            (err && err.message ? err.message : String(err)));
          approvalCtl.setChecked(requiresApproval);
          approvalCtl.setDisabled(false);
        });
      };
    }

    // ── loads and refetches ─────────────────────────────────────────────
    // Each is behind its own sequence counter and the mount's `destroyed` flag, so
    // a late response for an older request, or for a mount that has gone, is
    // dropped. `opts.external` also renders the External access state (enable and
    // disable; the initial load); `opts.fallback*` is what a failed refetch
    // falls back to, so a toggle never stays disabled.
    function refetchStatus(opts) {
      opts = opts || {};
      var seq = ++ctx.statusSeq;
      function live() { return !ctx.destroyed && seq === ctx.statusSeq; }
      if (!callbacks.fetchStatus) {
        renderState(false);
        renderApprovalState(false);
        ctx.renderExternalState(false);
        return Promise.resolve();
      }
      return callbacks.fetchStatus(ctx.agent.name).then(function (status) {
        if (!live()) return;
        renderState(!!(status && status.enabled));
        renderApprovalState(!!(status && status.requires_approval));
        if (opts.external !== false) ctx.renderExternalState(!!(status && status.enabled));
      }).catch(function () {
        if (!live()) return;
        if (opts.fallbackEnabled !== undefined) {
          renderState(opts.fallbackEnabled);
          ctx.renderExternalState(opts.fallbackEnabled);
          return;
        }
        if (opts.fallbackApproval !== undefined) {
          renderApprovalState(opts.fallbackApproval);
          return;
        }
        statusLine.set('idle', 'Unable to load self-configuration status.');
        approvalStatus.set('idle', 'Unable to load approval-mode status.');
        ctx.setExternalStatus('Unable to load external-access status.');
      });
    }

    // `passive` (squawk 0318): a refetch the operator did not ask for (the window or tab came
    // back); a failure keeps the shown waiting list and says so on the error line.
    var passiveRevisionsError = false;
    function refetchRevisions(passive) {
      var seq = ++ctx.revisionsSeq;
      function live() { return !ctx.destroyed && seq === ctx.revisionsSeq; }
      if (!callbacks.fetchRevisions) {
        ctx.renderQueue([]);
        ctx.renderHistory([]);
        return Promise.resolve();
      }
      // One fetch feeds both views: the queue is the `pending` subset, the
      // history is the whole list.
      return callbacks.fetchRevisions(ctx.agent.name).then(function (revisions) {
        if (!live()) return;
        if (passiveRevisionsError) { passiveRevisionsError = false; clearError(errorLine); }
        ctx.renderQueue(revisions);
        ctx.renderHistory(revisions);
      }).catch(function () {
        if (!live()) return;
        if (passive) {
          // Announce once per failure episode, and never over a real action error.
          if (passiveRevisionsError || !errorLine.el.hidden) return;
          passiveRevisionsError = true;
          showError(errorLine, 'Unable to refresh waiting changes.');
          return;
        }
        passiveRevisionsError = false;
        // Never leave an actionable card for a queue that cannot be confirmed.
        ctx.queueList.textContent = '';
        ctx.cards.prompt.queue.setUnavailable('unable to load pending revisions.');
        ctx.historyList.textContent = 'Unable to load revision history.';
      });
    }

    // The editor's same-identity update (patch): store the record and follow the
    // approval flag, which lives on it. Nothing is rebuilt and nothing is fetched.
    // An approval toggle in flight (its input disabled) or a status not yet loaded
    // is left to its own fetch.
    function setAgent(a) {
      if (ctx.destroyed || !a) return;
      ctx.agent = a;
      if (ctx.approvalReady && !approvalInput.disabled &&
          typeof a.self_revision_requires_approval === 'boolean') {
        renderApprovalState(a.self_revision_requires_approval);
      }
    }

    // Drop in-flight responses and the copy-once token (it never outlives the mount).
    function destroy() {
      ctx.destroyed = true;
      ctx.statusSeq += 1;
      ctx.revisionsSeq += 1;
      ctx.hideTokenReveal();
    }

    ctx.announce = announce;
    ctx.refetchStatus = refetchStatus;
    ctx.refetchRevisions = refetchRevisions;
    ctx.setAgent = setAgent;
    ctx.destroy = destroy;
  }

  window.App.studio.selfConfigStatus = { build: build };
})();
