(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Renders the LLM Providers page-header + tile grid.
  //
  // Tile DOM (L5.5 — Holograph populated card):
  //   <button class="provider-card entity-tile provider-tile"
  //           data-testid="provider-card"
  //           data-id="{provider.id}"
  //           aria-selected="{true|false}">
  //     <div class="provider-card-head">
  //       <div class="provider-type-cat entity-tile-badge admin-provider-badge admin-provider-badge--{type}">{type}</div>
  //       <div class="provider-card-status">
  //         <span class="stat-dot {ok|err|idle}"></span>{READY|ERROR|UNTESTED}
  //       </div>
  //     </div>
  //     <div class="provider-card-name entity-tile-name">{name}</div>
  //     <div class="provider-card-meta entity-tile-meta">LAST USED · {relative|NEVER}</div>
  //   </button>
  //
  // The active tile (when an editor is open for that id) carries
  // aria-selected="true"; others carry aria-selected="false".
  //
  // The badge slot composes `provider-type-cat` (new Holograph mono category
  // styling, uppercase via CSS text-transform) with `entity-tile-badge`
  // (selector continuity for browser tests + the legacy admin-provider-badge
  // per-type colour rules). Status / last-used rely on the optional
  // last_test_ok / last_used_at fields; absent fields collapse to UNTESTED /
  // never with no breakage.

  var KNOWN_BADGE_TYPES = ['ollama', 'openai-compatible', 'openai', 'anthropic', 'mock', 'openrouter'];

  function formatRelative(iso) {
    if (!iso) return null;
    var t = new Date(iso).getTime();
    if (!isFinite(t)) return null;
    var ms = Date.now() - t;
    if (ms < 0) ms = 0;
    var min = Math.floor(ms / 60000);
    if (min < 1) return 'just now';
    if (min < 60) return min + 'm ago';
    var hr = Math.floor(min / 60);
    if (hr < 24) return hr + 'h ago';
    return Math.floor(hr / 24) + 'd ago';
  }

  function statusFor(p) {
    if (p.last_test_ok === true) return { cls: 'ok', label: 'READY' };
    if (p.last_test_ok === false) return { cls: 'err', label: 'ERROR' };
    return { cls: 'idle', label: 'UNTESTED' };
  }

  function renderProviderCard(p, isActive) {
    var typeSuffix = KNOWN_BADGE_TYPES.indexOf(p.type) >= 0 ? p.type : 'unknown';
    var status = statusFor(p);
    var relative = formatRelative(p.last_used_at);
    var lastUsedText = 'LAST USED · ' + (relative ? relative.toUpperCase() : 'NEVER');

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'provider-card entity-tile provider-tile';
    btn.setAttribute('role', 'option');
    btn.setAttribute('data-testid', 'provider-card');
    btn.setAttribute('data-id', p.id);
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    if (isActive) btn.classList.add('selected');

    var head = document.createElement('div');
    head.className = 'provider-card-head';

    // Category / type badge — composes provider-type-cat (mono uppercase)
    // with entity-tile-badge + admin-provider-badge--{type} (color rules +
    // selector continuity for existing browser tests).
    var cat = document.createElement('span');
    cat.className =
      'provider-type-cat entity-tile-badge admin-provider-badge admin-provider-badge--' + typeSuffix;
    cat.textContent = p.type;
    head.appendChild(cat);

    var statusEl = document.createElement('div');
    statusEl.className = 'provider-card-status';
    var dot = document.createElement('span');
    dot.className = 'stat-dot ' + status.cls;
    statusEl.appendChild(dot);
    statusEl.appendChild(document.createTextNode(status.label));
    head.appendChild(statusEl);

    btn.appendChild(head);

    var nameEl = document.createElement('div');
    nameEl.className = 'provider-card-name entity-tile-name';
    nameEl.textContent = p.name;
    btn.appendChild(nameEl);

    var metaEl = document.createElement('div');
    metaEl.className = 'provider-card-meta entity-tile-meta';
    metaEl.textContent = lastUsedText;
    btn.appendChild(metaEl);

    return btn;
  }

  // L4.4 — provider-type card definitions for the empty-state 4-card grid.
  // Anthropic is RECOMMENDED (accent border + accent eyebrow); the other
  // three carry their category label (CLOUD / CLOUD / LOCAL) in muted mono.
  // Clicking a card opens the existing provider-editor pre-targeted to that
  // type via onCreateProvider(type).
  var PROVIDER_TYPE_CARDS = [
    { id: 'anthropic',         name: 'Anthropic',         cat: 'RECOMMENDED', desc: 'Claude family · API key', recommended: true },
    { id: 'openai',            name: 'OpenAI',            cat: 'CLOUD',       desc: 'GPT family · API key',    recommended: false },
    { id: 'openai-compatible', name: 'OpenAI-compatible', cat: 'CLOUD',       desc: 'Together, Groq, etc.',    recommended: false },
    { id: 'ollama',            name: 'Ollama',            cat: 'LOCAL',       desc: 'Self-hosted · no key',    recommended: false }
  ];

  // Builds the 4-card provider-type grid into `gridEl` (replaces any existing
  // children). Each card invokes `onPickType(type)` on click. Built via
  // createElement / textContent (security hook bans innerHTML for dynamic
  // strings; labels here are literal but we keep the pattern uniform).
  function renderProvidersEmpty(gridEl, onPickType) {
    while (gridEl.firstChild) gridEl.removeChild(gridEl.firstChild);
    var typeGrid = document.createElement('div');
    typeGrid.className = 'provider-type-grid';
    typeGrid.setAttribute('data-testid', 'provider-type-grid');

    for (var i = 0; i < PROVIDER_TYPE_CARDS.length; i++) {
      var c = PROVIDER_TYPE_CARDS[i];
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'provider-type-card' + (c.recommended ? ' recommended' : '');
      btn.dataset.testid = 'provider-type-card';
      btn.dataset.providerType = c.id;
      btn.setAttribute('aria-label', 'Create ' + c.name + ' provider');

      var cat = document.createElement('div');
      cat.className = 'provider-type-cat';
      cat.textContent = c.cat;
      btn.appendChild(cat);

      var nm = document.createElement('div');
      nm.className = 'provider-type-name';
      nm.textContent = c.name;
      btn.appendChild(nm);

      var ds = document.createElement('div');
      ds.className = 'provider-type-desc';
      ds.textContent = c.desc;
      btn.appendChild(ds);

      (function (cardEl) {
        cardEl.addEventListener('click', function () {
          onPickType(cardEl.dataset.providerType);
        });
      })(btn);

      typeGrid.appendChild(btn);
    }
    gridEl.appendChild(typeGrid);
  }

  function renderProvidersGrid(container, providers, callbacks) {
    callbacks = callbacks || {};
    var onSelectProvider = callbacks.onSelectProvider || function () {};
    var onCreateProvider = callbacks.onCreateProvider || function () {};
    var selectedId = callbacks.selectedId || null;

    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">LLM Providers</h1>' +
        // Header CTA renders icon-only at rest; expands on hover. CSS hides
        // it entirely when the grid below is empty, deferring the affordance
        // to the empty-canvas's centered CTA.
        '<button class="new-entity-btn" type="button" data-testid="new-provider-btn" aria-label="New provider">' +
          window.App.icon('square-pen') + '<span>New Provider</span>' +
        '</button>' +
      '</div>' +
      '<div class="entity-tile-grid" role="listbox" aria-label="LLM providers">' +
        '<div class="admin-loading">Loading providers…</div>' +
      '</div>';

    var newProviderBtn = container.querySelector('.new-entity-btn');
    newProviderBtn.addEventListener('click', function () { onCreateProvider(); });

    var gridEl = container.querySelector('.entity-tile-grid');
    if (providers === null || providers === undefined) {
      // Loading state — caller will re-invoke with populated array
      return;
    }

    if (providers.length === 0) {
      // L4.4 — 4-card provider-type grid replaces the old "No providers
      // configured…" canvas. Each card preselects its type in the editor.
      renderProvidersEmpty(gridEl, function (type) { onCreateProvider(type); });
      return;
    }

    // L5.5 — populated grid renders the new Holograph provider-card layout
    // (mono category badge + status dot + name + LAST USED meta) via
    // createElement / textContent. Each card preserves the legacy
    // entity-tile-name / entity-tile-badge / entity-tile-meta classes for
    // browser-test selector continuity.
    while (gridEl.firstChild) gridEl.removeChild(gridEl.firstChild);
    for (var i = 0; i < providers.length; i++) {
      var p = providers[i];
      var isActive = selectedId === p.id;
      var card = renderProviderCard(p, isActive);
      (function (cardEl) {
        cardEl.addEventListener('click', function () {
          var id = cardEl.dataset.id;
          if (id) onSelectProvider(id);
        });
      })(card);
      gridEl.appendChild(card);
    }
  }

  window.App.admin.renderProvidersGrid = renderProvidersGrid;
})();
