(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var BUCKET_ORDER = ['today', 'yesterday', 'last7', 'last30', 'older'];
  var BUCKET_LABELS = {
    today: 'Today',
    yesterday: 'Yesterday',
    last7: 'Last 7 Days',
    last30: 'Last 30 Days',
    older: 'Older'
  };

  function startOfDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  }

  function bucketForSession(s, nowDay) {
    // Sessions carry created_at/updated_at as ISO strings. Sort buckets by
    // most recent activity (updated_at falls back to created_at).
    var ts = s.updated_at || s.created_at;
    if (!ts) return 'older';
    var parsed = new Date(ts);
    if (isNaN(parsed.getTime())) return 'older';
    var sessionDay = startOfDay(parsed);
    var dayDiff = Math.round((nowDay - sessionDay) / 86400000);
    if (dayDiff <= 0) return 'today';
    if (dayDiff === 1) return 'yesterday';
    if (dayDiff <= 7) return 'last7';
    if (dayDiff <= 30) return 'last30';
    return 'older';
  }

  function buildSessionItem(s, currentSessionId, callbacks) {
    // Post-F2 leg 01: the row is a <li class="list-item"> containing a
    // <button class="session-item"> as the session selector and a sibling
    // <button class="delete list-item-delete"> for delete. Dropping the
    // listbox/option role pair fixes WCAG 4.1.2 (a role="option" cannot
    // legally contain a nested interactive element).
    //
    // The <li> preserves the `.list-item` class so the CSS :focus-within
    // reveal (components.css:123-124) keeps showing the delete affordance
    // when Tab moves focus into the row.
    var li = document.createElement('li');
    li.className = 'list-item' + (s.id === currentSessionId ? ' active' : '');

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'session-item';
    btn.dataset.id = s.id;
    if (s.id === currentSessionId) {
      btn.setAttribute('aria-current', 'page');
    }

    var textWrap = document.createElement('div');
    textWrap.className = 'session-item-text';

    var titleSpan = document.createElement('span');
    titleSpan.className = 'session-item-title';
    titleSpan.setAttribute('data-confirm-title', '');
    titleSpan.textContent = s.title;
    textWrap.appendChild(titleSpan);

    var agentSpan = document.createElement('span');
    agentSpan.className = 'session-item-agent';
    agentSpan.textContent = s.agent_name || 'default';
    textWrap.appendChild(agentSpan);

    // M10 F05 L01: connector-bound sessions show a source badge so the
    // operator can distinguish platform-driven conversations from web-native
    // ones at a glance. Non-connector rows (platform == null/undefined/'')
    // render exactly as before. The typed modifier class
    // (session-item-source--{type}) mirrors mcp-servers-grid.js's
    // admin-mcp-badge--{type} precedent so future connector types can be
    // color-themed via additive CSS only.
    if (s.platform) {
      var sourceSpan = document.createElement('span');
      // textContent is XSS-safe (DOM API, not innerHTML); the regex strip
      // below only matters for the className path — same defensive shape
      // as mcp-servers-grid.js:97-98 wrapping the badge-type suffix.
      var typeSafe = String(s.platform).replace(/[^a-zA-Z0-9_-]/g, '');
      sourceSpan.className = 'session-item-source'
        + (typeSafe ? ' session-item-source--' + typeSafe : '');
      sourceSpan.textContent = s.platform;
      textWrap.appendChild(sourceSpan);
    }

    btn.appendChild(textWrap);
    btn.onclick = function () { callbacks.onJoin(s.id); };
    // Native <button> Enter/Space activation handles the join — no custom
    // keydown bail needed. The previous wrapper-div implementation required
    // an "e.target !== el" guard to avoid descendant-bubbled keys firing
    // onJoin from the delete button; the sibling layout retires that case.
    li.appendChild(btn);

    var delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'delete list-item-delete';
    delBtn.setAttribute('aria-label', 'Delete session');
    delBtn.innerHTML = App.icon('x');
    delBtn.onclick = function (e) {
      e.stopPropagation();
      callbacks.onDelete(s.id, delBtn);
    };
    li.appendChild(delBtn);

    return li;
  }

  // Build the pinned "Pending approvals" section — M11 F17 L9 (Leg E).
  // Renders above "Chat History" whenever there are pending rows.
  // Each item shows peer_name + preview; not interactive (approve/dismiss
  // happens in the message-area banner). Kept simple: no delete affordance,
  // no routing — operator notices the flag and clicks into the session.
  function buildPendingApprovalsSection(pendingApprovals) {
    var section = document.createElement('div');
    section.className = 'session-group pending-approvals-section';
    section.setAttribute('data-testid', 'pending-approvals-section');

    var headingEl = document.createElement('div');
    headingEl.className = 'section-title pending-approvals-title';
    headingEl.textContent = 'Pending approvals';
    section.appendChild(headingEl);

    var listEl = document.createElement('ul');
    listEl.className = 'session-group-list';
    listEl.setAttribute('aria-label', 'Pending approvals');

    for (var i = 0; i < pendingApprovals.length; i++) {
      var pa = pendingApprovals[i];
      var li = document.createElement('li');
      li.className = 'list-item pending-approval-item';
      li.setAttribute('data-testid', 'pending-approval-item');

      var nameSpan = document.createElement('span');
      nameSpan.className = 'pending-approval-peer-name';
      nameSpan.textContent = pa.peer_name || 'Unknown';

      var previewSpan = document.createElement('span');
      previewSpan.className = 'pending-approval-preview';
      previewSpan.textContent = pa.preview || '';

      li.appendChild(nameSpan);
      li.appendChild(previewSpan);
      listEl.appendChild(li);
    }

    section.appendChild(listEl);
    return section;
  }

  function renderSessionList(sessionListEl, sessions, currentSessionId, callbacks, pendingApprovals) {
    sessionListEl.innerHTML = '';

    // Pinned "Pending approvals" section — rendered ABOVE "Chat History"
    // (M11 F17 L9 Leg E). Pending approvals are not sessions — they live
    // in their own section so they don't pollute the recency buckets.
    if (pendingApprovals && pendingApprovals.length > 0) {
      sessionListEl.appendChild(buildPendingApprovalsSection(pendingApprovals));
    }

    // Heading always renders so the empty + populated states share an anchor.
    // section-title gives the `// CHAT HISTORY` idiom shared with the
    // sidebar's `// SELECT AGENT` and the admin/studio section headers.
    var headingEl = document.createElement('div');
    headingEl.className = 'section-title';
    headingEl.textContent = 'Chat History';
    sessionListEl.appendChild(headingEl);

    if (!sessions.length) {
      var emptyEl = document.createElement('div');
      emptyEl.className = 'session-list-empty';
      emptyEl.textContent = 'No conversations yet.';
      sessionListEl.appendChild(emptyEl);
      return;
    }

    // Order sessions by updated_at desc within each bucket; assign to buckets.
    var nowDay = startOfDay(new Date());
    var grouped = {};
    for (var i = 0; i < sessions.length; i++) {
      var s = sessions[i];
      var bucket = bucketForSession(s, nowDay);
      (grouped[bucket] = grouped[bucket] || []).push(s);
    }

    // Sessions list arrives unordered; sort each bucket by recency.
    function recency(s) { return new Date(s.updated_at || s.created_at || 0).getTime(); }
    for (var b in grouped) {
      if (Object.prototype.hasOwnProperty.call(grouped, b)) {
        grouped[b].sort(function (a, c) { return recency(c) - recency(a); });
      }
    }

    for (var k = 0; k < BUCKET_ORDER.length; k++) {
      var key = BUCKET_ORDER[k];
      if (!grouped[key] || !grouped[key].length) continue;

      var groupEl = document.createElement('div');
      groupEl.className = 'session-group';

      var labelId = 'session-group-' + key;
      var labelEl = document.createElement('div');
      labelEl.className = 'session-group-label';
      labelEl.id = labelId;
      labelEl.textContent = BUCKET_LABELS[key];
      groupEl.appendChild(labelEl);

      // Each bucket gets its own <ul> so session rows are <li> children of
      // a list. The bucket label is the accessible name for the list.
      var listEl = document.createElement('ul');
      listEl.className = 'session-group-list';
      listEl.setAttribute('aria-labelledby', labelId);
      for (var m = 0; m < grouped[key].length; m++) {
        listEl.appendChild(buildSessionItem(grouped[key][m], currentSessionId, callbacks));
      }
      groupEl.appendChild(listEl);
      sessionListEl.appendChild(groupEl);
    }
  }

  window.App.chat.BUCKET_ORDER = BUCKET_ORDER;
  window.App.chat.BUCKET_LABELS = BUCKET_LABELS;
  window.App.chat.startOfDay = startOfDay;
  window.App.chat.bucketForSession = bucketForSession;
  window.App.chat.buildSessionItem = buildSessionItem;
  window.App.chat.buildPendingApprovalsSection = buildPendingApprovalsSection;
  window.App.chat.renderSessionList = renderSessionList;
})();
