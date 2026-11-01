// App.studio.selfConfigRevisions — the Self-configuration tab's pending-revision
// queue: the cards, approve, dismiss, the stale panel and the override, plus the
// pure diff helpers (M31 F2 L10b: split out of self-configuration-tab.js, a pure
// restructure). `build(ctx)` fills the Agent prompt card's "Waiting for approval" body
// (M33 F4 L06) and publishes `ctx.queueList` and `ctx.renderQueue`; it reads `ctx.agent` and
// the cross-module `ctx.announce` / `ctx.refetchRevisions` / `ctx.fieldName` at call
// time.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

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

  function build(ctx) {
    var callbacks = ctx.callbacks;

    // ── M21 F02 L02 — pending revision queue ────────────────────────────
    // The queue is the body of the Agent prompt card's "Waiting for approval" expander (M33 F4
    // L06); its count chip and zero label are the card's.
    var queueCard = ctx.cards.prompt.queue;

    var queueList = document.createElement('div');
    queueList.className = 'self-configuration-pending-queue';
    queueList.setAttribute('data-testid', 'pending-queue');
    queueCard.body.appendChild(queueList);

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
      var baseVal = App.ui.codeBlock({ className: 'revision-value', testid: 'revision-base' }).el;
      baseBlock.appendChild(baseHdr);
      baseBlock.appendChild(baseVal);
      card.appendChild(baseBlock);

      var proposedBlock = document.createElement('div');
      proposedBlock.className = 'revision-proposed';
      var proposedHdr = document.createElement('div');
      proposedHdr.className = 'revision-value-label';
      proposedHdr.textContent = 'Proposed';
      var proposedVal = App.ui.codeBlock({
        className: 'revision-value', testid: 'revision-proposed'
      }).el;
      proposedBlock.appendChild(proposedHdr);
      proposedBlock.appendChild(proposedVal);
      card.appendChild(proposedBlock);

      renderDiffedValues(baseVal, proposedVal, revision.base_value, revision.proposed_value);

      var errorStatus = App.ui.status({
        state: 'danger', led: false, role: 'alert', testid: 'revision-error'
      });
      var actionError = errorStatus.el;
      actionError.classList.add('self-configuration-error');
      actionError.hidden = true;
      card.appendChild(actionError);

      var actions = document.createElement('div');
      actions.className = 'revision-actions';

      // A short snippet of the proposed value distinguishes this card's
      // Approve/Dismiss from every other card's for a screen-reader rotor
      // (SC 2.4.6) — plain "Approve"/"Dismiss" is identical across cards.
      var snippet = revision.proposed_value ? revision.proposed_value : '(empty)';
      if (snippet.length > 40) snippet = snippet.slice(0, 40) + '…';
      var fieldLower = ctx.fieldName(revision.field).toLowerCase();

      var approveBtn = App.ui.button({
        variant: 'primary',
        label: 'Approve',
        ariaLabel: 'Approve ' + fieldLower + ' revision: “' + snippet + '”',
        className: 'revision-approve-btn',
        testid: 'revision-approve-btn'
      });

      var dismissBtn = App.ui.button({
        variant: 'secondary',
        label: 'Dismiss',
        ariaLabel: 'Dismiss ' + fieldLower + ' revision: “' + snippet + '”',
        className: 'revision-dismiss-btn',
        testid: 'revision-dismiss-btn'
      });

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
        // A failure that lands after the operator collapsed the expander opens it again.
        queueCard.open();
        actionError.hidden = false;
        errorStatus.set('danger', 'Action failed: ' +
          (err && err.message ? err.message : String(err)));
        setBusy(false);
      }

      function renderStale(detail) {
        // The row drifted since the agent proposed. Show what re-approving
        // would overwrite and require an explicit override confirm.
        queueCard.open();
        stalePanel.hidden = false;
        stalePanel.textContent = '';

        // HAT "match design language": the drift advisory reuses
        // `.banner-warning` (components.css) instead of an unstyled <p>.
        var warn = App.ui.banner({
          tone: 'warning', role: 'alert', className: 'revision-stale-warning',
          text: 'This value has changed since the agent proposed its revision. ' +
            'Approving will overwrite the current value below.'
        });
        stalePanel.appendChild(warn.el);

        var curHdr = document.createElement('div');
        curHdr.className = 'revision-value-label';
        curHdr.textContent = 'Current value now';
        var curVal = App.ui.codeBlock({
          className: 'revision-value', testid: 'revision-current', text: detail.current_value
        }).el;
        stalePanel.appendChild(curHdr);
        stalePanel.appendChild(curVal);

        var propHdr = document.createElement('div');
        propHdr.className = 'revision-value-label';
        propHdr.textContent = 'Proposed value';
        var propVal = App.ui.codeBlock({
          className: 'revision-value', testid: 'revision-stale-proposed', text: detail.proposed_value
        }).el;
        stalePanel.appendChild(propHdr);
        stalePanel.appendChild(propVal);

        var overrideBtn = App.ui.button({
          variant: 'primary',
          label: 'Overwrite and approve',
          ariaLabel: 'Overwrite and approve ' + fieldLower + ' revision: “' + snippet + '”',
          className: 'revision-override-btn',
          testid: 'revision-override-btn'
        });
        overrideBtn.onclick = function () {
          if (!callbacks.onApproveRevision) return;
          setBusy(true);
          overrideBtn.disabled = true;
          callbacks.onApproveRevision(ctx.agent.name, revision.id, true).then(function (result) {
            // Override should apply (re-captures base_value). On success the
            // revisions are refetched and the resolved row leaves the queue.
            if (result && result.stale) {
              // Extremely unlikely (drifted again between calls) — re-render.
              renderStale(result.detail);
              overrideBtn.disabled = false;
              return;
            }
            ctx.announce('Approved the ' + fieldLower + ' revision, overwriting the current value.');
            ctx.refetchRevisions();
          }).catch(function (err) {
            showActionError(err);
          });
        };
        stalePanel.appendChild(overrideBtn);
        setBusy(false);
      }

      approveBtn.onclick = function () {
        if (!callbacks.onApproveRevision) return;
        setBusy(true);
        callbacks.onApproveRevision(ctx.agent.name, revision.id, false).then(function (result) {
          if (result && result.stale) {
            // No refresh happened for a stale detection — the card stays
            // mounted and gains the override panel in place, so there is
            // nothing to announce/focus yet (the override click above
            // covers the actual apply).
            renderStale(result.detail);
            return;
          }
          // Applied: the revisions are refetched and the resolved row leaves
          // the pending list.
          ctx.announce('Approved the ' + fieldLower + ' revision.');
          ctx.refetchRevisions();
        }).catch(function (err) {
          showActionError(err);
        });
      };

      dismissBtn.onclick = function () {
        if (!callbacks.onDismissRevision) return;
        setBusy(true);
        callbacks.onDismissRevision(ctx.agent.name, revision.id).then(function () {
          ctx.announce('Dismissed the ' + fieldLower + ' revision.');
          ctx.refetchRevisions();
        }).catch(function (err) {
          showActionError(err);
        });
      };

      return card;
    }

    function renderQueue(revisions) {
      queueList.textContent = '';
      var pending = (revisions || []).filter(function (r) { return r.status === 'pending'; });
      // The card owns the count: a chip on the expander, or at zero the plain
      // "Waiting for approval (0)" line (`pending-queue-empty`).
      queueCard.setCount(pending.length);
      pending.forEach(function (rev) {
        queueList.appendChild(renderCard(rev));
      });
    }

    ctx.queueList = queueList;
    ctx.renderQueue = renderQueue;
  }

  window.App.studio.selfConfigRevisions = {
    build: build,
    diffSegments: diffSegments,
    renderDiffedValues: renderDiffedValues
  };
})();
