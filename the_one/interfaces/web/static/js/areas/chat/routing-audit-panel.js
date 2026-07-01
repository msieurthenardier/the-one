(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};
  window.App.chat.routingAuditPanel = window.App.chat.routingAuditPanel || {};

  // Stable display order for the "raw fields" expansion section.
  var EXPANSION_KEY_ORDER = [
    'disposition', 'ts', 'agent', 'scope', 'rule_index',
    'match', 'reason', 'intercept_source', 'policy'
  ];

  // Stable display order for the nested policy dict.
  var POLICY_KEY_ORDER = [
    'outcome',
    'inference_provider_id', 'inference_model',
    'account_always_listen', 'agent_always_listen'
  ];

  // F09-06: singleton reference to the currently-open overlay session so
  // ESC / focus-restore / one-at-a-time invariants have a single source of
  // truth. Holds { overlay, trigger } while open; null while closed.
  var _active = null;

  // Build the compact header trigger. Lives right-justified in the chat
  // header row; clicking it opens the audit overlay. chat.js wires the
  // click handler (so it can pass the paired overlay + trigger for focus
  // restore). Returns the <button>.
  function createTrigger() {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'routing-audit-trigger';
    btn.setAttribute('data-testid', 'routing-audit-trigger');
    btn.setAttribute('aria-haspopup', 'dialog');
    btn.textContent = 'Routing audit';
    return btn;
  }

  // Build the audit overlay — a centered, reasonably-sized modal (reusing the
  // .modal-overlay / .modal-dialog glass styling from components.css) holding
  // a title, the Refresh control, a ✕ close button, and the routing entries
  // body. Mounted hidden by chat.js; open()/close() toggle visibility. The
  // close ✕ and backdrop-click handlers are wired here (once); ESC + focus
  // trap are wired per-open in open(). Returns the outer .modal-overlay.
  function createOverlay() {
    var overlay = document.createElement('div');
    overlay.className = 'modal-overlay routing-audit-overlay';
    overlay.setAttribute('data-testid', 'routing-audit-overlay');
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'routing-audit-title');
    overlay.hidden = true;

    var dlg = document.createElement('div');
    dlg.className = 'modal-dialog routing-audit-modal';
    overlay.appendChild(dlg);

    var header = document.createElement('div');
    header.className = 'routing-audit-modal-header';

    var title = document.createElement('h2');
    title.className = 'modal-dialog-title';
    title.id = 'routing-audit-title';
    title.textContent = 'Routing audit';
    header.appendChild(title);

    var refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'btn-muted routing-audit-refresh';
    refreshBtn.textContent = 'Refresh';
    refreshBtn.setAttribute('data-testid', 'routing-audit-refresh');
    header.appendChild(refreshBtn);

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'routing-audit-close';
    closeBtn.setAttribute('data-testid', 'routing-audit-close');
    closeBtn.setAttribute('aria-label', 'Close routing audit');
    closeBtn.innerHTML = (window.App && App.icon) ? App.icon('x') : '✕';
    header.appendChild(closeBtn);

    dlg.appendChild(header);

    var body = document.createElement('div');
    body.className = 'routing-audit-body';
    body.setAttribute('data-testid', 'routing-audit-body');
    dlg.appendChild(body);

    // Close affordances wired once (idempotent — reference module-level close).
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', function (e) {
      // Backdrop click only — a click on the dialog itself must not dismiss.
      if (e.target === overlay) close();
    });

    return overlay;
  }

  // Focusable descendants of the dialog (for focus-into-open + Tab trap).
  function _focusables(overlay) {
    var dlg = overlay.querySelector('.modal-dialog');
    if (!dlg) return [];
    var sel = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    var nodes = dlg.querySelectorAll(sel);
    return Array.prototype.slice.call(nodes).filter(function (n) {
      return !n.disabled && n.offsetParent !== null;
    });
  }

  // Capture-phase key handler while an overlay is open: ESC closes; Tab wraps
  // focus inside the dialog.
  function _onKey(e) {
    if (!_active) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      return;
    }
    if (e.key === 'Tab') {
      var fs = _focusables(_active.overlay);
      if (fs.length === 0) { e.preventDefault(); return; }
      var first = fs[0];
      var last = fs[fs.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // Open the overlay: append it to <body> (so its fixed-position backdrop
  // covers the full viewport and stacks above the sidebar/topbar — mirrors the
  // App.confirmDialog mount pattern), reveal it, capture the trigger for
  // focus-restore, wire ESC + focus-trap, and move focus into the dialog.
  // Singleton — a second open() while one is showing is a no-op for the same
  // overlay; a different overlay first closes the active one.
  function open(overlay, trigger) {
    if (!overlay) return;
    if (_active) {
      if (_active.overlay === overlay) return;
      close();
    }
    if (overlay.parentNode !== document.body) document.body.appendChild(overlay);
    overlay.hidden = false;
    _active = { overlay: overlay, trigger: trigger || document.activeElement };
    document.addEventListener('keydown', _onKey, true);
    var fs = _focusables(overlay);
    var target = fs[0] || overlay.querySelector('.modal-dialog');
    if (target && typeof target.focus === 'function') {
      try { target.focus(); } catch (e) { /* ignore */ }
    }
  }

  // Close the active overlay: hide it, detach it from <body>, unwire ESC, and
  // restore focus to the trigger that opened it. No-op if nothing is open.
  function close() {
    if (!_active) return;
    var overlay = _active.overlay;
    var trigger = _active.trigger;
    document.removeEventListener('keydown', _onKey, true);
    overlay.hidden = true;
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    _active = null;
    if (trigger && typeof trigger.focus === 'function') {
      try { trigger.focus(); } catch (e) { /* ignore */ }
    }
  }

  // Render the body — one row per entry, or an empty-state message.
  function render(container, routingEntries) {
    if (!container) return;
    var body = container.querySelector('.routing-audit-body');
    if (!body) return;
    body.innerHTML = '';
    var entries = Array.isArray(routingEntries) ? routingEntries : [];
    if (entries.length === 0) {
      var empty = document.createElement('div');
      empty.className = 'routing-audit-empty';
      empty.setAttribute('data-testid', 'routing-audit-empty');
      empty.textContent = 'No routing decisions yet';
      body.appendChild(empty);
      return;
    }
    for (var i = 0; i < entries.length; i++) {
      // Cycle-1 medium follow-up: guard against corrupted / non-object
      // entries (defensive — mirrors append_to_session_metadata's
      // repository-layer normalization). Non-object rows are filtered
      // out rather than rendered as empty rows.
      var row = _buildRow(entries[i]);
      if (row !== null) body.appendChild(row);
    }
  }

  // Wire the Refresh button. chat.js calls this once per session-join so the
  // closure captures the right session id. Repeated calls overwrite the prior
  // handler (Refresh is idempotent — last-binding-wins).
  function wireRefresh(container, sessionId) {
    if (!container) return;
    var btn = container.querySelector('[data-testid="routing-audit-refresh"]');
    if (!btn) return;
    // Replace the node to drop any prior click listener (idempotent wire).
    var clone = btn.cloneNode(true);
    btn.parentNode.replaceChild(clone, btn);
    clone.addEventListener('click', function () {
      refresh(container, sessionId);
    });
  }

  function refresh(container, sessionId, onComplete) {
    if (!container || !sessionId) return;
    var btn = container.querySelector('[data-testid="routing-audit-refresh"]');
    if (btn) btn.disabled = true;
    fetch('/api/chat/sessions/' + encodeURIComponent(sessionId))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (payload) {
        var routing = payload && payload.session_metadata && payload.session_metadata.routing;
        render(container, routing || []);
      })
      .catch(function () { /* keep prior body; AC-7 empty-state still applies on a re-render */ })
      .then(function () {
        if (btn) btn.disabled = false;
        if (typeof onComplete === 'function') onComplete();
      });
  }

  // ─── private helpers ───────────────────────────────────────────────────

  function _buildRow(entry) {
    // Cycle-1 medium follow-up: defensive guard against corrupted DB
    // rows. Non-object entries are filtered (returns null; render
    // skips). Matches the repository-layer defensive normalization.
    if (!entry || typeof entry !== 'object') return null;
    var disposition = String(entry.disposition || 'unknown');
    var row = document.createElement('details');
    row.className = 'routing-audit-row';
    row.setAttribute('data-testid', 'routing-audit-row');
    row.setAttribute('data-disposition', disposition);
    var summary = document.createElement('summary');
    summary.className = 'routing-audit-row-summary';
    summary.setAttribute('data-testid', 'routing-audit-row-summary');

    // Timestamp.
    var time = document.createElement('time');
    time.className = 'routing-audit-ts';
    time.setAttribute('datetime', String(entry.ts || ''));
    time.textContent = String(entry.ts || '');
    summary.appendChild(time);

    // Agent.
    var agent = document.createElement('span');
    agent.className = 'routing-audit-agent';
    agent.textContent = entry.agent ? String(entry.agent) : '—';
    summary.appendChild(agent);

    // Scope.
    var scope = document.createElement('span');
    scope.className = 'routing-audit-scope';
    scope.textContent = String(entry.scope || '');
    summary.appendChild(scope);

    // Reason (truncated).
    var reason = String(entry.reason == null ? '' : entry.reason);
    var reasonSpan = document.createElement('span');
    reasonSpan.className = 'routing-audit-reason';
    reasonSpan.textContent = reason.length > 120 ? reason.slice(0, 120) + '…' : reason;
    summary.appendChild(reasonSpan);

    // Badge — class composes per-disposition.
    var badge = document.createElement('span');
    badge.className = 'routing-audit-badge routing-audit-badge--' + disposition;
    badge.setAttribute('data-testid', 'routing-audit-badge');
    badge.textContent = disposition;
    summary.appendChild(badge);

    row.appendChild(summary);

    // Expansion body — raw fields in EXPANSION_KEY_ORDER.
    var expansion = document.createElement('dl');
    expansion.className = 'routing-audit-expansion';
    expansion.setAttribute('data-testid', 'routing-audit-expansion');
    var seen = {};
    EXPANSION_KEY_ORDER.forEach(function (k) {
      if (!(k in entry)) return;
      seen[k] = true;
      _appendKeyValue(expansion, k, entry[k]);
    });
    // Catch-all for any future keys not in EXPANSION_KEY_ORDER.
    Object.keys(entry).forEach(function (k) {
      if (seen[k]) return;
      _appendKeyValue(expansion, k, entry[k]);
    });
    row.appendChild(expansion);
    return row;
  }

  function _appendKeyValue(dl, key, value) {
    var dt = document.createElement('dt');
    dt.textContent = key;
    dl.appendChild(dt);
    var dd = document.createElement('dd');
    if (key === 'policy' && value && typeof value === 'object') {
      // Nested rendering for the policy dict.
      var policyDl = document.createElement('dl');
      policyDl.className = 'routing-audit-policy';
      policyDl.setAttribute('data-testid', 'routing-audit-policy');
      var seenPolicy = {};
      POLICY_KEY_ORDER.forEach(function (k) {
        if (!(k in value)) return;
        seenPolicy[k] = true;
        _appendKeyValue(policyDl, k, value[k]);
      });
      Object.keys(value).forEach(function (k) {
        if (seenPolicy[k]) return;
        _appendKeyValue(policyDl, k, value[k]);
      });
      dd.appendChild(policyDl);
    } else if (value && typeof value === 'object') {
      // Default object/array rendering — JSON.
      dd.textContent = JSON.stringify(value);
    } else {
      dd.textContent = value == null ? '—' : String(value);
    }
    dl.appendChild(dd);
  }

  // Public exports.
  window.App.chat.routingAuditPanel.createTrigger = createTrigger;
  window.App.chat.routingAuditPanel.createOverlay = createOverlay;
  window.App.chat.routingAuditPanel.open = open;
  window.App.chat.routingAuditPanel.close = close;
  window.App.chat.routingAuditPanel.render = render;
  window.App.chat.routingAuditPanel.wireRefresh = wireRefresh;
  window.App.chat.routingAuditPanel.refresh = refresh;
})();
