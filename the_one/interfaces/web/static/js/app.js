(function () {
  var areas = {};
  var order = [];
  var currentId = null;
  var initialized = {};

  function registerArea(descriptor) {
    areas[descriptor.id] = descriptor;
    order.push(descriptor);
    order.sort(function (a, b) { return a.order - b.order; });
  }

  // The workbench rail (M25 F2 L6): App.ui.rail mounted in #app-rail. The
  // rail is plain <a href> links with no click handler: guarded navigation,
  // modifier-click passthrough and restore all ride on App.nav's link
  // interceptor. This keeps it in sync with the router on every commit: the
  // current destination links to its root (clicking it resets to the root),
  // every other destination to its last route (clicking it restores the item
  // the user left). First-boot hrefs need no special case: lastRoute() falls
  // back to the destination root.
  function mountRail() {
    var host = document.getElementById('app-rail');
    var dests = App.router.destinations;
    var items = [];
    for (var i = 0; i < dests.length; i++) {
      items.push({
        id: dests[i].id,
        label: dests[i].label,
        icon: dests[i].iconKey,
        href: '#' + App.router.lastRoute(dests[i].id),
        testid: 'rail-' + dests[i].id
      });
    }
    var rail = App.ui.rail({
      items: items,
      brand: { src: '/static/brand/topbar-icon-24.png', alt: 'GleepGlorp AI' }
    });
    host.textContent = '';
    host.appendChild(rail.el);
    App.router.onCommit(function (destId) {
      rail.setCurrent(destId);
      for (var k = 0; k < dests.length; k++) {
        var route = dests[k].id === destId ? App.router.root(destId) : App.router.lastRoute(dests[k].id);
        rail.setHref(dests[k].id, '#' + route);
      }
    });
  }

  // mountArea: the panel lifecycle only (commit-sequence step 6). The router
  // decides WHAT to show; this makes the area module's panels the active ones.
  // The module deactivates/activates only when the area module CHANGES, so
  // Agents <-> Library (both studio) never re-activates it. The active content
  // panel carries data-destination="<id>" (inactive panels have it removed),
  // which is also the browser tests' readiness probe.
  function mountArea(areaId, destinationId) {
    var contentPanels = document.querySelectorAll('#main-content .content-panel');
    if (areaId !== currentId) {
      App.perf.mark('area-switch:start');
      if (currentId && areas[currentId]) {
        areas[currentId].deactivate();
      }
      App.perf.mark('area-switch:deactivated');
      App.perf.measure('area-switch.deactivate', 'area-switch:start', 'area-switch:deactivated');

      // Hide all panels
      var sidebarPanels = document.querySelectorAll('#app-sidebar .sidebar-panel');
      var i;
      for (i = 0; i < sidebarPanels.length; i++) sidebarPanels[i].classList.remove('active');
      for (i = 0; i < contentPanels.length; i++) contentPanels[i].classList.remove('active');

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
    }

    contentPanels = document.querySelectorAll('#main-content .content-panel');
    for (var j = 0; j < contentPanels.length; j++) {
      if (contentPanels[j].classList.contains('active')) {
        contentPanels[j].setAttribute('data-destination', destinationId);
      } else {
        contentPanels[j].removeAttribute('data-destination');
      }
    }

    if (areaId !== currentId) {
      App.perf.mark('area-switch:activated');
      App.perf.measure('area-switch.full', 'area-switch:start', 'area-switch:activated');
      currentId = areaId;
      // Convention: activate() must refresh the area's data so changes made in
      // other areas (e.g. adding a provider in Settings) are reflected immediately.
      areas[areaId].activate();
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    mountRail();
    // Boot-block on /api/config so window.App.config is populated before
    // any area.init() runs. Areas read App.config.dev_mode in their init
    // closures (e.g. settings' category list).
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
        App.router.start({
          mountArea: mountArea,
          getArea: function (id) { return areas[id] || null; }
        });
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
    escapeHtml: escapeHtml,
    escapeAttr: escapeAttr,
    safeUrl: safeUrl,
    formatBytes: formatBytes,
    showFlash: showFlash,
  });
})();
