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
    var el = document.createElement('div');
    el.className = 'list-item session-item' + (s.id === currentSessionId ? ' active' : '');
    el.setAttribute('role', 'option');
    el.setAttribute('tabindex', '0');
    el.setAttribute('aria-selected', s.id === currentSessionId ? 'true' : 'false');
    el.dataset.id = s.id;

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

    el.appendChild(textWrap);

    var delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'delete list-item-delete';
    delBtn.setAttribute('aria-label', 'Delete session');
    delBtn.innerHTML = App.icon('x');
    delBtn.onclick = function (e) {
      e.stopPropagation();
      callbacks.onDelete(s.id, delBtn);
    };
    el.appendChild(delBtn);

    el.onclick = function () { callbacks.onJoin(s.id); };
    el.addEventListener('keydown', function (e) {
      // Ignore keydown bubbled from descendants (e.g., the delete button) so
      // pressing Enter while focused on the X doesn't suppress the button's
      // own activation and accidentally fire onJoin.
      if (e.target !== el) return;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        callbacks.onJoin(s.id);
      }
    });
    return el;
  }

  function renderSessionList(sessionListEl, sessions, currentSessionId, callbacks) {
    sessionListEl.innerHTML = '';

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
      groupEl.setAttribute('role', 'group');

      var labelId = 'session-group-' + key;
      var labelEl = document.createElement('div');
      labelEl.className = 'session-group-label';
      labelEl.id = labelId;
      labelEl.textContent = BUCKET_LABELS[key];
      groupEl.setAttribute('aria-labelledby', labelId);
      groupEl.appendChild(labelEl);

      for (var m = 0; m < grouped[key].length; m++) {
        groupEl.appendChild(buildSessionItem(grouped[key][m], currentSessionId, callbacks));
      }
      sessionListEl.appendChild(groupEl);
    }
  }

  window.App.chat.BUCKET_ORDER = BUCKET_ORDER;
  window.App.chat.BUCKET_LABELS = BUCKET_LABELS;
  window.App.chat.startOfDay = startOfDay;
  window.App.chat.bucketForSession = bucketForSession;
  window.App.chat.buildSessionItem = buildSessionItem;
  window.App.chat.renderSessionList = renderSessionList;
})();
