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
  //
  // The rail's footer (M25 F4 L7, DD9) holds the Jump to control, built here
  // BEFORE App.ui.rail() and passed as its `footer`; onCommit never touches
  // it. Its click opens the palette (App.jumpTo, jump-to.js) with the control
  // as the opener; App.jumpTo is looked up at click time.
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
    var keys = jumpToKeys(isMacPlatform());
    var jumpTo = App.ui.button({
      variant: 'ghost',
      icon: 'search',
      iconOnly: true,
      ariaLabel: 'Jump to (' + keys.hint + ')',
      testid: 'rail-jump-to',
      onClick: function () {
        if (App.jumpTo && typeof App.jumpTo.open === 'function') App.jumpTo.open(jumpTo);
      }
    });
    jumpTo.setAttribute('aria-keyshortcuts', keys.aria);
    var rail = App.ui.rail({
      items: items,
      brand: { src: '/static/brand/topbar-icon-24.png', alt: 'GleepGlorp AI' },
      footer: [jumpTo]
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

  // ── Ctrl K: the jump-to shortcut (M25 F4 L7, flight DD9) ────────────────
  //
  // isMacPlatform(nav): pure (nav defaults to window.navigator). The platform
  // from navigator.userAgentData.platform, else navigator.platform, matched
  // against /mac|iphone|ipad/i.
  function isMacPlatform(nav) {
    if (nav === undefined) nav = window.navigator;
    if (!nav) return false;
    var platform = '';
    if (nav.userAgentData && nav.userAgentData.platform) platform = nav.userAgentData.platform;
    else if (nav.platform) platform = nav.platform;
    return /mac|iphone|ipad/i.test(String(platform));
  }

  // isJumpToKey(e, mac): pure. On macOS only Meta+K (Ctrl+K is kill-line in
  // Cocoa text fields); elsewhere only Ctrl+K without Meta. Never with Shift
  // or Alt. The key matches by `key` (any case: Caps Lock) or by `code`
  // (KeyK: a non-Latin layout).
  function isJumpToKey(e, mac) {
    if (!e || e.shiftKey || e.altKey) return false;
    if (mac ? !(e.metaKey && !e.ctrlKey) : !(e.ctrlKey && !e.metaKey)) return false;
    var key = typeof e.key === 'string' ? e.key.toLowerCase() : '';
    return key === 'k' || e.code === 'KeyK';
  }

  // jumpToKeys(mac): the shortcut's copy -- `hint` for visible text and the
  // accessible name ("Ctrl K" / "⌘ K"), `aria` for aria-keyshortcuts.
  function jumpToKeys(mac) {
    return mac ? { hint: '\u2318 K', aria: 'Meta+K' } : { hint: 'Ctrl K', aria: 'Control+K' };
  }

  // The ONE shell-level keydown listener for Ctrl K, on document (library
  // factories may not install document listeners: Flight 1 DD1). Installed
  // once per boot, beside the rail mount. app.js loads before the ui/
  // factories and jump-to.js, so App.ui.modal and App.jumpTo are looked up
  // at keydown. It works from inside inputs and textareas (Ctrl K is no
  // text-editing key on Windows or Linux; macOS takes Meta K) and calls
  // preventDefault on every match (the browser's own Ctrl K never runs over
  // the app). Then:
  //   - an IME composition (isComposing, keyCode 229): ignored;
  //   - the palette open: focus its input;
  //   - any other modal open (App.ui.modal.anyOpen(): the leave-guard confirm,
  //     the agent picker): nothing, so the topmost-modal rule holds;
  //   - else: open the palette with the focused element as its opener.
  function onJumpToKeydown(e) {
    if (e.isComposing || e.keyCode === 229) return;
    if (!isJumpToKey(e, isMacPlatform())) return;
    e.preventDefault();
    var palette = App.jumpTo;
    if (!palette || typeof palette.open !== 'function') return;
    if (palette.isOpen()) {
      palette.focusInput();
      return;
    }
    var modal = App.ui && App.ui.modal;
    if (modal && typeof modal.anyOpen === 'function' && modal.anyOpen()) return;
    palette.open(document.activeElement);
  }

  var jumpToKeyInstalled = false;
  function installJumpToKey() {
    if (jumpToKeyInstalled) return;
    jumpToKeyInstalled = true;
    document.addEventListener('keydown', onJumpToKeydown);
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
    installJumpToKey();
    // Boot-block on /api/config so window.App.config is populated before
    // any area.init() runs. Areas read App.config.dev_mode in their init
    // closures (e.g. settings' category list).
    // The operator's time zone loads in parallel with /api/config and gates the router
    // for at most 2 seconds (M28 F2 L1): the chain never rejects (r.ok check plus its own
    // catch), a failure leaves the zone unset (browser-local), and a late response still
    // applies through setZone, which re-renders subscribers.
    var settingsChain = fetch('/api/time-settings')
      .then(function (r) {
        if (!r.ok) throw new Error('time-settings ' + r.status);
        return r.json();
      })
      .then(function (s) { App.time.applySettings(s); })
      .catch(function () { /* keep the browser-local zone */ });
    var bootTimer = null;
    var settingsOrTimeout = Promise.race([
      settingsChain.then(function () { if (bootTimer !== null) clearTimeout(bootTimer); }),
      new Promise(function (resolve) { bootTimer = setTimeout(resolve, 2000); })
    ]);
    var configChain = fetch('/api/config')
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
      });
    Promise.all([configChain, settingsOrTimeout])
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

  // Decimal units (1 GB = 1e9 B), so the label matches the maths and the sizes
  // agree with ollama.com and `ollama pull`.
  function formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    var units = ['B', 'KB', 'MB', 'GB', 'TB'];
    var i = 0;
    var val = bytes;
    while (val >= 1000 && i < units.length - 1) { val /= 1000; i++; }
    return (i >= 2 ? val.toFixed(1) : Math.round(val)) + ' ' + units[i];
  }

  // App.ui.flash owns the markup, roles and timing; this keeps the old signature.
  function showFlash(container, msg, isError) {
    App.ui.flash(msg, { error: !!isError, container: container || document.body });
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
    // The Ctrl K shortcut's pure helpers (M25 F4 L7, DD9): the platform
    // detector, the key matcher and the platform-aware copy, shared with the
    // jump-to palette's footer and unit-tested in the browser.
    shortcuts: {
      isMacPlatform: isMacPlatform,
      isJumpToKey: isJumpToKey,
      jumpToKeys: jumpToKeys
    },
  });
})();
