// M10 — topnav render. Extracted from app.js. Owns brand + nav + search
// + avatar markup AND the per-area telemetry chip strip (chip selection
// per spec §2). Subscribes to TelemetryStore for live counts.
//
// Static-template markup: all interpolated values are project-controlled
// constants (AREA_CHIPS keys, CHIP_LABELS values, hardcoded area defs).
// No user input flows into the string template; `insertAdjacentHTML` is
// used in place of `innerHTML =` to match the L1.4 / L2.1 construction
// pattern preferred by the project's security hook for new files.
(function () {
  'use strict';

  // Chip configurations per area. Order matters.
  var AREA_CHIPS = {
    chat:   ['sessions', 'ctx', 'ws'],
    studio: ['agents', 'providers', 'ws'],
    admin:  ['providers', 'tools', 'ws']
  };

  var CHIP_LABELS = {
    sessions: 'SESSIONS',
    agents: 'AGENTS',
    providers: 'PROVIDERS',
    tools: 'TOOLS',
    ctx: 'CTX',
    ws: 'WS'
  };

  function renderChip(key, store) {
    if (key === 'ws') {
      var dotClass = store.ws_state === 'ok' ? 'ok' : 'err';
      var rtt = store.ws_rtt_ms === '—' ? '—' : (store.ws_rtt_ms + 'ms');
      return '<span class="tele-chip" data-chip="ws">' +
        '<span class="stat-dot ' + dotClass + '"></span>' +
        'WS<strong>' + rtt + '</strong></span>';
    }
    return '<span class="tele-chip" data-chip="' + key + '">' +
      CHIP_LABELS[key] + '<strong>' + store[key] + '</strong></span>';
  }

  function buildTopnavHtml(activeArea) {
    var store = window.TelemetryStore.get();
    var chipKeys = AREA_CHIPS[activeArea] || AREA_CHIPS.chat;
    var chipsHtml = chipKeys.map(function (k) { return renderChip(k, store); }).join('');

    var areas = [
      { id: 'chat',   idx: '01', label: 'CHAT' },
      { id: 'studio', idx: '02', label: 'STUDIO' },
      { id: 'admin',  idx: '03', label: 'SYSTEM' }
    ];
    var navHtml = areas.map(function (a) {
      var cls = 'navseg' + (a.id === activeArea ? ' active' : '');
      var ariaCur = a.id === activeArea ? ' aria-current="page"' : '';
      return '<button class="' + cls + '" data-area="' + a.id + '" aria-label="Go to ' + a.label + '"' + ariaCur + '>' +
        '<span class="idx">' + a.idx + '</span>' + a.label +
        '</button>';
    }).join('');

    return '<div class="brand">' +
        '<div class="brand-mark">H</div>' +
        '<div class="brand-name">Holograph</div>' +
      '</div>' +
      '<div class="nav-segments">' + navHtml + '</div>' +
      '<div class="spacer"></div>' +
      '<div class="tele-strip">' + chipsHtml + '</div>' +
      '<div class="search-wrap">' +
        '<label for="topnav-search" class="visually-hidden">Search</label>' +
        '<input type="search" id="topnav-search" class="search-input" placeholder="Search" aria-label="Open search"/>' +
        '<span class="search-kbd">⌘K</span>' +
      '</div>' +
      '<button class="avatar" aria-label="User">JD</button>';
  }

  function renderTopnav(activeArea) {
    var topnav = document.getElementById('app-topnav');
    if (!topnav) return;
    // Replace contents: clear, then insertAdjacentHTML to rebuild.
    while (topnav.firstChild) topnav.removeChild(topnav.firstChild);
    topnav.insertAdjacentHTML('beforeend', buildTopnavHtml(activeArea));
  }

  function bindEvents(onAreaSwitch) {
    var topnav = document.getElementById('app-topnav');
    topnav.addEventListener('click', function (ev) {
      var seg = ev.target.closest('.navseg');
      if (seg && seg.dataset.area) {
        onAreaSwitch(seg.dataset.area);
      }
    });
  }

  function subscribeForRerender() {
    window.TelemetryStore.subscribe(function () {
      var topnav = document.getElementById('app-topnav');
      if (!topnav) return;
      var strip = topnav.querySelector('.tele-strip');
      if (!strip) return;
      var active = topnav.querySelector('.navseg.active');
      var areaId = active ? active.dataset.area : 'chat';
      var chipKeys = AREA_CHIPS[areaId] || AREA_CHIPS.chat;
      var store = window.TelemetryStore.get();
      while (strip.firstChild) strip.removeChild(strip.firstChild);
      strip.insertAdjacentHTML('beforeend',
        chipKeys.map(function (k) { return renderChip(k, store); }).join(''));
    });
  }

  window.Topnav = {
    render: renderTopnav,
    bindEvents: bindEvents,
    subscribeForRerender: subscribeForRerender
  };
})();
