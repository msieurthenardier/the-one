// App.studio.knowledgeSearch — the Knowledge detail's Search section (Mission
// 24 Flight 6, DD-6; split out of knowledge-section.js in Mission 31 Flight 3
// Leg 02). `create({kb, root})` appends its section to `root` at call time.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function create(ctx) {
    var root = ctx.root;
    var kb = ctx.kb;
    function isLive() { return ctx.isLive ? ctx.isLive() : true; }

    // ── Search (AC-6, DD-6), on the library since M31 F3 L05b ────────────
    // Every search, clear and destroy bumps `generation`; a response (or
    // failure) for an older generation is dropped, so a slow first search can
    // never overwrite a later one's results.
    var generation = 0;
    var searchField = App.ui.clearableInput({
      id: 'kb-search-query',
      placeholder: 'Search this knowledge base',
      testid: 'kb-search-input',
      dataset: { field: 'q' },
      label: 'Search',
      clearTestid: 'kb-search-clear-btn',
      onClear: function () {
        generation += 1;
        resultsEl.textContent = '';
        degradedLine.el.hidden = true;
        announcer.set('idle', '');
      }
    });
    var searchInput = searchField.input;
    var queryField = App.ui.field({
      label: 'Search',
      control: searchInput,
      host: searchField.el
    });
    var searchBtn = App.ui.button({
      variant: 'secondary',
      label: 'Search',
      testid: 'kb-search-btn',
      onClick: runSearch
    });
    // The degrade line and the indexer word come from the SAME search response,
    // never the polled status (AC-12).
    var degradedLine = App.ui.status({
      state: 'danger', led: false, live: 'polite', textTone: true, testid: 'kb-search-degraded'
    });
    degradedLine.el.hidden = true;
    // WCAG 4.1.3: a visually hidden polite status says what a search came back with.
    var announcer = App.ui.status({
      state: 'idle', led: false, testid: 'kb-search-announcer'
    });
    announcer.el.classList.add('visually-hidden');
    announcer.set('idle', '');
    var resultsEl = document.createElement('div');
    resultsEl.className = 'kb-search-results';
    resultsEl.setAttribute('data-testid', 'kb-search-results');
    var section = App.ui.section({
      title: 'Search',
      children: [queryField.el, searchBtn, degradedLine.el, announcer.el, resultsEl]
    });
    root.appendChild(section.el);

    function el(cls, text) {
      var n = document.createElement('span');
      n.className = cls;
      n.textContent = text;
      return n;
    }

    function runSearch() {
      generation += 1;
      var mine = generation;
      var q = searchInput.value;
      resultsEl.textContent = '';
      degradedLine.el.hidden = true;
      announcer.set('idle', '');
      if (!q.trim()) return;
      var searching = App.ui.status({ state: 'pending', led: false, live: 'off' });
      searching.set('pending', 'Searching…');
      resultsEl.appendChild(searching.el);
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) +
        '/search?q=' + encodeURIComponent(q) + '&limit=10'
      )
        .then(function (r) {
          if (!r.ok) throw new Error('Search failed: HTTP ' + r.status);
          return r.json();
        })
        .then(function (result) {
          if (!isLive() || mine !== generation) return;
          resultsEl.textContent = '';
          if (result.degraded) {
            degradedLine.el.hidden = false;
            degradedLine.set(
              'danger', 'Degraded: ' + result.degraded + ' (indexer: ' + result.indexer + ')'
            );
          }
          var n = result.hits.length;
          announcer.set('idle', n === 0 ? 'No results.' : n === 1 ? '1 result' : n + ' results');
          if (n === 0) {
            resultsEl.appendChild(App.ui.emptyState({ title: 'No results.', titleTag: 'p' }));
            return;
          }
          result.hits.forEach(function (hit) {
            var row = document.createElement('div');
            row.className = 'kb-search-hit';
            row.setAttribute('data-testid', 'kb-search-hit');
            row.appendChild(el('kb-search-hit-path', hit.path));
            row.appendChild(el('kb-search-hit-score', 'score: ' + hit.score.toFixed(3)));
            row.appendChild(el('kb-search-hit-text', hit.text));
            resultsEl.appendChild(row);
          });
        })
        .catch(function (err) {
          if (!isLive() || mine !== generation) return;
          resultsEl.textContent = '';
          var failed = App.ui.status({
            state: 'danger', led: false, role: 'alert', textTone: true
          });
          failed.set('danger', err.message || String(err));
          resultsEl.appendChild(failed.el);
        });
    }
    searchInput.addEventListener('keydown', onEnter);
    function onEnter(e) {
      if (e.key === 'Enter') { e.preventDefault(); runSearch(); }
    }

    return {
      destroy: function () {
        generation += 1;
        searchInput.removeEventListener('keydown', onEnter);
        searchField.destroy();
      }
    };
  }

  window.App.studio.knowledgeSearch = { create: create };
})();
