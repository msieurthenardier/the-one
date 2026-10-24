// App.studio.knowledgeSearch — the Knowledge detail's Search section (Mission
// 24 Flight 6, DD-6; split out of knowledge-section.js in Mission 31 Flight 3
// Leg 02). `create({kb, root})` appends its section to `root` at call time.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;

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

    // The snippet as plain text: line endings normalised, whitespace-only
    // lines emptied, every run of blank lines collapsed to one, and the ends
    // trimmed. Shown with textContent only (pre-line, clamped to three lines
    // in CSS).
    function snippetText(text) {
      return String(text || '')
        .replace(/\r\n?/g, '\n')
        .replace(/^[ \t]+$/gm, '')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
    }

    // One hit: the file name, a meta line (the full path, ellipsised, with
    // the path also as its title, then the score), and the snippet.
    function buildHit(hit) {
      var row = K.el('li', { className: 'kb-search-hit' });
      row.setAttribute('data-testid', 'kb-search-hit');
      row.appendChild(K.el('div', { className: 'kb-search-hit-title', text: K.baseName(hit.path) }));
      var meta = K.el('div', { className: 'kb-search-hit-meta' });
      var path = K.el('span', { className: 'kb-search-hit-path', text: hit.path });
      path.title = hit.path;
      meta.appendChild(path);
      meta.appendChild(K.el('span', { className: 'kb-search-hit-score', text: 'score ' + hit.score.toFixed(3) }));
      row.appendChild(meta);
      row.appendChild(K.el('div', { className: 'kb-search-hit-text', text: snippetText(hit.text) }));
      return row;
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
      App.api.fetchJson(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) +
        '/search?q=' + encodeURIComponent(q) + '&limit=10'
      )
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
          var list = K.el('ul', { className: 'kb-search-hit-list' });
          result.hits.forEach(function (hit) { list.appendChild(buildHit(hit)); });
          resultsEl.appendChild(list);
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
