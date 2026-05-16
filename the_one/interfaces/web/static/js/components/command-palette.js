// L8 — Command Palette (⌘K).
//
// Overlay dialog. Reuses dialog.js patterns: capture-phase keydown,
// focus trap, restore-focus-on-close-only-if-trigger-still-connected.
// Closes on hashchange and on topnav:rerender (L7.8) when the trigger
// anchor was removed.
//
// Safe rendering: every dynamic string (agent names, session titles,
// provider names) is set via textContent. No insertAdjacentHTML on
// user-controlled text.
(function () {
  'use strict';

  var root = null;
  var inputEl = null;
  var resultsEl = null;
  var statusEl = null;
  var trigger = null;
  var items = [];
  var visibleItems = [];
  var activeIndex = 0;

  function build() {
    root = document.createElement('div');
    root.className = 'cp-overlay';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-labelledby', 'cp-title');
    root.setAttribute('data-testid', 'command-palette');
    root.style.display = 'none';

    var title = document.createElement('h2');
    title.id = 'cp-title';
    title.className = 'visually-hidden';
    title.textContent = 'Command palette';

    var card = document.createElement('div');
    card.className = 'cp-card';

    inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.className = 'cp-input';
    inputEl.setAttribute('placeholder', 'Type a command, agent, provider, or session…');
    inputEl.setAttribute('aria-controls', 'cp-results');
    inputEl.setAttribute('autocomplete', 'off');
    inputEl.setAttribute('spellcheck', 'false');

    statusEl = document.createElement('div');
    statusEl.className = 'cp-status';
    statusEl.setAttribute('aria-live', 'polite');

    resultsEl = document.createElement('ul');
    resultsEl.id = 'cp-results';
    resultsEl.className = 'cp-results';
    resultsEl.setAttribute('role', 'listbox');

    card.appendChild(inputEl);
    card.appendChild(statusEl);
    card.appendChild(resultsEl);
    root.appendChild(title);
    root.appendChild(card);

    root.addEventListener('click', function (e) {
      if (e.target === root) close();
    });
    inputEl.addEventListener('input', render);
    document.body.appendChild(root);
  }

  function rankedItems(query) {
    var fuzzy = window.App.commandFuzzy.score;
    if (!query) {
      // Empty state: show navigation + recent sessions.
      return items.filter(function (it) {
        return it.section === 'NAVIGATION' || it.section === 'SESSIONS';
      }).slice(0, 8);
    }
    var scored = items
      .map(function (it) { return { it: it, s: fuzzy(query, it) }; })
      .filter(function (x) { return x.s > 0; })
      .sort(function (a, b) { return b.s - a.s; });
    return scored.slice(0, 8).map(function (x) { return x.it; });
  }

  function render() {
    var query = inputEl.value;
    visibleItems = rankedItems(query);
    activeIndex = visibleItems.length > 0 ? 0 : -1;

    // Clear results.
    while (resultsEl.firstChild) resultsEl.removeChild(resultsEl.firstChild);

    // Group by section in display order.
    var order = ['NAVIGATION', 'AGENTS', 'PROVIDERS', 'SESSIONS', 'ACTIONS'];
    order.forEach(function (sec) {
      var inSection = visibleItems.filter(function (it) { return it.section === sec; });
      if (inSection.length === 0) return;
      var head = document.createElement('li');
      head.className = 'cp-section';
      head.setAttribute('role', 'presentation');
      head.textContent = sec;
      resultsEl.appendChild(head);
      inSection.forEach(function (it) {
        var li = document.createElement('li');
        li.className = 'cp-item';
        li.setAttribute('role', 'option');
        li.setAttribute('data-id', it.id);
        // Active highlight set below after all rows mounted.
        li.textContent = it.label;
        li.addEventListener('click', function () { invokeIndex(visibleItems.indexOf(it)); });
        resultsEl.appendChild(li);
      });
    });

    updateActiveHighlight();
    statusEl.textContent = window.App.commandCatalog.lastFetchHadFailures()
      ? 'Some results unavailable'
      : '';
  }

  function updateActiveHighlight() {
    var rows = resultsEl.querySelectorAll('.cp-item');
    for (var i = 0; i < rows.length; i++) {
      if (i === activeIndex) {
        rows[i].classList.add('active');
        rows[i].setAttribute('aria-selected', 'true');
      } else {
        rows[i].classList.remove('active');
        rows[i].removeAttribute('aria-selected');
      }
    }
  }

  function invokeIndex(idx) {
    if (idx < 0 || idx >= visibleItems.length) return;
    var item = visibleItems[idx];
    close();
    window.App.commandCatalog.invoke(item);
  }

  function onKeydown(e) {
    if (root.style.display === 'none') return;
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (visibleItems.length === 0) return;
      activeIndex = (activeIndex + 1) % visibleItems.length;
      updateActiveHighlight();
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (visibleItems.length === 0) return;
      activeIndex = (activeIndex - 1 + visibleItems.length) % visibleItems.length;
      updateActiveHighlight();
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      invokeIndex(activeIndex);
      return;
    }
    if (e.key === 'Tab') {
      // Focus trap — palette only has one focusable (the input), so we
      // just keep focus on it.
      e.preventDefault();
      inputEl.focus();
      return;
    }
  }

  function onHashChange() { if (root && root.style.display !== 'none') close(); }
  function onTopnavRerender() {
    if (root && root.style.display !== 'none' && trigger && !trigger.isConnected) {
      close();
    }
  }

  function open(triggerEl) {
    if (!root) build();
    trigger = triggerEl || null;
    inputEl.value = '';
    items = []; visibleItems = []; activeIndex = -1;
    statusEl.textContent = 'Loading…';
    root.style.display = 'flex';
    inputEl.focus();
    window.App.commandCatalog.build().then(function (built) {
      items = built;
      render();
    });
  }

  function close() {
    if (!root) return;
    root.style.display = 'none';
    if (trigger && trigger.isConnected && typeof trigger.focus === 'function') {
      try { trigger.focus(); } catch (e) { /* ignore */ }
    }
    trigger = null;
  }

  // Capture-phase keydown so palette sees keys before focused-field handlers.
  document.addEventListener('keydown', onKeydown, true);
  window.addEventListener('hashchange', onHashChange);
  document.addEventListener('topnav:rerender', onTopnavRerender);

  window.App = window.App || {};
  window.App.commandPalette = { open: open, close: close };
})();
