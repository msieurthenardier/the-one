// App.studio.knowledgeInspect — the Knowledge detail's chunks and source
// panels (Mission 24 Flight 6; split out of knowledge-section.js in
// Mission 31 Flight 3 Leg 02).
//
// `create({kb})` builds the two panels, hidden, and returns
// `{chunksPanel, sourcePanel, openChunks(item), openSource(item)}`. It appends
// nothing: the detail appends the panels to the Folders section. DD-8: neither
// panel is fetched while the item list renders, only on the operator's click.
// Per-mount state (the two panel nodes) lives inside each `create` call.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var _el = K.el;
  var _errorMessageFromResponse = K.errorMessageFromResponse;

  function create(ctx) {
    var kb = ctx.kb;
    // One slot for both panels (leg 06b): opening either one makes any pending
    // response for the other (or for an earlier item) a no-op.
    var slot = App.ui.util.mountSlot();

    // kb-studio-round-trip remediation FIX 4: both panels render at a fixed
    // position and, with more than one row, nothing on screen said which item's
    // content is showing. Each panel's heading is built once and titled with
    // the item's own path on open; only the content region below it changes, so
    // focus on the heading survives the response landing.
    function buildPanel(className, heading) {
      var section = App.ui.section({
        title: heading,
        titleTag: 'h3',
        className: 'kb-inspect-panel ' + className
      });
      var titleEl = section.el.firstElementChild;
      titleEl.setAttribute('tabindex', '-1');
      titleEl.setAttribute('data-testid', 'kb-panel-title');
      var content = _el('div', { className: 'kb-inspect-content' });
      section.el.appendChild(content);
      section.el.hidden = true;
      return { section: section, el: section.el, titleEl: titleEl, content: content };
    }

    var chunks = buildPanel('kb-chunks-panel', 'Chunks');
    chunks.el.setAttribute('data-testid', 'kb-chunks-panel');
    var source = buildPanel('kb-source-panel', 'Source');
    source.el.setAttribute('data-testid', 'kb-source-panel');

    function setLine(panel, state, text) {
      panel.content.textContent = '';
      var line = state === 'pending'
        ? App.ui.status({ led: false, live: 'off' })
        : App.ui.status({ led: false, live: 'polite', role: 'alert', textTone: true });
      line.set(state, text);
      panel.content.appendChild(line.el);
    }

    // DD-8/AC-13: neither is fetched while rendering the item list — only on
    // the operator's explicit click.
    function open(panel, other, item, loadingText, path, render) {
      var token = slot.mount(function () {});
      other.el.hidden = true;
      panel.el.hidden = false;
      panel.section.setTitle(item.path_or_url);
      setLine(panel, 'pending', loadingText);
      // The menu has already returned focus to its trigger; move it to the
      // opened panel so it is never left on a hidden menu item.
      panel.titleEl.focus();
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) +
        '/items/' + encodeURIComponent(item.id) + path)
        .then(function (r) {
          if (!r.ok) {
            return r.text().then(function (body) {
              throw new Error(_errorMessageFromResponse(body) || ('HTTP ' + r.status));
            });
          }
          return r.json();
        })
        .then(function (data) {
          if (!slot.isCurrent(token)) return;
          panel.content.textContent = '';
          render(data);
        })
        .catch(function (err) {
          if (!slot.isCurrent(token)) return;
          setLine(panel, 'danger', err.message || String(err));
        });
    }

    function openChunksPanel(item) {
      open(chunks, source, item, 'Loading chunks…', '/chunks', function (list) {
        if (list.length === 0) {
          chunks.content.appendChild(App.ui.emptyState({ title: 'No chunks yet.', titleTag: 'p' }));
          return;
        }
        // AC-13: render in seq order (the route already pages in seq order;
        // sort defensively so the UI's own contract doesn't depend on that).
        list.sort(function (a, b) { return a.seq - b.seq; });
        list.forEach(function (c) {
          var row = _el('div', { className: 'kb-chunk-row' });
          row.setAttribute('data-testid', 'kb-chunk-row');
          row.appendChild(_el('span', { className: 'kb-chunk-seq', text: '#' + c.seq }));
          row.appendChild(_el('span', { className: 'kb-chunk-text', text: c.text }));
          chunks.content.appendChild(row);
        });
      });
    }

    function openSourcePanel(item) {
      open(source, chunks, item, 'Loading source…', '/source', function (result) {
        var pre = _el('pre', { className: 'kb-source-text', text: result.text });
        pre.setAttribute('data-testid', 'kb-source-text');
        source.content.appendChild(pre);
      });
    }

    return {
      chunksPanel: chunks.el,
      sourcePanel: source.el,
      openChunks: openChunksPanel,
      openSource: openSourcePanel,
      destroy: function () { slot.destroy(); }
    };
  }

  window.App.studio.knowledgeInspect = { create: create };
})();
