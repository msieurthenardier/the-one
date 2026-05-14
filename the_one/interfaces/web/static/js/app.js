(function () {
  var areas = {};
  var order = [];
  var currentId = null;
  var currentSub = null;
  var initialized = {};

  function registerArea(descriptor) {
    areas[descriptor.id] = descriptor;
    order.push(descriptor);
    order.sort(function (a, b) { return a.order - b.order; });
  }

  function renderTopNav() {
    var topnav = document.getElementById('app-topnav');

    var navlinksHtml = '';
    for (var i = 0; i < order.length; i++) {
      var a = order[i];
      navlinksHtml +=
        '<button class="navlink" data-area="' + a.id + '" aria-label="Go to ' + escapeAttr(a.label) + '">' +
        escapeHtml(a.label) +
        '</button>';
    }

    topnav.innerHTML =
      '<div class="brand">' +
        '<div class="brand-mark">H</div>' +
        '<div class="brand-name">Holograph</div>' +
      '</div>' +
      '<div class="navlinks">' + navlinksHtml + '</div>' +
      '<div class="nav-right">' +
        '<button class="search" aria-label="Open search" aria-keyshortcuts="Control+K Meta+K">' +
          '<svg class="icn" viewBox="0 0 16 16" aria-hidden="true">' +
            '<circle cx="7" cy="7" r="5"/>' +
            '<path d="M14 14l-3-3"/>' +
          '</svg>' +
          '<span>Search</span>' +
          '<span class="kbd">⌘K</span>' +
        '</button>' +
        '<div class="avatar" id="app-user-avatar" aria-label="User">JD</div>' +
      '</div>';

    // Wire navlink clicks to hash navigation.
    var buttons = topnav.querySelectorAll('.navlink');
    for (var j = 0; j < buttons.length; j++) {
      (function (btn) {
        var areaId = btn.dataset.area;
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          location.hash = areaId;
        });
      })(buttons[j]);
    }

    // Wire the search button + ⌘K / Ctrl-K shortcut to the stub toast.
    // (Search itself is non-goal per spec §"Out of scope"; a future flight
    // can wire up a real command palette behind this same affordance.)
    var searchBtn = topnav.querySelector('.search');
    searchBtn.addEventListener('click', function () {
      if (window.App && window.App.toast) {
        window.App.toast('Search coming soon.');
      } else if (console && console.info) {
        console.info('[Holograph] Search coming soon.');
      }
    });

    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        searchBtn.click();
      }
    });
  }

  function parseHash(hashString) {
    var raw = (hashString || '').replace(/^#/, '');
    if (!raw) return { area: null, sub: null };
    var slash = raw.indexOf('/');
    if (slash === -1) return { area: raw, sub: null };
    return { area: raw.slice(0, slash), sub: raw.slice(slash + 1) };
  }

  // Sync the URL hash with the area's serialized state when it diverges
  // (e.g. user navigates to bare `#admin` and admin's default is `general`,
  // so the URL should redirect to `#admin/general`). Called after hydrate
  // in both same-area-sub-change and cross-area paths.
  function syncUrlFromState(areaId, sub) {
    if (typeof areas[areaId].serializeState !== 'function') return;
    var serialized = areas[areaId].serializeState();
    if (serialized && serialized !== sub) {
      history.replaceState(null, '', '#' + areaId + '/' + serialized);
      currentSub = serialized;
    }
  }

  function switchTo(areaId, sub) {
    if (!areas[areaId]) areaId = 'chat';
    sub = (sub === undefined ? null : sub);

    // Same-area sub-change: only hydrate
    if (areaId === currentId && sub === currentSub) return;
    if (areaId === currentId && sub !== currentSub) {
      currentSub = sub;
      if (typeof areas[areaId].hydrateState === 'function') areas[areaId].hydrateState(sub);
      // After hydrate, let the area redirect bare `#admin` → `#admin/general`
      // (or any other default-sub redirect) by syncing URL from serializeState.
      syncUrlFromState(areaId, sub);
      return;
    }

    // Cross-area navigation — optional `confirmLeave` hook on the outgoing
    // area can defer/abort the transition. Used by admin to surface the
    // dirty-editor confirm dialog before navigating away (covers topbar
    // clicks AND browser back/forward AND direct hash typing). Areas
    // without the hook proceed immediately. On abort, the hash is rolled
    // back to the prior area's URL so the address bar stays consistent.
    function performCrossAreaSwitch() {
      if (currentId && areas[currentId]) {
        areas[currentId].deactivate();
      }

      // Hide all content panels (no sidebar in Holograph). The `.active`
      // class is kept for browser-test selectors and aria-bookkeeping, but
      // visibility is enforced directly via inline `display` — no
      // `.content-panel` CSS rule governs visibility, so relying on the
      // class alone left the outgoing area's DOM stacked above the new one.
      var contentPanels = document.querySelectorAll('#main-content .content-panel');
      for (var i = 0; i < contentPanels.length; i++) {
        contentPanels[i].classList.remove('active');
        contentPanels[i].style.display = 'none';
      }

      // Init on first activation
      if (!initialized[areaId]) {
        var contentPanel = document.createElement('div');
        contentPanel.className = 'content-panel area-' + areaId;
        document.getElementById('main-content').appendChild(contentPanel);
        areas[areaId].init(contentPanel);
        initialized[areaId] = true;
      }

      // Show target panel
      var targetContent = document.querySelector('#main-content .area-' + areaId);
      if (targetContent) {
        targetContent.classList.add('active');
        targetContent.style.display = '';
      }

      // Update navlink "you are here" state — toggle .active class for
      // Holograph styling AND aria-current="page" for browser-test selectors
      // (preserved during the L3-L5 selector migration).
      var navlinks = document.querySelectorAll('#app-topnav .navlink');
      for (var k = 0; k < navlinks.length; k++) {
        var isActive = navlinks[k].dataset.area === areaId;
        navlinks[k].classList.toggle('active', isActive);
        if (isActive) navlinks[k].setAttribute('aria-current', 'page');
        else navlinks[k].removeAttribute('aria-current');
      }

      currentId = areaId;
      currentSub = sub;
      // Convention: activate() must refresh the area's data so changes made in
      // other areas (e.g. adding a provider in Admin) are reflected immediately.
      areas[areaId].activate();

      if (typeof areas[areaId].hydrateState === 'function') areas[areaId].hydrateState(sub);

      // If the area retained internal state across navigation (e.g. chat's
      // currentSessionId after a studio side-trip), or has a default sub-state
      // (admin's `general`), sync the URL hash from serializeState so the
      // address bar reflects what's actually shown.
      syncUrlFromState(areaId, sub);
    }

    // confirmLeave gate. Hook contract:
    //   confirmLeave(proceed: () => void, abort: () => void): void
    //   - Called BEFORE deactivating the outgoing area on cross-area
    //     navigation. Clean: call proceed() immediately. Dirty: open
    //     a confirm dialog; on user-confirm call proceed(), on user-
    //     cancel call abort() (the gate restores the prior URL).
    // Areas without the hook fall through to performCrossAreaSwitch().
    if (currentId && areas[currentId] && typeof areas[currentId].confirmLeave === 'function') {
      var priorHash = '#' + currentId + (currentSub ? '/' + currentSub : '');
      areas[currentId].confirmLeave(
        performCrossAreaSwitch,
        function () {
          // Roll back the URL. The triggering action (topbar click /
          // browser back / hash typing) has already mutated location.hash;
          // replaceState rewrites the current entry without firing
          // hashchange (so we don't loop back into switchTo).
          if (location.hash !== priorHash) {
            history.replaceState(null, '', priorHash);
          }
        }
      );
    } else {
      performCrossAreaSwitch();
    }
  }

  window.addEventListener('hashchange', function () {
    var parsed = parseHash(location.hash);
    if (!parsed.area || !areas[parsed.area]) return; // skip-link / unknown area
    switchTo(parsed.area, parsed.sub);
  });

  document.addEventListener('DOMContentLoaded', function () {
    renderTopNav();
    // M10 — body-level instrument frame (corner ticks); the grid canvas
    // itself lives on #main-content via components.css.
    if (!document.querySelector('.canvas-frame')) {
      var frame = document.createElement('div');
      frame.className = 'canvas-frame';
      frame.setAttribute('aria-hidden', 'true');
      // Two extra spans for top-right + bottom-left ticks (the ::before/::after
      // pseudos cover top-left + bottom-right).
      var tr = document.createElement('span');
      tr.className = 'tr';
      var bl = document.createElement('span');
      bl.className = 'bl';
      frame.appendChild(tr);
      frame.appendChild(bl);
      document.body.appendChild(frame);
    }
    // Boot-block on /api/config so window.App.config is populated before
    // any area.init() runs. Areas read App.config.dev_mode in their init
    // closures (e.g. admin's sidebar categories list).
    fetch('/api/config')
      .then(function (r) { return r.json(); })
      .then(function (config) {
        // Defensive default: a malformed 200 (null body, truncated JSON
        // that parses to a non-object) won't crash downstream readers.
        window.App.config = (config && typeof config === 'object')
          ? config
          : { dev_mode: false, version: 'unknown' };
      })
      .catch(function () {
        // Failed fetch must not break boot. Defaults to non-dev,
        // unknown-version so dev-mode-gated features stay off.
        window.App.config = { dev_mode: false, version: 'unknown' };
      })
      .then(function () {
        var parsed = parseHash(location.hash);
        var area = (parsed.area && areas[parsed.area]) ? parsed.area : 'chat';
        switchTo(area, parsed.sub);
      });
  });

  function escapeHtml(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function escapeAttr(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = 0;
    var val = bytes;
    while (val >= 1024 && i < units.length - 1) { val /= 1024; i++; }
    return (i >= 2 ? val.toFixed(1) : Math.round(val)) + ' ' + units[i];
  }

  function showFlash(container, msg, isError) {
    var el = document.createElement('div');
    el.className = 'app-flash' + (isError ? ' error' : '');
    if (isError) {
      el.setAttribute('role', 'alert');
    } else {
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
    }
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(function () { el.classList.add('visible'); }, 10);
    setTimeout(function () {
      el.classList.remove('visible');
      setTimeout(function () { el.remove(); }, 300);
    }, 2000);
  }

  function toast(msg, opts) {
    opts = opts || {};
    var existing = document.querySelector('.app-toast');
    if (existing) existing.remove();
    var el = document.createElement('div');
    el.className = 'app-toast';
    el.textContent = msg;
    el.setAttribute('role', 'status');
    document.body.appendChild(el);
    var duration = opts.duration || 2400;
    setTimeout(function () { el.classList.add('app-toast-out'); }, duration);
    setTimeout(function () { el.remove(); }, duration + 320);
  }

  window.App = window.App || {};
  Object.assign(window.App, {
    registerArea: registerArea,
    // F6.6 L0: export the area registry as an ARRAY (the closure-private
    // ``order`` list, not the dict ``areas``) so consumers can use
    // ``Array.prototype.find`` semantics. The chat-area browser-test helper
    // at ``tests/browser/test_oauth_modal_flow.py:42`` calls
    // ``window.App.areas.find(a => a.id === 'chat')`` — ``.find()`` is
    // ``Array.prototype``, NOT a method on plain objects, so a dict export
    // (``areas: areas``) would mechanically fail. See flight log
    // ``Deviations`` for the rationale.
    areas: order,
    router: {
      parseHash: parseHash,
      /**
       * Update the URL sub-state without pushing history. Used by area code when
       * the user navigates within an area (selects a different session/agent/category).
       * The area is implicit (currentId) — only the sub portion is updated.
       * Calling this does NOT fire hashchange (replaceState is silent), so it does
       * not loop back through switchTo.
       */
      replaceSub: function (sub) {
        if (!currentId) return;
        var newHash = sub ? '#' + currentId + '/' + sub : '#' + currentId;
        if (location.hash === newHash) return; // no-op
        history.replaceState(null, '', newHash);
      },
    },
    escapeHtml: escapeHtml,
    escapeAttr: escapeAttr,
    formatBytes: formatBytes,
    showFlash: showFlash,
    toast: toast,
  });
})();
