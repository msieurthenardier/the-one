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

  // Pending-approval badge poller — M11 F17 L9 (Leg E).
  // Polls /api/connectors/peer-approvals/pending-count every 10s and
  // updates the badge on the Chat nav button. Hidden at count=0.
  // Robust: errors are swallowed; interval is stored so callers can clear it.
  var _pendingBadgeInterval = null;

  function _updatePendingBadge(count) {
    var badge = document.querySelector('[data-testid="nav-pending-badge"]');
    if (!badge) return;
    badge.textContent = count > 0 ? String(count) : '';
    badge.style.display = count > 0 ? '' : 'none';
  }

  function _pollPendingCount() {
    fetch('/api/connectors/peer-approvals/pending-count')
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && typeof data.count === 'number') _updatePendingBadge(data.count);
      })
      .catch(function () { /* swallow — badge stays at last known value */ });
  }

  function _startPendingBadgePoll() {
    _pollPendingCount(); // immediate first fetch
    _pendingBadgeInterval = setInterval(_pollPendingCount, 10000);
  }

  function renderTopBar() {
    var topbar = document.getElementById('app-topbar');
    // Build the area buttons by iterating registered areas in declared order.
    // Each area becomes a flat top-bar button — direct-navigate, no popover.
    // Active state is set in switchTo() via aria-current="page".
    var buttonsHtml = '';
    for (var i = 0; i < order.length; i++) {
      var a = order[i];
      // The Chat button gets a testid and a pending-approval badge child
      // (M11 F17 L9 — Leg E). Badge is hidden via display:none when count=0.
      var extraAttrs = a.id === 'chat'
        ? ' data-testid="nav-chat-btn"'
        : '';
      var badgeHtml = a.id === 'chat'
        ? '<span class="nav-pending-badge" data-testid="nav-pending-badge" style="display:none" aria-label="pending approvals"></span>'
        : '';
      buttonsHtml +=
        '<button class="app-picker-button" data-area="' + a.id + '" aria-label="Go to ' + a.label + '"' + extraAttrs + '>' +
          '<span class="app-picker-button-icon">' + (a.icon || '') + '</span>' +
          '<span class="app-picker-button-label">' + a.label + '</span>' +
          badgeHtml +
        '</button>';
    }

    // Brand lockup (M17 F3): set-type wordmark + compact mark. The <img>
    // mark is decorative (aria-hidden, empty alt); the text carries the
    // accessible name.
    topbar.innerHTML =
      '<div class="app-brand">' +
        '<img src="/static/brand/topbar-icon-24.png" alt="" aria-hidden="true" class="app-brand-mark">' +
        '<span class="app-brand-wordmark">GleepGlorp AI</span>' +
      '</div>' +
      '<div class="app-topbar-actions">' + buttonsHtml + '</div>';

    // Wire each button to a direct hash navigation.
    var buttons = topbar.querySelectorAll('.app-picker-button');
    for (var j = 0; j < buttons.length; j++) {
      (function (btn) {
        var areaId = btn.dataset.area;
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          location.hash = areaId;
        });
      })(buttons[j]);
    }
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
      App.perf.mark('area-switch:start');
      if (currentId && areas[currentId]) {
        areas[currentId].deactivate();
      }
      App.perf.mark('area-switch:deactivated');
      App.perf.measure('area-switch.deactivate', 'area-switch:start', 'area-switch:deactivated');

    // Hide all panels
    var sidebarPanels = document.querySelectorAll('#app-sidebar .sidebar-panel');
    var contentPanels = document.querySelectorAll('#main-content .content-panel');
    for (var i = 0; i < sidebarPanels.length; i++) sidebarPanels[i].classList.remove('active');
    for (var i = 0; i < contentPanels.length; i++) contentPanels[i].classList.remove('active');

    // Init on first activation
    if (!initialized[areaId]) {
      var sidebarPanel = document.createElement('div');
      sidebarPanel.className = 'sidebar-panel area-' + areaId;
      document.getElementById('app-sidebar').appendChild(sidebarPanel);

      var contentPanel = document.createElement('div');
      contentPanel.className = 'content-panel area-' + areaId;
      document.getElementById('main-content').appendChild(contentPanel);

      areas[areaId].init(sidebarPanel, contentPanel);
      initialized[areaId] = true;
    }

    // Show target panels
    var targetSidebar = document.querySelector('#app-sidebar .area-' + areaId);
    var targetContent = document.querySelector('#main-content .area-' + areaId);
    if (targetSidebar) targetSidebar.classList.add('active');
    if (targetContent) targetContent.classList.add('active');

    // Set aside aria-label for the active area
    var asideEl = document.getElementById('app-sidebar');
    var areaLabel = areas[areaId].sidebarLabel || (areas[areaId].label + ' sidebar');
    asideEl.setAttribute('aria-label', areaLabel);

    // Update top-bar button "you are here" state — each flat button gets
    // aria-current="page" when its area is active, removed otherwise.
    var topbarBtns = document.querySelectorAll('#app-topbar .app-picker-button');
    for (var i = 0; i < topbarBtns.length; i++) {
      if (topbarBtns[i].dataset.area === areaId) topbarBtns[i].setAttribute('aria-current', 'page');
      else topbarBtns[i].removeAttribute('aria-current');
    }

    App.perf.mark('area-switch:activated');
    App.perf.measure('area-switch.full', 'area-switch:start', 'area-switch:activated');

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
    renderTopBar();
    _startPendingBadgePoll();
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

  // Fail-closed URL-scheme allow-list for values that land in a live `href`/
  // `src` attribute and originate from an untrusted third party (e.g. an MCP
  // server's `initialize()` response — `serverInfo.websiteUrl`, `icons[].src`).
  // Mirrors the anchoring/obfuscation-defeat shape of markdown.js's
  // `safeHref()` (M17 F4 L1 hardening decision) but is narrower: only
  // `http:`/`https:` are allowed (no `mailto:`/`tel:`/relative/fragment —
  // those markdown affordances don't apply to a server-supplied website link
  // or icon). Returns the URL unchanged when it passes, or `null` when it
  // doesn't — callers must drop the attribute/element entirely, never fall
  // back to a placeholder href that still renders as a live link.
  function safeUrl(url) {
    if (!url || typeof url !== 'string') return null;
    // Protocol-relative URLs (`//host/...`) inherit the page's scheme and
    // resolve OFF-SITE; reject before the scheme check so they don't need a
    // separate carve-out. Leading-whitespace variants are already rejected
    // below by the anchored match, but checked here too for clarity/parity
    // with safeHref's ordering.
    if (/^\s*\/\//.test(url)) return null;
    // Anchored `^` with no leading `\s` — any leading junk (whitespace, tab,
    // newline, control chars) defeats the match, same fail-closed posture as
    // safeHref. Case-insensitive so `JavaScript:`/`HTTP:` obfuscation can't
    // sneak past either side.
    return /^https?:/i.test(url) ? url : null;
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
    // F2 Leg 2 (A.5): extend auto-dismiss from 2s to 5s. role=alert/
    // role=status already handles SR announcement immediately, but the
    // visual dwell time was below WCAG 2.2.1's minimum-for-reading
    // threshold. 5s covers typical English reading speed for the short
    // status strings we emit (≈8-12 words).
    setTimeout(function () {
      el.classList.remove('visible');
      setTimeout(function () { el.remove(); }, 300);
    }, 5000);
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
    safeUrl: safeUrl,
    formatBytes: formatBytes,
    showFlash: showFlash,
  });
})();
