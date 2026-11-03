// App.studio.knowledgeInspect — the Knowledge detail's chunks and source
// panels (Mission 24 Flight 6; split out of knowledge-section.js in
// Mission 31 Flight 3 Leg 02).
//
// `create({kb, onClose})` builds the two panels, hidden, and returns
// `{chunksPanel, sourcePanel, openChunks(item, opener), openSource(item,
// opener), close(), closeUnless(liveIds), destroy()}`. It appends nothing: the
// detail appends the panels to the Folders section. DD-8: neither panel is
// fetched while the item list renders, only on the operator's click.
// Per-mount state (the two panel nodes and the slot) lives inside each
// `create` call.
//
// M31 F3 HAT: each panel is headed by a static "Chunks"/"Source" h3 (the
// focus target on open), then a line with the file's name and a line with its
// full path (ellipsised, the path as `title`), and a close (x) button. The h3
// is named by itself plus the name line, so focus announces "Chunks
// runbook-01.md". One mount slot holds the open panel with `{item, opener,
// panel}`: opening the other panel destroys the first, and closing hides the
// panel and clears its content, so a late response fails `isCurrent` and is
// dropped. After a close, `ctx.onClose(item, opener)` (the detail wires it to
// the folders module) puts focus back. Escape does not close a panel: it is an
// inline, non-modal region.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var K = window.App.studio.knowledgeShared;
  var _el = K.el;
  var _baseName = K.baseName;

  function create(ctx) {
    var kb = ctx.kb;
    // One slot for both panels (leg 06b): opening either one makes any pending
    // response for the other (or for an earlier item) a no-op.
    var slot = App.ui.util.mountSlot();

    // kb-studio-round-trip remediation FIX 4: both panels render at a fixed
    // position and, with more than one row, nothing on screen said which item's
    // content is showing. The heading is built once and never retitled; the
    // name and path lines under it name the item, and only the content region
    // below them changes, so focus on the heading survives the response landing.
    function buildPanel(className, heading, closeLabel) {
      var section = App.ui.section({
        title: heading,
        titleTag: 'h3',
        className: 'kb-inspect-panel ' + className
      });
      var titleEl = section.el.firstElementChild;
      titleEl.setAttribute('tabindex', '-1');
      titleEl.setAttribute('data-testid', 'kb-panel-title');
      if (!titleEl.id) titleEl.id = App.ui.util.uid('kb-panel-title');

      var head = _el('div', { className: 'kb-inspect-head' });
      var file = _el('div', { className: 'kb-inspect-file' });
      var nameEl = _el('span', { className: 'kb-inspect-name' });
      nameEl.id = App.ui.util.uid('kb-panel-file-name');
      nameEl.setAttribute('data-testid', 'kb-panel-file-name');
      var pathEl = _el('span', { className: 'kb-inspect-path' });
      pathEl.setAttribute('data-testid', 'kb-panel-file-path');
      file.appendChild(nameEl);
      file.appendChild(pathEl);
      var closeBtn = App.ui.button({
        variant: 'ghost',
        size: 'sm',
        iconOnly: true,
        icon: 'x',
        ariaLabel: closeLabel,
        testid: 'kb-panel-close-btn',
        onClick: function () { close(); }
      });
      closeBtn.title = 'Close';
      head.appendChild(file);
      head.appendChild(closeBtn);
      section.el.appendChild(head);
      titleEl.setAttribute('aria-labelledby', titleEl.id + ' ' + nameEl.id);

      var content = _el('div', { className: 'kb-inspect-content' });
      section.el.appendChild(content);
      // Squawk 0239: the pending line is silent (focus is already on the
      // heading), so a persistent polite live region, present before its text
      // changes, announces the result when a load finishes.
      var announce = _el('span', { className: 'visually-hidden' });
      announce.setAttribute('role', 'status');
      announce.setAttribute('aria-live', 'polite');
      announce.setAttribute('data-testid', 'kb-panel-announce');
      section.el.appendChild(announce);
      section.el.hidden = true;
      return {
        section: section, el: section.el, titleEl: titleEl,
        nameEl: nameEl, pathEl: pathEl, content: content, announce: announce
      };
    }

    var chunks = buildPanel('kb-chunks-panel', 'Chunks', 'Close chunks');
    chunks.el.setAttribute('data-testid', 'kb-chunks-panel');
    var source = buildPanel('kb-source-panel', 'Source', 'Close source');
    source.el.setAttribute('data-testid', 'kb-source-panel');

    function hidePanel(panel) {
      panel.el.hidden = true;
      panel.content.textContent = '';
      panel.announce.textContent = '';
    }

    // Closes the open panel (no-op when none is open), then hands focus back
    // through `ctx.onClose` unless `quiet` says focus was elsewhere.
    function closeCurrent(quiet) {
      var cur = slot.current();
      if (!cur) return;
      slot.destroy();
      if (!quiet && ctx.onClose) ctx.onClose(cur.data.item, cur.data.opener);
    }

    function close() { closeCurrent(false); }

    // After every items render: an open panel whose item is no longer listed
    // closes. Focus moves only if it was inside the panel.
    function closeUnless(liveIds) {
      var cur = slot.current();
      if (!cur || (liveIds && liveIds[cur.data.item.id])) return;
      var active = document.activeElement;
      var hadFocus = !!active && cur.data.panel.el.contains(active);
      closeCurrent(!hadFocus);
    }

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
    function open(panel, item, opener, loadingText, path, render, announceText) {
      var token = slot.mount(function () { hidePanel(panel); },
        { item: item, opener: opener, panel: panel });
      panel.el.hidden = false;
      panel.nameEl.textContent = _baseName(item.path_or_url);
      panel.pathEl.textContent = item.path_or_url;
      panel.pathEl.title = item.path_or_url;
      panel.announce.textContent = '';
      setLine(panel, 'pending', loadingText);
      // The menu has already returned focus to its trigger; move it to the
      // opened panel so it is never left on a hidden menu item.
      panel.titleEl.focus();
      App.api.fetchJson('/api/knowledge-bases/' + encodeURIComponent(kb.id) +
        '/items/' + encodeURIComponent(item.id) + path)
        .then(function (data) {
          if (!slot.isCurrent(token)) return;
          panel.content.textContent = '';
          render(data);
          panel.announce.textContent = announceText(data);
        })
        .catch(function (err) {
          if (!slot.isCurrent(token)) return;
          setLine(panel, 'danger', err.message || String(err));
        });
    }

    function openChunksPanel(item, opener) {
      open(chunks, item, opener, 'Loading chunks…', '/chunks', function (list) {
        if (list.length === 0) {
          chunks.content.appendChild(App.ui.emptyState({ title: 'No chunks yet.', titleTag: 'p' }));
          return;
        }
        // AC-13: render in seq order (the route already pages in seq order;
        // sort defensively so the UI's own contract doesn't depend on that).
        list.sort(function (a, b) { return a.seq - b.seq; });
        // M31 F3 HAT: the rows sit in one box, the same box as the source text;
        // the loading, error and empty lines stay outside it.
        var box = _el('div', { className: 'kb-chunk-list' });
        box.setAttribute('data-testid', 'kb-chunk-list');
        list.forEach(function (c) {
          var row = _el('div', { className: 'kb-chunk-row' });
          row.setAttribute('data-testid', 'kb-chunk-row');
          row.appendChild(_el('span', { className: 'kb-chunk-seq', text: '#' + c.seq }));
          row.appendChild(_el('span', { className: 'kb-chunk-text', text: c.text }));
          box.appendChild(row);
        });
        chunks.content.appendChild(box);
      }, function (list) {
        if (list.length === 0) return 'No chunks yet';
        return list.length + (list.length === 1 ? ' chunk' : ' chunks');
      });
    }

    function openSourcePanel(item, opener) {
      open(source, item, opener, 'Loading source…', '/source', function (result) {
        var pre = _el('pre', { className: 'kb-source-text', text: result.text });
        pre.setAttribute('data-testid', 'kb-source-text');
        source.content.appendChild(pre);
      }, function () { return 'Source loaded'; });
    }

    return {
      chunksPanel: chunks.el,
      sourcePanel: source.el,
      openChunks: openChunksPanel,
      openSource: openSourcePanel,
      close: close,
      closeUnless: closeUnless,
      destroy: function () { slot.destroy(); }
    };
  }

  window.App.studio.knowledgeInspect = { create: create };
})();
