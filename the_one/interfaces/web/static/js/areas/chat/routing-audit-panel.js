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

  // Build the panel chrome. Returns the outer container; chat.js inserts
  // it into chromeEl between .messages and .input-area.
  function create() {
    var wrap = document.createElement('div');
    wrap.className = 'routing-audit-panel';
    wrap.setAttribute('data-testid', 'routing-audit-panel');
    var details = document.createElement('details');
    details.setAttribute('data-testid', 'routing-audit-details');
    // Collapsed by default — AC-12.
    var summary = document.createElement('summary');
    summary.className = 'routing-audit-toggle';
    summary.textContent = 'Routing audit';
    summary.setAttribute('data-testid', 'routing-audit-summary');
    details.appendChild(summary);

    var header = document.createElement('div');
    header.className = 'routing-audit-header';
    var refreshBtn = document.createElement('button');
    refreshBtn.type = 'button';
    refreshBtn.className = 'btn-muted routing-audit-refresh';
    refreshBtn.textContent = 'Refresh';
    refreshBtn.setAttribute('data-testid', 'routing-audit-refresh');
    header.appendChild(refreshBtn);
    details.appendChild(header);

    var body = document.createElement('div');
    body.className = 'routing-audit-body';
    body.setAttribute('data-testid', 'routing-audit-body');
    details.appendChild(body);

    wrap.appendChild(details);
    return wrap;
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
  window.App.chat.routingAuditPanel.create = create;
  window.App.chat.routingAuditPanel.render = render;
  window.App.chat.routingAuditPanel.wireRefresh = wireRefresh;
  window.App.chat.routingAuditPanel.refresh = refresh;
})();
