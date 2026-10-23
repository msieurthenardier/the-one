// App.studio.knowledgeStatus — the Knowledge detail's Status section: the
// per-status counts, chunk count and indexer line, plus the whole-knowledge-
// base re-index controls (Mission 24 Flight 6; split out of
// knowledge-section.js in Mission 31 Flight 3 Leg 02).
//
// `create({kb, root, initialStatus, refreshStatus})` appends its section to
// `root` at call time (so the detail calls it after the Folders section) and
// returns `{update(status)}`. `refreshStatus` is the detail's lazy wrapper
// that fetches `/status` and updates both this module and the folders.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var STATUS_LABELS = K.STATUS_LABELS;

  function create(ctx) {
    var root = ctx.root;
    var initialStatus = ctx.initialStatus;
    var kb = ctx.kb;
    function isLive() { return ctx.isLive ? ctx.isLive() : true; }
    function refreshStatusNow() { return ctx.refreshStatus(); }

    // ── Status (AC-6, amended by the HAT polish pass) — counts / chunks /
    // indexer, plus the re-index controls. Created AFTER the folders section
    // so it renders BELOW it. Built once from the library (M31 F3 L05b): the
    // chips and the two lines are patched only when their text changes, so an
    // unchanged poll tick writes nothing to the DOM. The detail mounts this
    // only after /status resolved, so `update` never receives null.
    var summaryEl = document.createElement('div');
    summaryEl.className = 'kb-status-summary';
    summaryEl.setAttribute('data-testid', 'kb-status-summary');
    var countsRow = document.createElement('div');
    countsRow.className = 'kb-status-counts';
    summaryEl.appendChild(countsRow);
    var chipEls = {};
    var chipText = {};
    STATUS_LABELS.forEach(function (label) {
      chipText[label] = label + ': 0';
      chipEls[label] = App.ui.chip({
        label: chipText[label],
        dataset: { status: label },
        testid: 'kb-status-count'
      });
      countsRow.appendChild(chipEls[label]);
    });
    var chunkLine = App.ui.status({ led: false, live: 'off', testid: 'kb-chunk-count' });
    var indexerLine = App.ui.status({ led: false, live: 'off', testid: 'kb-indexer-state' });
    var chunkText = null;
    var indexerText = null;
    summaryEl.appendChild(chunkLine.el);
    summaryEl.appendChild(indexerLine.el);

    // The scope hint: both buttons POST to /reindex, which is whole-knowledge-
    // base by construction (`requeue_for_reindex` is one UPDATE across every
    // folder) — there is no per-folder re-index.
    var reindexChangedBtn = App.ui.button({
      variant: 'secondary',
      label: 'Re-index changed files',
      testid: 'kb-reindex-changed-btn',
      onClick: function () { triggerReindex('changed'); }
    });
    var reindexAllBtn = App.ui.button({
      variant: 'secondary',
      label: 'Re-index all files',
      testid: 'kb-reindex-all-btn',
      onClick: function () { triggerReindex('all'); }
    });
    var reindexRow = document.createElement('div');
    reindexRow.className = 'kb-reindex-row';
    reindexRow.appendChild(reindexChangedBtn);
    reindexRow.appendChild(reindexAllBtn);

    var section = App.ui.section({
      title: 'Status',
      description:
        'Re-indexing always covers every folder registered in this knowledge base — ' +
        'there is no per-folder re-index. "Changed files" re-walks each folder and ' +
        'indexes only what differs; "All files" re-embeds every file from scratch.',
      descriptionTestid: 'kb-reindex-scope-hint',
      children: [summaryEl, reindexRow]
    });
    root.appendChild(section.el);

    function renderStatusSummary(status) {
      if (!status) return;
      var counts = status.items || {};
      STATUS_LABELS.forEach(function (label) {
        var text = label + ': ' + (counts[label] || 0);
        if (text !== chipText[label]) {
          chipText[label] = text;
          chipEls[label].textContent = text;
        }
      });
      var chunks = 'Chunks: ' + status.chunks;
      if (chunks !== chunkText) {
        chunkText = chunks;
        chunkLine.set('idle', chunks);
      }
      var indexer = 'Indexer: ' + status.indexer;
      if (indexer !== indexerText) {
        indexerText = indexer;
        indexerLine.set('idle', indexer);
      }
    }
    renderStatusSummary(initialStatus);

    function triggerReindex(scope) {
      reindexChangedBtn.disabled = true;
      reindexAllBtn.disabled = true;
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/reindex?scope=' + scope,
        { method: 'POST' }
      )
        .then(function (r) {
          if (!r.ok) throw new Error('Re-index request failed: HTTP ' + r.status);
          return r.json();
        })
        // The reindex response carries no indexer state, so issue one
        // immediate status fetch rather than waiting a full poll interval.
        .then(function () { if (isLive()) refreshStatusNow(); })
        .catch(function () {
          // Leave last-rendered state; the operator can retry.
        })
        .then(function () {
          if (!isLive()) return;
          reindexChangedBtn.disabled = false;
          reindexAllBtn.disabled = false;
        });
    }

    // destroy is a no-op here: late responses are gated by ctx.isLive().
    return { update: renderStatusSummary, destroy: function () {} };
  }

  window.App.studio.knowledgeStatus = { create: create };
})();
