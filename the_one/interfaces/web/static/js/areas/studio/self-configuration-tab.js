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
//
// M21 F02 L04 HAT — operator UX review pass. Presentation-only; no
// behavior/endpoint changes. Highlights:
//   - Enable/disable and approval-mode are now `.tool-enable-switch` iOS
//     switches (admin.css, dual-scoped .area-admin/.area-studio) instead of
//     buttons — the testids stay on the underlying `<input>` so tests keep
//     the same selectors.
//   - Restore-node value + Restore button lay out side-by-side, grouped by
//     field ("Description" / "System prompt" subheadings).
//   - The chronological log lives in a `<details class="advanced-collapsible">`
//     below a "Restore to an earlier value" subheading; the restore-node
//     list itself (the actionable part) stays always visible.
//   - Before/after values get a small prefix/suffix diff highlight
//     (`diffSegments` below) instead of two bare full-text blocks — no
//     shared diff util exists app-wide, so this is a small new primitive,
//     intentionally simple (common-prefix/suffix, not a general LCS).
//   - Timestamps render via a copy of chat/message-bubble.js's relative-time
//     idiom (there is no shared formatter); the full ISO string stays on
//     `title=`.
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

  // ── HAT fix #4 — human-readable timestamps ──────────────────────────
  // Copied from chat/message-bubble.js's relative-time idiom (no shared
  // formatter exists app-wide; see the reuse note in the header comment).
  // `rev.created_at` is an ISO 8601 string (backend `now_iso()`); this
  // renders it as coarse relative time ("3 hours ago") and returns the
  // original ISO string separately so the caller can keep it as a
  // `title=` tooltip for the exact instant.
  function formatTimeAgo(epochSeconds) {
    if (typeof epochSeconds !== 'number' || !isFinite(epochSeconds)) return '';
    var diffSec = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
    if (diffSec < 60) return 'just now';
    var diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return diffMin + ' minute' + (diffMin === 1 ? '' : 's') + ' ago';
    var diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return diffHr + ' hour' + (diffHr === 1 ? '' : 's') + ' ago';
    var diffDay = Math.floor(diffHr / 24);
    return diffDay + ' day' + (diffDay === 1 ? '' : 's') + ' ago';
  }

  function formatRevisionTimestamp(isoStr) {
    if (!isoStr) return { text: '', title: '' };
    var d = new Date(isoStr);
    if (isNaN(d.getTime())) return { text: String(isoStr), title: String(isoStr) };
    return { text: formatTimeAgo(d.getTime() / 1000), title: isoStr };
  }

  // ── HAT fix #6 — before/after diff highlighting ─────────────────────
  // No diff util exists app-wide. This is a deliberately small primitive:
  // a common-prefix/common-suffix split (not a general LCS) that's enough
  // to highlight the changed span(s) in the near-identical values this tab
  // shows ("…SPARROW." -> "…FALCON."). Handles empty strings and identical
  // values (mid segments come back empty, nothing gets wrapped).
  function commonPrefixLen(a, b) {
    var n = Math.min(a.length, b.length);
    var i = 0;
    while (i < n && a.charAt(i) === b.charAt(i)) i++;
    return i;
  }

  function commonSuffixLen(a, b, maxLen) {
    var i = 0;
    while (i < maxLen && a.charAt(a.length - 1 - i) === b.charAt(b.length - 1 - i)) i++;
    return i;
  }

  function diffSegments(oldStr, newStr) {
    oldStr = oldStr == null ? '' : String(oldStr);
    newStr = newStr == null ? '' : String(newStr);
    if (oldStr === newStr) {
      return { prefix: oldStr, oldMid: '', newMid: '', suffix: '' };
    }
    var prefixLen = commonPrefixLen(oldStr, newStr);
    var maxSuffix = Math.min(oldStr.length - prefixLen, newStr.length - prefixLen);
    var suffixLen = commonSuffixLen(oldStr, newStr, maxSuffix);
    var prefix = oldStr.slice(0, prefixLen);
    var suffix = suffixLen > 0 ? oldStr.slice(oldStr.length - suffixLen) : '';
    var oldMid = oldStr.slice(prefixLen, oldStr.length - suffixLen);
    var newMid = newStr.slice(prefixLen, newStr.length - suffixLen);
    return { prefix: prefix, oldMid: oldMid, newMid: newMid, suffix: suffix };
  }

  // Renders `prefix + <span class="midClass">mid</span> + suffix` into an
  // existing element (a `<pre>`), skipping empty pieces. `prefix`/`suffix`
  // are shared verbatim text (never highlighted); `mid` is the changed run.
  function applyDiffSpans(el, prefix, mid, suffix, midClass) {
    el.textContent = '';
    if (prefix) el.appendChild(document.createTextNode(prefix));
    if (mid) {
      var span = document.createElement('span');
      span.className = midClass;
      span.textContent = mid;
      el.appendChild(span);
    }
    if (suffix) el.appendChild(document.createTextNode(suffix));
  }

  // Renders a before/after pair of `<pre>` elements with only the changed
  // span highlighted (`.diff-del` on `beforeEl`, `.diff-add` on `afterEl`);
  // the unchanged prefix/suffix render as plain text on both, so the full
  // value stays readable for context.
  function renderDiffedValues(beforeEl, afterEl, oldStr, newStr) {
    var seg = diffSegments(oldStr, newStr);
    applyDiffSpans(beforeEl, seg.prefix, seg.oldMid, seg.suffix, 'diff-del');
    applyDiffSpans(afterEl, seg.prefix, seg.newMid, seg.suffix, 'diff-add');
  }

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

    // HAT: enable/disable is a 2-state immediate-post control — the
    // reusable `.tool-enable-switch` iOS switch (admin.css, already
    // dual-scoped .area-admin/.area-studio) fits better than a button.
    // The testid stays on the actual `<input>` so existing test selectors
    // keep resolving to the interactive control.
    var toggleLabel = document.createElement('label');
    toggleLabel.className = 'tool-enable-switch self-configuration-toggle-switch';
    var toggleInput = document.createElement('input');
    toggleInput.type = 'checkbox';
    toggleInput.setAttribute('data-testid', 'self-configuration-toggle-btn');
    toggleInput.setAttribute('aria-label', 'Enable self-configuration');
    toggleInput.disabled = true;
    toggleLabel.appendChild(toggleInput);
    var toggleTrack = document.createElement('span');
    toggleTrack.className = 'tool-enable-switch-track';
    toggleTrack.setAttribute('aria-hidden', 'true');
    toggleLabel.appendChild(toggleTrack);
    section.appendChild(toggleLabel);

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

    // HAT: same switch treatment as the enable/disable control above —
    // 2-state, immediate-post.
    var approvalLabel = document.createElement('label');
    approvalLabel.className = 'tool-enable-switch self-configuration-toggle-switch';
    var approvalInput = document.createElement('input');
    approvalInput.type = 'checkbox';
    approvalInput.setAttribute('data-testid', 'approval-mode-toggle-btn');
    approvalInput.setAttribute('aria-label', 'Require approval for self-revisions');
    approvalInput.disabled = true;
    approvalLabel.appendChild(approvalInput);
    var approvalTrack = document.createElement('span');
    approvalTrack.className = 'tool-enable-switch-track';
    approvalTrack.setAttribute('aria-hidden', 'true');
    approvalLabel.appendChild(approvalTrack);
    approvalSection.appendChild(approvalLabel);

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
    historyDesc.textContent = 'Every change to this agent’s description and system prompt. ' +
      'Restore returns a field to any earlier value it held — it applies immediately (your ' +
      'restore is never held for approval) and is recorded as a new entry.';
    historySection.appendChild(historyDesc);

    // HAT fix #3: the restore-node list (below) and the chronological log
    // (further below, in the collapsible) used to sit under one heading
    // with no visible separation. Two distinct subheadings now — this one
    // for the actionable restore list…
    var restoreHeading = document.createElement('div');
    restoreHeading.className = 'self-configuration-subheading';
    restoreHeading.textContent = 'Restore to an earlier value';
    historySection.appendChild(restoreHeading);

    // Restore controls: one per distinct value the fields have held,
    // grouped by field (HAT fix #8) — see renderHistory below.
    var restoreControls = document.createElement('div');
    restoreControls.className = 'self-configuration-restore-controls';
    restoreControls.setAttribute('data-testid', 'revision-restore-controls');
    restoreControls.setAttribute('role', 'group');
    restoreControls.setAttribute('aria-label', 'Restore an earlier value');
    historySection.appendChild(restoreControls);

    // …and the collapsible "History (N)" `<summary>` below for the
    // chronological log (HAT fix #10 — native `<details>`, zero-JS
    // disclosure, components.css `.advanced-collapsible`). The restore
    // list above stays always visible; only the full log collapses.
    var historyDetails = document.createElement('details');
    historyDetails.className = 'advanced-collapsible self-configuration-history-details';
    historyDetails.setAttribute('data-testid', 'revision-history-details');

    var historySummary = document.createElement('summary');
    historySummary.setAttribute('data-testid', 'revision-history-summary');
    historySummary.textContent = 'History';
    historyDetails.appendChild(historySummary);

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
    historyDetails.appendChild(historyList);

    historySection.appendChild(historyDetails);

    panel.appendChild(historySection);

    // ── M21 F03 L03 — External access ───────────────────────────────────
    // Grant / list / revoke / rotate external-client credentials over
    // Leg 1's endpoints. Unlike every other action on this tab, these do
    // NOT route through `_refreshAgentAfterSelfConfigurationChange`: mint
    // and rotate return the full `ext_<id>.<secret>` token exactly once,
    // and a whole-editor re-render would tear the copy-once reveal down
    // before the operator copies it. So each action re-fetches ONLY the
    // list locally (`refreshExternalList`) and the reveal persists until an
    // explicit dismiss or the next full tab render (which clears the token
    // by rebuilding the panel — the token is never persisted anywhere,
    // never `localStorage`/`sessionStorage`). Because there is no full
    // re-render, the `pendingAction`/`actionStatus` focus-bridge above does
    // not apply here; this section announces through its own
    // `role="status" aria-live="polite"` line — the same live-region idiom
    // the tab's status/count lines already use — and moves focus itself.
    var externalSection = document.createElement('div');
    externalSection.className = 'editor-section self-configuration-external-section';

    var externalTitle = document.createElement('div');
    externalTitle.className = 'section-title';
    externalTitle.textContent = 'External access';
    externalSection.appendChild(externalTitle);

    var externalDesc = document.createElement('p');
    externalDesc.className = 'self-configuration-description';
    externalDesc.textContent = 'Grant an external client — a tool outside the platform, or ' +
      'another agent inside it — a credential scoped to just this agent’s self-configuration ' +
      'surface. Each grant’s token is shown once, at creation. Revoke or rotate a grant at any ' +
      'time; the change takes effect immediately, without a restart.';
    externalSection.appendChild(externalDesc);

    // Announcement + status live region for grant/revoke/rotate (see the
    // rationale in the section comment above).
    var externalStatus = document.createElement('p');
    externalStatus.className = 'self-configuration-status self-configuration-external-status';
    externalStatus.setAttribute('data-testid', 'self-configuration-external-status');
    externalStatus.setAttribute('role', 'status');
    externalStatus.setAttribute('aria-live', 'polite');
    externalStatus.textContent = 'Loading…';
    externalSection.appendChild(externalStatus);

    // Section-level error (survives a list re-fetch — a per-row error would
    // vanish when the list rebuilds after a failed revoke/rotate).
    var externalError = document.createElement('p');
    externalError.className = 'self-configuration-error';
    externalError.setAttribute('data-testid', 'self-configuration-external-error');
    externalError.setAttribute('role', 'alert');
    externalError.hidden = true;
    externalSection.appendChild(externalError);

    // ── grant control ──
    var grantRow = document.createElement('div');
    grantRow.className = 'self-configuration-external-grant';

    var grantLabelEl = document.createElement('label');
    grantLabelEl.className = 'self-configuration-external-grant-label-text';
    grantLabelEl.setAttribute('for', 'self-configuration-external-grant-label-input');
    grantLabelEl.textContent = 'Label';
    grantRow.appendChild(grantLabelEl);

    var grantInput = document.createElement('input');
    grantInput.type = 'text';
    grantInput.className = 'field-input';
    grantInput.id = 'self-configuration-external-grant-label-input';
    grantInput.setAttribute('data-testid', 'self-configuration-external-grant-label');
    grantInput.setAttribute('placeholder', 'e.g. staging-deploy-bot');
    grantInput.setAttribute('maxlength', '200');
    // Inert until the surface status resolves (parity with the enable
    // toggle above); `renderExternalState` sets the real state.
    grantInput.disabled = true;
    grantRow.appendChild(grantInput);

    var grantBtn = document.createElement('button');
    grantBtn.type = 'button';
    grantBtn.className = 'btn-filled-primary self-configuration-external-grant-btn';
    grantBtn.setAttribute('data-testid', 'self-configuration-external-grant-btn');
    grantBtn.textContent = 'Grant access';
    grantBtn.disabled = true;
    grantRow.appendChild(grantBtn);

    externalSection.appendChild(grantRow);

    // Disabled-surface hint (AC1) — shown when self-configuration is off.
    var grantHint = document.createElement('p');
    grantHint.className = 'self-configuration-description self-configuration-external-grant-hint';
    grantHint.setAttribute('data-testid', 'self-configuration-external-grant-hint');
    grantHint.textContent = 'Enable self-configuration above to grant external access.';
    grantHint.hidden = true;
    externalSection.appendChild(grantHint);

    // ── copy-once secret reveal (hidden until a mint/rotate returns) ──
    var tokenReveal = document.createElement('div');
    tokenReveal.className = 'self-configuration-external-token-reveal banner banner-warning';
    tokenReveal.setAttribute('data-testid', 'self-configuration-external-token-reveal');
    tokenReveal.setAttribute('role', 'status');
    tokenReveal.setAttribute('aria-live', 'polite');
    tokenReveal.tabIndex = -1;
    tokenReveal.hidden = true;

    var tokenWarning = document.createElement('p');
    tokenWarning.className = 'self-configuration-external-token-warning';
    // Programmatic association target (WCAG 1.3.1): the copy button and token
    // input point their aria-describedby at this id so the full shown-once
    // caution is read when focus lands on either control.
    tokenWarning.id = 'self-configuration-external-token-warning';
    tokenWarning.textContent = 'Copy this token now — it is shown only once and cannot be ' +
      'retrieved again. If you lose it, revoke this grant and create a new one.';
    tokenReveal.appendChild(tokenWarning);

    var tokenValueRow = document.createElement('div');
    tokenValueRow.className = 'self-configuration-external-token-row';

    var tokenValue = document.createElement('input');
    tokenValue.type = 'text';
    tokenValue.readOnly = true;
    tokenValue.className = 'field-input self-configuration-external-token-value';
    tokenValue.setAttribute('data-testid', 'self-configuration-external-token-value');
    tokenValue.setAttribute('aria-label', 'External access token (shown once)');
    tokenValue.setAttribute('aria-describedby', 'self-configuration-external-token-warning');
    tokenValueRow.appendChild(tokenValue);

    var tokenCopyBtn = document.createElement('button');
    tokenCopyBtn.type = 'button';
    tokenCopyBtn.className = 'btn-outlined-primary self-configuration-external-token-copy-btn';
    tokenCopyBtn.setAttribute('data-testid', 'self-configuration-external-token-copy-btn');
    tokenCopyBtn.setAttribute('aria-describedby', 'self-configuration-external-token-warning');
    tokenCopyBtn.textContent = 'Copy';
    tokenValueRow.appendChild(tokenCopyBtn);

    tokenReveal.appendChild(tokenValueRow);

    var tokenUrl = document.createElement('p');
    tokenUrl.className = 'self-configuration-external-token-url';
    var tokenUrlLabel = document.createElement('span');
    tokenUrlLabel.className = 'self-configuration-external-token-url-label';
    tokenUrlLabel.textContent = 'Surface URL: ';
    var tokenUrlValue = document.createElement('span');
    tokenUrlValue.setAttribute('data-testid', 'self-configuration-external-token-url');
    tokenUrl.appendChild(tokenUrlLabel);
    tokenUrl.appendChild(tokenUrlValue);
    tokenReveal.appendChild(tokenUrl);

    var tokenDismissBtn = document.createElement('button');
    tokenDismissBtn.type = 'button';
    tokenDismissBtn.className = 'btn-ghost btn-sm self-configuration-external-token-dismiss-btn';
    tokenDismissBtn.setAttribute('data-testid', 'self-configuration-external-token-dismiss-btn');
    tokenDismissBtn.textContent = 'Dismiss';
    tokenReveal.appendChild(tokenDismissBtn);

    externalSection.appendChild(tokenReveal);

    // ── active-grants list ──
    var externalList = document.createElement('div');
    externalList.className = 'self-configuration-external-list';
    externalList.setAttribute('data-testid', 'self-configuration-external-list');
    externalList.setAttribute('role', 'group');
    externalList.setAttribute('aria-label', 'Active external-access grants');
    externalSection.appendChild(externalList);

    panel.appendChild(externalSection);

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
      toggleInput.checked = enabled;
      toggleInput.disabled = false;
      errorLine.hidden = true;
      errorLine.textContent = '';
      // `change` fires after the browser has already flipped `.checked` to
      // the new (opposite of `enabled`) state — that IS the "flip on
      // change" immediate-post behavior the switch preserves from the old
      // button's onclick. On failure, revert to the pre-click state.
      toggleInput.onchange = function () {
        var action = enabled ? callbacks.onDisable : callbacks.onEnable;
        if (!action) { toggleInput.checked = enabled; return; }
        pendingAction = {
          agentName: agent.name,
          message: enabled ? 'Disabled self-configuration.' : 'Enabled self-configuration.'
        };
        toggleInput.disabled = true;
        action(agent.name).then(function (result) {
          renderState(!!(result && result.enabled));
        }).catch(function (err) {
          pendingAction = null;
          errorLine.hidden = false;
          errorLine.textContent = 'Failed to ' + (enabled ? 'disable' : 'enable') +
            ' self-configuration: ' + (err && err.message ? err.message : String(err));
          toggleInput.checked = enabled;
          toggleInput.disabled = false;
        });
      };
    }

    // ── approval-mode toggle (immediate-post, like enable) ──────────────
    function renderApprovalState(requiresApproval) {
      approvalStatus.textContent = requiresApproval
        ? 'Approval mode is on — this agent’s self-revisions require your approval.'
        : 'Approval mode is off — this agent’s self-revisions take effect without approval.';
      approvalInput.checked = requiresApproval;
      approvalInput.disabled = false;
      approvalError.hidden = true;
      approvalError.textContent = '';
      approvalInput.onchange = function () {
        if (!callbacks.onSetApprovalMode) { approvalInput.checked = requiresApproval; return; }
        pendingAction = {
          agentName: agent.name,
          message: requiresApproval ? 'Turned off approval mode.' : 'Turned on approval mode.'
        };
        approvalInput.disabled = true;
        // On success studio.js re-renders the whole tab (the flag lives
        // outside the Save flow), so the fresh render reflects the new
        // value — no local state update needed here.
        callbacks.onSetApprovalMode(agent.name, !requiresApproval).catch(function (err) {
          pendingAction = null;
          approvalError.hidden = false;
          approvalError.textContent = 'Failed to change approval mode: ' +
            (err && err.message ? err.message : String(err));
          approvalInput.checked = requiresApproval;
          approvalInput.disabled = false;
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
      // the one-click path, not only the 409 path). HAT fix #6: only the
      // changed span is highlighted (diff-del/diff-add) instead of two
      // bare full-text blocks. HAT "match design language": `.code-block`
      // is the app's read-only value-artifact primitive.
      var baseBlock = document.createElement('div');
      baseBlock.className = 'revision-base';
      var baseHdr = document.createElement('div');
      baseHdr.className = 'revision-value-label';
      baseHdr.textContent = 'Current';
      var baseVal = document.createElement('pre');
      baseVal.className = 'revision-value code-block';
      baseVal.setAttribute('data-testid', 'revision-base');
      baseBlock.appendChild(baseHdr);
      baseBlock.appendChild(baseVal);
      card.appendChild(baseBlock);

      var proposedBlock = document.createElement('div');
      proposedBlock.className = 'revision-proposed';
      var proposedHdr = document.createElement('div');
      proposedHdr.className = 'revision-value-label';
      proposedHdr.textContent = 'Proposed';
      var proposedVal = document.createElement('pre');
      proposedVal.className = 'revision-value code-block';
      proposedVal.setAttribute('data-testid', 'revision-proposed');
      proposedBlock.appendChild(proposedHdr);
      proposedBlock.appendChild(proposedVal);
      card.appendChild(proposedBlock);

      renderDiffedValues(baseVal, proposedVal, revision.base_value, revision.proposed_value);

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

        // HAT "match design language": the drift advisory reuses
        // `.banner-warning` (components.css) instead of an unstyled <p>.
        var warn = document.createElement('p');
        warn.className = 'revision-stale-warning banner banner-warning';
        warn.setAttribute('role', 'alert');
        warn.textContent = 'This value has changed since the agent proposed its revision. ' +
          'Approving will overwrite the current value below.';
        stalePanel.appendChild(warn);

        var curHdr = document.createElement('div');
        curHdr.className = 'revision-value-label';
        curHdr.textContent = 'Current value now';
        var curVal = document.createElement('pre');
        curVal.className = 'revision-value code-block';
        curVal.setAttribute('data-testid', 'revision-current');
        curVal.textContent = detail.current_value;
        stalePanel.appendChild(curHdr);
        stalePanel.appendChild(curVal);

        var propHdr = document.createElement('div');
        propHdr.className = 'revision-value-label';
        propHdr.textContent = 'Proposed value';
        var propVal = document.createElement('pre');
        propVal.className = 'revision-value code-block';
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
      // HAT fix #5: at zero, show only ONE empty-state message (the
      // dedicated `pending-queue-empty` notice below) — the count line
      // used to ALSO say "0 revisions awaiting your approval.", which
      // read as two conflicting/redundant messages stacked on top of
      // each other.
      if (pending.length === 0) {
        countLine.hidden = true;
        countLine.textContent = '';
        var empty = document.createElement('p');
        empty.className = 'empty-state';
        empty.setAttribute('data-testid', 'pending-queue-empty');
        empty.textContent = 'No revisions are awaiting approval.';
        queueList.appendChild(empty);
        return;
      }
      countLine.hidden = false;
      countLine.textContent = pending.length === 1
        ? '1 revision awaiting your approval.'
        : pending.length + ' revisions awaiting your approval.';
      pending.forEach(function (rev) {
        queueList.appendChild(renderCard(rev));
      });
    }

    // ── M21 F02 L03 — revision history + restore rendering ──────────────
    function fieldName(field) {
      return field === 'system_prompt' ? 'System prompt' : 'Description';
    }

    // Maps a revision's `status` (applied/pending/dismissed/superseded —
    // see db/models.py AgentRevision) to an `.indicator-led--*` variant.
    function statusLedVariant(status) {
      if (status === 'applied') return 'success';
      if (status === 'pending') return 'warning';
      return 'idle'; // dismissed, superseded
    }

    // Builds one restore-node row: value + Restore button laid out
    // side-by-side (HAT fix #9 — `.self-configuration-restore-node` flex
    // row in studio.css; short values sit inline with the button pinned
    // right, long/multi-line values wrap). Extracted to a function since
    // nodes now render grouped by field (HAT fix #8) instead of one flat
    // list.
    function renderRestoreNodeRow(node) {
      var row = document.createElement('div');
      row.className = 'self-configuration-restore-node';
      row.setAttribute('data-testid', 'revision-restore-node');
      row.setAttribute('data-field', node.field);
      row.setAttribute('data-side', node.side);

      var preview = document.createElement('pre');
      preview.className = 'revision-value code-block restore-node-value';
      preview.textContent = node.value;
      row.appendChild(preview);

      // A short snippet of this node's own value distinguishes it from
      // every other Restore button for a screen-reader rotor (SC 2.4.6)
      // — plain "Restore this description value" repeats verbatim across
      // nodes. Nodes are already deduped per-field (see below), so the
      // snippet is unique among a field's own nodes.
      var nodeSnippet = node.value ? node.value : '(empty)';
      if (nodeSnippet.length > 40) nodeSnippet = nodeSnippet.slice(0, 40) + '…';

      var restoreBtn = document.createElement('button');
      restoreBtn.type = 'button';
      restoreBtn.className = 'btn-outlined-primary btn-sm revision-restore-btn';
      restoreBtn.setAttribute('data-testid', 'revision-restore-btn');
      restoreBtn.setAttribute('data-revision-id', node.revisionId);
      restoreBtn.setAttribute('data-side', node.side);
      // Labelled for assistive tech — names the field it restores and a
      // snippet of the value, so it reads distinctly from sibling nodes.
      restoreBtn.setAttribute('aria-label',
        'Restore this ' + fieldName(node.field).toLowerCase() + ' value: “' + nodeSnippet + '”');
      restoreBtn.textContent = 'Restore';
      row.appendChild(restoreBtn);

      var nodeError = document.createElement('p');
      nodeError.className = 'self-configuration-error';
      nodeError.setAttribute('data-testid', 'revision-restore-error');
      nodeError.setAttribute('role', 'alert');
      nodeError.hidden = true;
      row.appendChild(nodeError);

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

      return row;
    }

    // The two fields this tab manages (DD1 — see the header comment).
    // Explicit order (not alphabetical-by-accident) drives the grouped
    // restore list below.
    var RESTORE_FIELD_ORDER = ['description', 'system_prompt'];

    function renderHistory(revisions) {
      revisions = revisions || [];

      // ── the full chronological log (newest-first, all statuses) ──
      historyList.innerHTML = '';
      historySummary.textContent = 'History (' + revisions.length + ')';
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
          // HAT fix #1: the field-name span and the source/status/time
          // span used to sit adjacent with no separator ("System
          // prompt**self-revised**"). An explicit em-dash text node reads
          // correctly even if the flex `gap` below is unavailable (e.g.
          // copy/paste, a screen reader's linearized text).
          head.appendChild(document.createTextNode(' — '));

          var meta = document.createElement('span');
          meta.className = 'history-entry-meta';
          // HAT "match design language": a status LED, paired with the
          // status word already in the visible text (so it's decorative
          // — aria-hidden — per the indicator-led a11y contract in
          // components.css).
          var led = document.createElement('span');
          led.className = 'indicator-led indicator-led--' + statusLedVariant(rev.status);
          led.setAttribute('aria-hidden', 'true');
          meta.appendChild(led);

          var metaText = document.createElement('span');
          metaText.className = 'history-entry-meta-text';
          // source + status + timestamp, human-readable and attributable.
          // HAT fix #4: formatted relative time instead of the raw ISO
          // string; the exact instant stays available via `title=`.
          var sourceLabel = rev.source === 'restore' ? 'restored' : 'self-revised';
          var ts = formatRevisionTimestamp(rev.created_at);
          metaText.textContent = sourceLabel + ' · ' + rev.status +
            (ts.text ? ' · ' + ts.text : '');
          if (ts.title) metaText.title = ts.title;
          meta.appendChild(metaText);
          head.appendChild(meta);
          entry.appendChild(head);

          // HAT fix #6: only the changed span is highlighted instead of
          // two bare full-text blocks.
          var change = document.createElement('div');
          change.className = 'history-entry-change';
          var beforeVal = document.createElement('pre');
          beforeVal.className = 'revision-value code-block history-entry-before';
          var arrow = document.createElement('span');
          arrow.className = 'history-entry-arrow';
          arrow.setAttribute('aria-label', 'changed to');
          arrow.textContent = '→';
          var afterVal = document.createElement('pre');
          afterVal.className = 'revision-value code-block history-entry-after';
          change.appendChild(beforeVal);
          change.appendChild(arrow);
          change.appendChild(afterVal);
          entry.appendChild(change);
          renderDiffedValues(beforeVal, afterVal, rev.base_value, rev.proposed_value);

          historyList.appendChild(entry);
        });
      }

      // ── restore controls: one per DISTINCT value-node, grouped by field ──
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

      // HAT fix #8: grouped by field ("Description" subgroup, then
      // "System prompt") instead of interleaved chronologically — this
      // also folds in HAT fix #2 (restore rows previously had no visible
      // field label; the subheading now labels the whole group). A field
      // with zero nodes contributes no subgroup (nothing to restore for
      // it yet).
      RESTORE_FIELD_ORDER.forEach(function (field) {
        var fieldNodes = nodes.filter(function (n) { return n.field === field; });
        if (fieldNodes.length === 0) return;

        var groupHeading = document.createElement('div');
        groupHeading.className = 'self-configuration-restore-group-label';
        groupHeading.textContent = fieldName(field);
        restoreControls.appendChild(groupHeading);

        var group = document.createElement('div');
        group.className = 'self-configuration-restore-group';
        fieldNodes.forEach(function (node) {
          group.appendChild(renderRestoreNodeRow(node));
        });
        restoreControls.appendChild(group);
      });
    }

    // ── M21 F03 L03 — External access behavior ──────────────────────────
    function externalErrMsg(err) {
      return err && err.message ? err.message : String(err);
    }

    function clearExternalError() {
      externalError.hidden = true;
      externalError.textContent = '';
    }

    function showExternalError(message) {
      externalError.hidden = false;
      externalError.textContent = message;
    }

    // The copy-once reveal. The token lives ONLY here (the readonly input's
    // value + this DOM); it is never written to localStorage/sessionStorage
    // and is cleared by `hideTokenReveal` or by the next full tab render
    // (the next full tab render rebuilds this section from scratch).
    function hideTokenReveal() {
      tokenReveal.hidden = true;
      tokenValue.value = '';
      tokenUrlValue.textContent = '';
    }

    function showTokenReveal(result) {
      // `result` is the mint/rotate response: {identifier, label, token, url}.
      tokenValue.value = result && result.token ? result.token : '';
      tokenUrlValue.textContent = result && result.url ? result.url : '';
      tokenReveal.hidden = false;
      // Focus lands on the reveal's primary action (Copy) — inside the
      // reveal, keyboard-operable, never the page top (AC7). The reveal is
      // an `aria-live` region, so its warning is announced as it appears.
      tokenCopyBtn.focus();
    }

    tokenCopyBtn.onclick = function () {
      var text = tokenValue.value;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () {
          externalStatus.textContent = 'Token copied to the clipboard.';
        }, function () { fallbackCopy(); });
      } else {
        fallbackCopy();
      }
      function fallbackCopy() {
        tokenValue.select();
        try { document.execCommand('copy'); } catch (e) { /* selection remains */ }
        externalStatus.textContent = 'Token copied to the clipboard.';
      }
    };

    tokenDismissBtn.onclick = function () {
      hideTokenReveal();
      externalStatus.textContent = 'Dismissed the token. It cannot be shown again.';
      grantInput.focus();
    };

    function renderCredentialRow(cred) {
      var row = document.createElement('div');
      row.className = 'self-configuration-external-credential-row';
      row.setAttribute('data-testid', 'self-configuration-external-credential-row');
      row.setAttribute('data-identifier', cred.identifier);

      var info = document.createElement('div');
      info.className = 'self-configuration-external-credential-info';

      // Label rendered as text content (never HTML) — AC / edge case.
      var labelEl = document.createElement('div');
      labelEl.className = 'self-configuration-external-credential-label';
      labelEl.textContent = cred.label ? cred.label : '(no label)';
      info.appendChild(labelEl);

      var meta = document.createElement('div');
      meta.className = 'self-configuration-external-credential-meta';
      var idEl = document.createElement('span');
      idEl.className = 'self-configuration-external-credential-id';
      // The public identifier (secret-free) — NOT the one-time token.
      idEl.textContent = 'ext_' + cred.identifier;
      meta.appendChild(idEl);
      var ts = formatRevisionTimestamp(cred.created_at);
      if (ts.text) {
        var sep = document.createElement('span');
        sep.textContent = ' · created ';
        meta.appendChild(sep);
        var timeEl = document.createElement('span');
        timeEl.className = 'self-configuration-external-credential-created';
        timeEl.textContent = ts.text;
        if (ts.title) timeEl.title = ts.title;
        meta.appendChild(timeEl);
      }
      info.appendChild(meta);
      row.appendChild(info);

      var actions = document.createElement('div');
      actions.className = 'self-configuration-external-credential-actions';

      var labelSnippet = cred.label ? cred.label : cred.identifier;
      if (labelSnippet.length > 40) labelSnippet = labelSnippet.slice(0, 40) + '…';

      var rotateBtn = document.createElement('button');
      rotateBtn.type = 'button';
      rotateBtn.className = 'btn-outlined-primary btn-sm self-configuration-external-rotate-btn';
      rotateBtn.setAttribute('data-testid', 'self-configuration-external-rotate-btn');
      rotateBtn.setAttribute('aria-label', 'Rotate external access “' + labelSnippet + '”');
      rotateBtn.textContent = 'Rotate';
      rotateBtn.onclick = function () {
        if (!callbacks.onRotateExternalCredential) return;
        clearExternalError();
        rotateBtn.disabled = true;
        callbacks.onRotateExternalCredential(agent.name, cred.identifier).then(function (result) {
          externalStatus.textContent = 'Rotated external access “' +
            (result && result.label ? result.label : labelSnippet) +
            '”. Copy the new token now — it is shown only once.';
          showTokenReveal(result);
          return refreshExternalList();
        }).catch(function (err) {
          showExternalError('Failed to rotate external access: ' + externalErrMsg(err));
          // Move focus to a stable target BEFORE the list rebuild destroys
          // this button, so focus never drops to <body> (AC7 — never the
          // page top). grantInput is outside the list container and survives
          // the refresh, mirroring the revoke-success and grant-error paths.
          grantInput.focus();
          // The row may be stale (revoked out-of-band → 404). Re-fetch so
          // the list reflects reality; the error stays on the section.
          refreshExternalList();
        });
      };
      actions.appendChild(rotateBtn);

      // Revoke uses the canonical two-step in-place confirm (confirm.js):
      // first click arms ("Confirm revoke?"), second click within the
      // window commits. Keyboard-operable (it is a <button>).
      var revokeBtn = document.createElement('button');
      revokeBtn.type = 'button';
      revokeBtn.className = 'btn-muted-destructive btn-sm delete-btn self-configuration-external-revoke-btn';
      revokeBtn.setAttribute('data-testid', 'self-configuration-external-revoke-btn');
      revokeBtn.setAttribute('aria-label', 'Revoke external access “' + labelSnippet + '”');
      var revokeLabel = document.createElement('span');
      revokeLabel.setAttribute('data-confirm-title', '');
      revokeLabel.textContent = 'Revoke';
      revokeBtn.appendChild(revokeLabel);
      revokeBtn.onclick = function () {
        if (!callbacks.onRevokeExternalCredential) return;
        var commit = function () {
          clearExternalError();
          revokeBtn.disabled = true;
          callbacks.onRevokeExternalCredential(agent.name, cred.identifier).then(function () {
            externalStatus.textContent = 'Revoked external access “' +
              (cred.label ? cred.label : labelSnippet) + '”.';
            // Focus a stable target BEFORE the list rebuilds (AC7 — never
            // the page top). The grant input is outside the list container.
            grantInput.focus();
            return refreshExternalList();
          }).catch(function (err) {
            showExternalError('Failed to revoke external access: ' + externalErrMsg(err));
            // Move focus to a stable target BEFORE the list rebuild destroys
            // this button, so focus never drops to <body> (AC7 — never the
            // page top). grantInput survives the refresh (it is outside the
            // list container), mirroring the revoke-success path above.
            grantInput.focus();
            refreshExternalList();
          });
        };
        if (window.App && window.App.confirmDelete) {
          // The persistent aria-label ("Revoke external access …") overrides
          // the button's visible text as its accessible name, so confirmDelete
          // swapping the visible [data-confirm-title] text to "Confirm revoke?"
          // is invisible to screen-reader users. Detect the arm (the first
          // click, before the class is added) and announce the armed state via
          // externalStatus (role=status), which the section already uses for
          // every other action, so the armed state IS conveyed (WCAG 4.1.2).
          var arming = !revokeBtn.classList.contains('confirm-delete');
          window.App.confirmDelete(revokeBtn, commit, {
            titleSelector: '[data-confirm-title]',
            confirmLabel: 'Confirm revoke?'
          });
          if (arming && revokeBtn.classList.contains('confirm-delete')) {
            externalStatus.textContent = 'Confirm revoke of external access “' +
              labelSnippet + '”? Activate Revoke again to confirm.';
          }
        } else {
          commit();
        }
      };
      actions.appendChild(revokeBtn);

      row.appendChild(actions);
      return row;
    }

    function renderExternalList(credentials) {
      externalList.innerHTML = '';
      credentials = credentials || [];
      if (credentials.length === 0) {
        var empty = document.createElement('p');
        empty.className = 'empty-state';
        empty.setAttribute('data-testid', 'self-configuration-external-empty');
        empty.textContent = 'No external-access grants.';
        externalList.appendChild(empty);
        return;
      }
      credentials.forEach(function (cred) {
        externalList.appendChild(renderCredentialRow(cred));
      });
    }

    // Local list re-fetch (never the whole-editor re-render — see the
    // section comment). Returns a promise so callers can chain.
    function refreshExternalList() {
      if (!callbacks.fetchExternalCredentials) {
        renderExternalList([]);
        return Promise.resolve();
      }
      return callbacks.fetchExternalCredentials(agent.name).then(function (credentials) {
        renderExternalList(credentials);
      }).catch(function () {
        externalList.textContent = 'Unable to load external-access grants.';
      });
    }

    grantBtn.onclick = function () {
      if (!callbacks.onMintExternalCredential) return;
      var label = grantInput.value.trim();
      if (!label) {
        // Inline rejection — no server round-trip (AC6).
        showExternalError('Enter a label for this external client before granting access.');
        grantInput.focus();
        return;
      }
      clearExternalError();
      grantBtn.disabled = true;
      callbacks.onMintExternalCredential(agent.name, label).then(function (result) {
        grantInput.value = '';
        grantBtn.disabled = false;
        externalStatus.textContent = 'Granted external access “' +
          (result && result.label ? result.label : label) +
          '”. Copy the token now — it is shown only once.';
        showTokenReveal(result);
        return refreshExternalList();
      }).catch(function (err) {
        grantBtn.disabled = false;
        showExternalError('Failed to grant external access: ' + externalErrMsg(err));
      });
    };

    // AC1 — enablement gate. When the surface is enabled the grant control
    // is actionable and the active-grants list is shown; when disabled the
    // grant control is disabled with a hint and the list is empty (the
    // server cascades credentials away on disable, and mint 409s otherwise).
    function renderExternalState(enabled) {
      clearExternalError();
      if (enabled) {
        externalStatus.textContent = 'Grant external clients access to this agent’s surface.';
        grantInput.disabled = false;
        grantBtn.disabled = false;
        grantHint.hidden = true;
        refreshExternalList();
      } else {
        externalStatus.textContent = 'External access is unavailable while self-configuration ' +
          'is disabled.';
        grantInput.disabled = true;
        grantBtn.disabled = true;
        grantHint.hidden = false;
        hideTokenReveal();
        renderExternalList([]);
      }
    }

    // ── initial load ────────────────────────────────────────────────────
    if (!callbacks.fetchStatus) {
      renderState(false);
      renderApprovalState(false);
      renderExternalState(false);
    } else {
      callbacks.fetchStatus(agent.name).then(function (status) {
        renderState(!!(status && status.enabled));
        renderApprovalState(!!(status && status.requires_approval));
        renderExternalState(!!(status && status.enabled));
      }).catch(function () {
        statusLine.textContent = 'Unable to load self-configuration status.';
        approvalStatus.textContent = 'Unable to load approval-mode status.';
        externalStatus.textContent = 'Unable to load external-access status.';
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
