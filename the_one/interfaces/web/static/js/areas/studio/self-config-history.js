// App.studio.selfConfigHistory — the Self-configuration tab's revision history and
// restore controls (M31 F2 L10b: split out of self-configuration-tab.js, a pure
// restructure). `build(ctx)` appends the history section to `ctx.panel` and
// publishes `ctx.historyList` and `ctx.renderHistory`; it reads `ctx.agent` and the
// cross-module `ctx.announce` / `ctx.refetchRevisions` at call time. The timestamp
// formatters and `fieldName` are exported for the other modules.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

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

  function build(ctx) {
    var panel = ctx.panel;
    var callbacks = ctx.callbacks;
    var renderDiffedValues = window.App.studio.selfConfigRevisions.renderDiffedValues;

    // ── M21 F02 L03 — revision history + restore ────────────────────────
    var historySectionCtl = App.ui.section({
      title: 'Revision history',
      titleTag: 'h3',
      className: 'self-configuration-history-section'
    });
    var historySection = historySectionCtl.body;

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

    // …and the collapsible "History (N)" disclosure below for the
    // chronological log (HAT fix #10 — App.ui.disclosure, plain variant, a
    // native `<details>`). The restore list above stays always visible; only
    // the full log collapses.
    var historyCtl = App.ui.disclosure({
      variant: 'plain',
      summary: 'History',
      testid: 'revision-history-details',
      summaryTestid: 'revision-history-summary',
      className: 'self-configuration-history-details'
    });
    var historyDetails = historyCtl.el;

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
    historyCtl.body.appendChild(historyList);

    historySection.appendChild(historyDetails);

    panel.appendChild(historySectionCtl.el);

    // ── M21 F02 L03 — revision history + restore rendering ──────────────
    function fieldName(field) {
      return field === 'system_prompt' ? 'System prompt' : 'Description';
    }

    // Maps a revision's `status` (applied/pending/dismissed/superseded —
    // see db/models.py AgentRevision) to an App.ui.status state.
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

      var preview = App.ui.codeBlock({
        className: 'revision-value restore-node-value', text: node.value
      }).el;
      row.appendChild(preview);

      // A short snippet of this node's own value distinguishes it from
      // every other Restore button for a screen-reader rotor (SC 2.4.6)
      // — plain "Restore this description value" repeats verbatim across
      // nodes. Nodes are already deduped per-field (see below), so the
      // snippet is unique among a field's own nodes.
      var nodeSnippet = node.value ? node.value : '(empty)';
      if (nodeSnippet.length > 40) nodeSnippet = nodeSnippet.slice(0, 40) + '…';

      // Labelled for assistive tech — names the field it restores and a
      // snippet of the value, so it reads distinctly from sibling nodes.
      var restoreBtn = App.ui.button({
        variant: 'secondary',
        size: 'sm',
        label: 'Restore',
        ariaLabel: 'Restore this ' + fieldName(node.field).toLowerCase() +
          ' value: “' + nodeSnippet + '”',
        className: 'revision-restore-btn',
        testid: 'revision-restore-btn'
      });
      restoreBtn.setAttribute('data-revision-id', node.revisionId);
      restoreBtn.setAttribute('data-side', node.side);
      row.appendChild(restoreBtn);

      var errorStatus = App.ui.status({
        state: 'danger', led: false, role: 'alert', testid: 'revision-restore-error'
      });
      var nodeError = errorStatus.el;
      nodeError.classList.add('self-configuration-error');
      nodeError.hidden = true;
      row.appendChild(nodeError);

      restoreBtn.onclick = function () {
        if (!callbacks.onRestoreRevision) return;
        restoreBtn.disabled = true;
        nodeError.hidden = true;
        errorStatus.set('danger', '');
        // On success the revisions are refetched — the new restore row appears
        // in the history.
        callbacks.onRestoreRevision(ctx.agent.name, node.revisionId, node.side)
          .then(function () {
            ctx.announce('Restored ' + fieldName(node.field).toLowerCase() + ' to an earlier value.');
            ctx.refetchRevisions();
          })
          .catch(function (err) {
            nodeError.hidden = false;
            errorStatus.set('danger', 'Restore failed: ' +
              (err && err.message ? err.message : String(err)));
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
      historyList.textContent = '';
      historyCtl.setSummary('History (' + revisions.length + ')');
      if (revisions.length === 0) {
        historyList.appendChild(App.ui.emptyState({
          title: 'No revisions yet.',
          titleTag: 'p',
          variant: 'plain',
          testid: 'revision-history-empty'
        }));
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

          // HAT "match design language": a status LED, paired with the status
          // word already in the visible text (so it is decorative), as one
          // App.ui.status line.
          // source + status + timestamp, human-readable and attributable.
          // HAT fix #4: formatted relative time instead of the raw ISO
          // string; the exact instant stays available via `title=`.
          var sourceLabel;
          if (rev.source === 'restore') {
            sourceLabel = 'restored';
          } else if (rev.source === 'external') {
            // source_principal is the credential IDENTIFIER (e.g.
            // "ext_abc123"), never the secret — safe to display. Built via
            // string concat into a textContent assignment below, so no
            // markup injection risk even if the identifier ever contained
            // special characters.
            sourceLabel = (typeof rev.source_principal === 'string' && rev.source_principal)
              ? 'external (' + rev.source_principal + ')'
              : 'external';
          } else {
            sourceLabel = 'self-revised';
          }
          var ts = formatRevisionTimestamp(rev.created_at);
          var metaStatus = App.ui.status({
            state: statusLedVariant(rev.status),
            text: sourceLabel + ' · ' + rev.status + (ts.text ? ' · ' + ts.text : ''),
            live: 'off'
          });
          var meta = metaStatus.el;
          meta.classList.add('history-entry-meta');
          if (ts.title) meta.title = ts.title;
          head.appendChild(meta);
          entry.appendChild(head);

          // HAT fix #6: only the changed span is highlighted instead of
          // two bare full-text blocks.
          var change = document.createElement('div');
          change.className = 'history-entry-change';
          var beforeVal = App.ui.codeBlock({
            className: 'revision-value history-entry-before'
          }).el;
          var arrow = document.createElement('span');
          arrow.className = 'history-entry-arrow';
          arrow.setAttribute('aria-label', 'changed to');
          arrow.textContent = '→';
          var afterVal = App.ui.codeBlock({
            className: 'revision-value history-entry-after'
          }).el;
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
      restoreControls.textContent = '';
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
        restoreControls.appendChild(App.ui.emptyState({
          title: 'No earlier values to restore.',
          titleTag: 'p',
          variant: 'plain',
          testid: 'revision-restore-empty'
        }));
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

    ctx.historyList = historyList;
    ctx.renderHistory = renderHistory;
    ctx.fieldName = fieldName;
  }

  window.App.studio.selfConfigHistory = {
    build: build,
    formatTimeAgo: formatTimeAgo,
    formatRevisionTimestamp: formatRevisionTimestamp
  };
})();
