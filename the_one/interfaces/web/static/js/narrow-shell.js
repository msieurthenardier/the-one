/* Narrow-window overlay shell coordinator (Mission 38 Flight 1).
 *
 * Below 900px ((max-width: 899px)), #app-sidebar collapses offscreen by default
 * and opens as a left overlay beside #app-rail via a rail footer toggle. This
 * coordinator also enforces single-overlay exclusivity across #app-sidebar,
 * #chat-drawer, and #gleepglorp-drawer, keeping focus inside opened overlays
 * and returning focus on dismissal.
 */
(function () {
  'use strict';

  var NARROW_QUERY = '(max-width: 899px)';
  var LABELS = {
    chats: 'Chats',
    agents: 'Agents',
    library: 'Library',
    settings: 'Settings'
  };

  var overlays = Object.create(null);
  var mounted = false;
  var narrow = false;
  var sidebarOpen = false;
  var currentDest = 'chats';

  var row = null;
  var sidebar = null;
  var main = null;
  var toggleBtn = null;
  var bar = null;
  var titleEl = null;
  var closeBtn = null;
  var mq = null;

  function currentLabel() {
    return LABELS[currentDest] || 'List';
  }

  function isFocusableVisible(el) {
    if (!el || typeof el.focus !== 'function' || el.disabled) return false;
    if (!el.getClientRects || el.getClientRects().length === 0) return false;
    return !(el.closest && el.closest('[hidden]'));
  }

  function updateControls() {
    var label = currentLabel();
    if (titleEl) titleEl.textContent = label;
    if (row) {
      if (narrow) row.setAttribute('data-narrow', 'true');
      else row.removeAttribute('data-narrow');
    }
    if (sidebar) {
      if (narrow && sidebarOpen) sidebar.setAttribute('data-narrow-open', 'true');
      else sidebar.removeAttribute('data-narrow-open');
    }
    if (bar) bar.hidden = !(narrow && sidebarOpen);
    if (toggleBtn) {
      toggleBtn.hidden = !narrow;
      toggleBtn.setAttribute('aria-expanded', sidebarOpen ? 'true' : 'false');
      toggleBtn.setAttribute('aria-label', (sidebarOpen ? 'Hide ' : 'Show ') + label);
    }
  }

  function focusFirstInSidebar() {
    if (!sidebar) return;
    var activePanel = sidebar.querySelector('.sidebar-panel:not([hidden])');
    if (activePanel) {
      var candidates = activePanel.querySelectorAll(
        'input:not([type="hidden"]), select, textarea, button, a[href], [tabindex]:not([tabindex="-1"])'
      );
      for (var i = 0; i < candidates.length; i++) {
        if (isFocusableVisible(candidates[i])) {
          candidates[i].focus();
          return;
        }
      }
    }
    if (isFocusableVisible(closeBtn)) closeBtn.focus();
  }

  function closeSidebar(options) {
    var restore = !options || options.restoreFocus !== false;
    var forceRestore = !!(options && options.forceRestoreFocus);
    var hadFocus = !!(sidebar && document.activeElement && sidebar.contains(document.activeElement));
    if (!sidebarOpen) {
      updateControls();
      return;
    }
    sidebarOpen = false;
    updateControls();
    if (restore && (hadFocus || forceRestore) && toggleBtn && !toggleBtn.hidden && typeof toggleBtn.focus === 'function') {
      toggleBtn.focus();
    }
  }

  function openSidebar() {
    if (!narrow || !sidebar || sidebar.hidden) return;
    willOpen('sidebar');
    sidebarOpen = true;
    updateControls();
    focusFirstInSidebar();
  }

  function register(id, closeFn) {
    if (!id || typeof closeFn !== 'function') return function () {};
    overlays[id] = closeFn;
    return function () {
      if (overlays[id] === closeFn) delete overlays[id];
    };
  }

  function willOpen(openingId) {
    var keys = Object.keys(overlays);
    for (var i = 0; i < keys.length; i++) {
      var id = keys[i];
      if (id === openingId) continue;
      if (typeof overlays[id] === 'function') overlays[id]();
    }
  }

  function onMediaChange() {
    narrow = !!(mq && mq.matches);
    if (!narrow && sidebarOpen) {
      closeSidebar({ restoreFocus: false });
      return;
    }
    updateControls();
  }

  function mount(options) {
    if (mounted) return;
    mounted = true;

    row = document.querySelector('.app-shell-row');
    sidebar = document.getElementById('app-sidebar');
    main = document.getElementById('main-content');
    toggleBtn = (options && options.toggle) || null;

    if (sidebar) {
      bar = document.createElement('div');
      bar.className = 'narrow-sidebar-bar';
      bar.hidden = true;

      titleEl = document.createElement('span');
      titleEl.className = 'narrow-sidebar-title';
      titleEl.textContent = currentLabel();

      closeBtn = App.ui.button({
        variant: 'ghost',
        size: 'sm',
        label: 'Close',
        ariaLabel: 'Close list',
        testid: 'narrow-sidebar-close',
        onClick: function () {
          closeSidebar({ forceRestoreFocus: true });
        }
      });
      closeBtn.setAttribute('aria-keyshortcuts', 'Escape');

      bar.appendChild(titleEl);
      bar.appendChild(closeBtn);
      sidebar.insertBefore(bar, sidebar.firstChild);

      sidebar.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !e.defaultPrevented && narrow && sidebarOpen && !document.querySelector('dialog[open]')) {
          e.preventDefault();
          e.stopPropagation();
          closeSidebar({ forceRestoreFocus: true });
        }
      });

      sidebar.addEventListener('click', function (e) {
        if (!narrow || !sidebarOpen) return;
        var link = e.target && e.target.closest ? e.target.closest('a[href][aria-current="page"]') : null;
        if (link) closeSidebar();
      });
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && narrow && sidebarOpen && !e.defaultPrevented && !document.querySelector('dialog[open]')) {
        e.preventDefault();
        closeSidebar({ forceRestoreFocus: true });
      }
    });

    if (main) {
      main.addEventListener('click', function () {
        if (narrow && sidebarOpen) closeSidebar();
      });
    }

    if (toggleBtn) {
      toggleBtn.addEventListener('click', function () {
        if (sidebarOpen) closeSidebar({ forceRestoreFocus: true });
        else openSidebar();
      });
    }

    register('sidebar', function () {
      if (!narrow || !sidebarOpen) return;
      closeSidebar({ restoreFocus: false });
    });

    mq = typeof window.matchMedia === 'function' ? window.matchMedia(NARROW_QUERY) : null;
    narrow = !!(mq && mq.matches);
    if (mq) {
      if (typeof mq.addEventListener === 'function') mq.addEventListener('change', onMediaChange);
      else if (typeof mq.addListener === 'function') mq.addListener(onMediaChange);
    }

    if (window.App && App.router && typeof App.router.onCommit === 'function') {
      App.router.onCommit(function (destId) {
        if (destId) currentDest = destId;
        if (sidebarOpen) closeSidebar();
        else updateControls();
      });
    }

    updateControls();
  }

  window.App = window.App || {};
  window.App.narrowShell = {
    mount: mount,
    register: register,
    willOpen: willOpen,
    isNarrow: function () { return narrow; },
    isSidebarOpen: function () { return narrow && sidebarOpen; },
    openSidebar: openSidebar,
    closeSidebar: closeSidebar
  };
})();
