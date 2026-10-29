// App.studio.selfConfigStatus — the Self-configuration tab's frame and status
// logic: the action-status focus target, the enable and approval-mode switches and
// their status lines, the status and revisions refetches, and the handle's
// setAgent / destroy (M31 F2 L10b: split out of self-configuration-tab.js, a pure
// restructure). `build(ctx)` appends the first three sections to `ctx.panel` (the
// entry builds the queue, history and external sections after it) and publishes
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

    // Error and status lines are App.ui.status without an LED (the words alone, as
    // before); the class on the root keeps the tab's own size, ink and spacing.
    var section = App.ui.section({ title: 'Self-configuration', titleTag: 'h3' });

    var description = document.createElement('p');
    description.className = 'self-configuration-description';
    description.textContent = 'When enabled, this agent can read its own configuration ' +
      'and revise its own description and system prompt through a dedicated MCP source. ' +
      'The operator’s per-tool controls on the Tools tab still govern which capabilities ' +
      'the agent can actually use.';
    section.body.appendChild(description);

    var statusLine = App.ui.status({
      state: 'idle', text: 'Loading…', led: false, testid: 'self-configuration-status'
    });
    statusLine.el.classList.add('self-configuration-status');
    section.body.appendChild(statusLine.el);

    var errorLine = App.ui.status({
      state: 'danger', led: false, role: 'alert', testid: 'self-configuration-error'
    });
    errorLine.el.classList.add('self-configuration-error');
    errorLine.el.hidden = true;
    section.body.appendChild(errorLine.el);

    // Enable/disable is a 2-state immediate-post control: an App.ui.toggle (a
    // switch), its label beside it. The testid is on the native input, which stays the
    // interactive control; it is inert until the status resolves.
    var toggleCtl = App.ui.toggle({
      label: 'Enable self-configuration',
      testid: 'self-configuration-toggle-btn',
      disabled: true
    });
    toggleCtl.el.classList.add('self-configuration-toggle-switch');
    var toggleInput = toggleCtl.control;
    section.body.appendChild(toggleCtl.el);

    panel.appendChild(section.el);

    // ── M21 F02 L02 — approval-mode section ─────────────────────────────
    var approvalSection = App.ui.section({
      title: 'Approval mode',
      titleTag: 'h3',
      className: 'self-configuration-approval-section'
    });

    var approvalDesc = document.createElement('p');
    approvalDesc.className = 'self-configuration-description';
    approvalDesc.textContent = 'When approval mode is on, a revision this agent proposes to ' +
      'its own description or system prompt is held for your review instead of taking effect. ' +
      'You approve or dismiss each proposal below.';
    approvalSection.body.appendChild(approvalDesc);

    var approvalStatus = App.ui.status({
      state: 'idle', text: 'Loading…', led: false, testid: 'approval-mode-status'
    });
    approvalStatus.el.classList.add('self-configuration-status');
    approvalSection.body.appendChild(approvalStatus.el);

    var approvalError = App.ui.status({
      state: 'danger', led: false, role: 'alert', testid: 'approval-mode-error'
    });
    approvalError.el.classList.add('self-configuration-error');
    approvalError.el.hidden = true;
    approvalSection.body.appendChild(approvalError.el);

    // Same switch treatment as the enable control above: 2-state, immediate-post.
    var approvalCtl = App.ui.toggle({
      label: 'Require approval for self-revisions',
      testid: 'approval-mode-toggle-btn',
      disabled: true
    });
    approvalCtl.el.classList.add('self-configuration-toggle-switch');
    var approvalInput = approvalCtl.control;
    approvalSection.body.appendChild(approvalCtl.el);

    panel.appendChild(approvalSection.el);

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
          refetchRevisions();
        }).catch(function (err) {
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

    function refetchRevisions() {
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
        ctx.renderQueue(revisions);
        ctx.renderHistory(revisions);
      }).catch(function () {
        if (!live()) return;
        // Never leave an actionable card for a queue that cannot be confirmed.
        ctx.queueList.textContent = '';
        ctx.setCountLine('Unable to load pending revisions.');
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
