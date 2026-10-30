// App.studio.renderSelfConfigurationTab — agent-editor Self-configuration
// tab content (M21 F01 L02; approval mode + revision queue M21 F02 L02).
//
// A single enable/disable control + status line. Enabling mints a
// per-agent credential and creates a `streamable-http` MCP source row that
// the agent's own client presents to reach a loopback endpoint the
// platform serves itself — off by default for every agent (mission
// constraint). This tab is the ONLY place that toggles it; the row's
// attach checkbox on the Tools tab renders checked-and-disabled (see
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
//     per-agent pending count is shown. On any action the tab refetches its
//     own revisions (or status) locally (M31 F2 L10a) — the resolved row
//     leaves the pending list naturally; the editor no longer rebuilds it.
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
//                    onApproveRevision(name, id, override) ->
//                       Promise<{applied:true}|{stale:true, detail}>,
//                    onDismissRevision(name, id) -> Promise<revision>,
//                    onRestoreRevision(name, id, side) -> Promise<revision>,
//                    // M21 F03 L03 — external-client credentials:
//                    onMintExternalCredential(name, label) ->
//                       Promise<{identifier, label, token, url}>,
//                    fetchExternalCredentials(name) ->
//                       Promise<Array<{identifier, label, created_at}>>,
//                    onRevokeExternalCredential(name, identifier) -> Promise,
//                    onRotateExternalCredential(name, identifier) ->
//                       Promise<{identifier, label, token, url}> }
//
// M21 F02 L03 adds a revision-HISTORY section below the pending queue: the
// full revisions list (newest-first) — each entry shows field, before→after,
// timestamp, source (self/restore/external) and status. Restore is operator-direct
// (applies immediately regardless of approval mode). To make "restore any
// earlier value" literally true with NO duplicate buttons, the history
// renders one Restore control per DISTINCT value-node — the dedup of
// base_value + proposed_value across all `applied` rows — each restoring via
// an appropriate (revision_id, side). This surfaces the original (earliest
// base_value, side=base), each self-revised value (side=proposed) and any
// out-of-band operator-set value (a mid-row base_value) for free. On restore
// the tab refetches the revisions, so the new restore row appears in the
// history with nothing to update in place.
//
// Save-flow note: unlike every other tab, these controls do NOT participate
// in collectFormData()/dirty-tracking — enable/disable and the approval-mode
// toggle are immediate API calls (mirrors the Danger Zone's Delete/Purge
// buttons), not form fields staged for the Save button.
//
// M21 F02 L04 HAT — operator UX review pass. Presentation-only; no
// behavior/endpoint changes. Highlights:
//   - Enable/disable and approval-mode are switches (App.ui.toggle since M31 F2
//     L10c; they were a bespoke checkbox switch before) instead of buttons — the
//     testids stay on the underlying `<input>`.
//   - Restore-node value + Restore button lay out side-by-side, grouped by
//     field ("Description" / "System prompt" subheadings).
//   - The chronological log lives in an `App.ui.disclosure` (plain)
//     below a "Restore to an earlier value" subheading; the restore-node
//     list itself (the actionable part) stays always visible.
//   - Before/after values get a small prefix/suffix diff highlight
//     (`diffSegments` below) instead of two bare full-text blocks — no
//     shared diff util exists app-wide, so this is a small new primitive,
//     intentionally simple (common-prefix/suffix, not a general LCS).
//   - Timestamps render via a copy of the chat message control's (js/ui/message.js) relative-time
//     idiom (there is no shared formatter); the full ISO string stays on
//     `title=`.
//
// M31 F2 L10c — the modules are on the control library (App.ui) with no HTML-string sinks
// and no ownership-allowance rows.
//
// M31 F2 L10b — the file is split (a pure restructure, no behaviour or DOM change).
// This entry keeps the public name and the handle; the sections and their logic live
// in four modules loaded before it, around one per-mount context object built here:
//   self-config-status.js     frame, enable / approval switches, refetches, setAgent
//   self-config-revisions.js  pending queue, cards, approve / dismiss / override, diff
//   self-config-history.js    history list, restore nodes, timestamp formatters
//   self-config-external.js   external credentials and the token reveal
// and (M33 F2 L5) the Routines item: self-config-routines.js (switches, history) and
// self-config-routines-queue.js (the waiting-for-approval list).
// The context holds `panel`, `agent`, `callbacks`, `destroyed`, the two sequence
// counters and `approvalReady`; each module publishes its renderers back on it.

(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Action announcement (a11y — SC 2.4.3 focus / SC 4.1.3 status messages). On a
  // successful action the tab writes a short summary to `actionStatus` and moves
  // focus there BEFORE it refetches (the refetch can remove the focused card, so
  // focus would otherwise drop to <body>); the focus move alone conveys the
  // summary (no live region, to avoid double announcement). A stale-detected or
  // failed action does not move focus. (M31 F2 L10a: this used to be a
  // module-level bridge across the editor's rebuild of the whole panel.)

  function renderSelfConfigurationTab(panel, agent, callbacks) {
    callbacks = callbacks || {};
    panel.textContent = '';

    if (!agent) {
      var notice = App.ui.emptyState({
        title: 'Save the agent first to enable self-configuration.',
        titleTag: 'p',
        variant: 'plain',
        testid: 'self-configuration-save-first'
      });
      panel.appendChild(notice);
      return {
        setAgent: function () {}, destroy: function () {}, deactivate: function () {},
        activate: function () {}
      };
    }

    // Per-mount context (M31 F2 L10b). Liveness (M31 F2 L10a): a refetch's response
    // is applied only while the mount is alive and no newer request of its kind has
    // started.
    var ctx = {
      panel: panel,
      agent: agent,
      callbacks: callbacks,
      destroyed: false,
      statusSeq: 0,
      revisionsSeq: 0,
      approvalReady: false
    };

    // The waiting count of an item's card (M33 F4 L06): the section modules report it here; the
    // `default` agent has no Routines card, so a missing card is ignored.
    ctx.setWaitingCount = function (item, n) {
      var card = ctx.cards && ctx.cards[item];
      if (card) card.setWaitingCount(n);
    };

    var studio = window.App.studio;
    // SC2 (M33 F4 L06): the page eyebrow and the Agent prompt card (status), the card's two
    // bodies (revisions, history), the Routines card as the second item, then External access
    // as the page-level section at the bottom.
    studio.selfConfigStatus.build(ctx);
    studio.selfConfigRevisions.build(ctx);
    studio.selfConfigHistory.build(ctx);
    studio.selfConfigRoutines.build(ctx);
    studio.selfConfigExternal.build(ctx);

    ctx.refetchStatus({});
    ctx.refetchRevisions();
    ctx.refetchRoutines();

    // `deactivate` (M31 F2 L10c): the tab stopped being the shown one (a tab switch, or
    // the Studio area deactivating) — the copy-once token is cleared, nothing else.
    // `activate` (M33 F2 L5): the tab became the shown one again, so the queues are refetched
    // (an agent can propose while the operator is on another tab).
    function activate() {
      ctx.refetchRevisions();
      ctx.refetchRoutines();
    }
    // The tab can become visible again by routes that never call `activate` (the Agents
    // destination re-entered from Chats, the editor re-selected), and the window can come back
    // to the foreground: refetch whenever the page is shown or focused and this panel is
    // actually visible (F-E3-1). Removed on destroy.
    function onShown() {
      if (ctx.destroyed || document.hidden || !panel.offsetParent) return;
      activate();
    }
    document.addEventListener('visibilitychange', onShown);
    window.addEventListener('focus', onShown);
    var destroyMount = ctx.destroy;
    function destroy() {
      document.removeEventListener('visibilitychange', onShown);
      window.removeEventListener('focus', onShown);
      destroyMount();
    }
    return {
      setAgent: ctx.setAgent, destroy: destroy, deactivate: ctx.hideTokenReveal,
      activate: activate
    };
  }

  window.App.studio.renderSelfConfigurationTab = renderSelfConfigurationTab;
})();
