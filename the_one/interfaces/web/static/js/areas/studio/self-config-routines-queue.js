// App.studio.selfConfigRoutinesQueue -- the Self-configuration tab's Routines item, queue half
// (M33 F2 L5): the "Waiting for approval" list of the agent's pending routine changes, with
// Approve, Dismiss and the stale path ("Approve anyway"), plus the display helpers the history
// list shares. `build(ctx)` appends the queue to `ctx.routinesSection.body` and publishes
// `ctx.renderRoutineQueue(proposals)`; it reads `ctx.agent`, `ctx.callbacks` and the sibling
// module's `ctx.refetchRoutines` / `ctx.routinesAnnounce` at call time. Every text goes through
// textContent; no HTML-string sinks.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var ACTION_WORDS = { create: 'Create', update: 'Change', delete: 'Cancel' };
  var ACTION_NOUNS = { create: 'creation', update: 'change', delete: 'cancellation' };
  var FIELD_LABELS = {
    name: 'Name', prompt: 'Prompt', schedule: 'Schedule', enabled: 'Switch'
  };
  var FIELD_ORDER = ['name', 'schedule', 'enabled', 'prompt'];
  // The stale 409's maps are keyed by the stored columns; each field's primary column says
  // whether the proposal touched it (schedule and enabled also carry finished_at).
  var PRIMARY_COLUMN = {
    name: 'name', prompt: 'prompt', schedule: 'schedule', enabled: 'enabled'
  };

  function el(tag, attrs, children) { return App.ui.util.el(tag, attrs, children); }
  function describe() { return App.studio.routinesDescribe; }
  function actionWord(a) { return ACTION_WORDS[a] || 'Change'; }
  function statusWord(s) {
    if (s === 'applied') return 'Applied';
    if (s === 'dismissed') return 'Dismissed';
    if (s === 'superseded') return 'Withdrawn';
    return s === 'pending' ? 'Waiting' : String(s || '');
  }

  // A stored routine's columns -> the view shape the describers read.
  // `scheduleText` is the server's sentence for the schedule (the browser never words one).
  function baseView(b, scheduleText) {
    b = b || {};
    return {
      name: b.name, prompt: b.prompt, schedule: b.schedule, enabled: b.enabled,
      scheduleText: scheduleText
    };
  }

  // One field of a routine view in words (never the prompt: that is a code block).
  function fieldWords(field, view) {
    if (!view) return '';
    switch (field) {
      case 'name': return String(view.name == null ? '' : view.name);
      case 'schedule': return view.scheduleText == null ? '' : String(view.scheduleText);
      case 'enabled': return view.enabled === false ? 'Off' : 'On';
      default: return '';
    }
  }

  // Which fields a proposal touches, in display order.
  function touchedFields(p) {
    var payload = p.payload || {};
    return FIELD_ORDER.filter(function (f) { return Object.prototype.hasOwnProperty.call(payload, f); });
  }

  // The view of a stale 409's `current_value` / `base_value` map (stored columns).
  function columnsView(map, scheduleText) {
    return baseView(map, scheduleText);
  }

  // A proposal payload as a view, carrying the server's sentence for its schedule.
  function payloadView(payload, scheduleText) {
    var v = { scheduleText: scheduleText };
    Object.keys(payload || {}).forEach(function (k) { v[k] = payload[k]; });
    return v;
  }

  // One labelled field: "Label: before -> after" for words, or Now / Proposed code blocks for a
  // prompt. `before` null means a plain value (a create).
  function fieldBlock(field, beforeView, afterView) {
    var box = el('div', { className: 'self-config-routine-field' });
    box.setAttribute('data-field', field);
    var label = FIELD_LABELS[field];
    if (field === 'prompt') {
      box.appendChild(el('div', { className: 'revision-value-label', text: label }));
      if (beforeView) {
        box.appendChild(el('div', { className: 'revision-value-label', text: 'Now' }));
        box.appendChild(App.ui.codeBlock({
          className: 'revision-value', text: String(beforeView.prompt == null ? '' : beforeView.prompt),
          testid: 'self-config-routine-prompt-now'
        }).el);
        box.appendChild(el('div', { className: 'revision-value-label', text: 'Proposed' }));
      }
      box.appendChild(App.ui.codeBlock({
        className: 'revision-value', text: String(afterView.prompt == null ? '' : afterView.prompt),
        testid: 'self-config-routine-prompt-proposed'
      }).el);
      return box;
    }
    var after = fieldWords(field, afterView);
    var text = beforeView ? fieldWords(field, beforeView) + ' → ' + after : after;
    box.appendChild(el('span', { className: 'self-config-routine-field-label', text: label + ': ' }));
    box.appendChild(el('span', { className: 'self-config-routine-field-value', text: text }));
    return box;
  }

  // The proposal's body: a create's whole routine, a change's touched fields, a cancel's
  // routine as it stands.
  function buildBody(p) {
    var body = el('div', { className: 'self-config-routine-body' });
    var payload = p.payload || {};
    if (p.action === 'create') {
      var v = {
        name: payload.name, prompt: payload.prompt, schedule: payload.schedule,
        enabled: payload.enabled, scheduleText: p.payload_schedule_text
      };
      body.appendChild(fieldBlock('schedule', null, v));
      if (payload.enabled === false) body.appendChild(fieldBlock('enabled', null, v));
      body.appendChild(fieldBlock('prompt', null, v));
    } else if (p.action === 'update') {
      var before = baseView(p.base, p.base_schedule_text);
      var after = payloadView(payload, p.payload_schedule_text);
      touchedFields(p).forEach(function (f) { body.appendChild(fieldBlock(f, before, after)); });
    } else {
      var cur = baseView(p.base, p.base_schedule_text);
      body.appendChild(el('p', { className: 'self-config-routine-line',
        text: 'The agent asks to delete this routine and its history.' }));
      body.appendChild(fieldBlock('schedule', null, cur));
    }
    return body;
  }

  // The proposal's header: action word, name, the flag and the time.
  function buildHead(p) {
    var kids = [
      el('span', { className: 'self-config-routine-action', text: actionWord(p.action) }),
      el('span', { className: 'self-config-routine-name', text: p.routine_name || '' })
    ];
    kids[0].setAttribute('data-testid', 'self-config-routine-action');
    kids[1].setAttribute('data-testid', 'self-config-routine-name');
    if (p.untrusted) {
      var flag = App.ui.noteFlag({ subject: 'routine', sources: p.untrusted_sources || [] });
      flag.setAttribute('data-testid', 'self-config-routine-flag');
      kids.push(flag);
    }
    var when = el('span', { className: 'self-config-routine-when',
      text: describe().describeWhen(p.resolved_at && p.status !== 'pending' ? p.resolved_at : p.created_at),
      title: p.created_at || '' });
    when.setAttribute('data-testid', 'self-config-routine-when');
    kids.push(when);
    return el('div', { className: 'self-config-routine-head' }, kids);
  }

  // Keyed in-place reconcile of `list`'s children against `rows` (objects with `id`): kept
  // views are untouched (their open state survives), new ones are built, gone ones dropped.
  function reconcile(list, rows, views, build) {
    var seen = {};
    rows.forEach(function (row, i) {
      seen[row.id] = true;
      var v = views[row.id];
      if (!v) { v = build(row); views[row.id] = v; }
      if (list.children[i] !== v.el) list.insertBefore(v.el, list.children[i] || null);
    });
    Object.keys(views).forEach(function (id) {
      if (!seen[id]) { if (views[id].el.parentNode) views[id].el.remove(); delete views[id]; }
    });
  }

  function errorText(err) {
    var d = err && err.detail;
    if (err && err.status === 422) return App.api.fieldErrors(err, []).text;
    if (typeof d === 'string' && d) return d;
    return (err && err.message) || 'That did not work.';
  }

  function build(ctx) {
    var cb = ctx.callbacks;
    // The card's "Waiting for approval" expander body; its count chip and the plain
    // "(0)" line (the focus target when the queue empties) belong to the card.
    var queueCard = ctx.cards.routines.queue;
    var body = queueCard.body;

    body.appendChild(el('p', { className: 'self-configuration-description',
      text: 'Changes the agent asked for. A one-off whose time has passed can only be dismissed.' }));

    var list = el('ul', { className: 'self-config-routine-proposals' });
    list.setAttribute('role', 'list');
    list.setAttribute('data-testid', 'self-config-routine-proposals');
    body.appendChild(list);

    var empty = queueCard.zero;

    var views = {};

    function buildItem(p) {
      var v = { id: p.id, p: p };
      var li = el('li', { className: 'self-config-routine-proposal' });
      li.setAttribute('data-testid', 'self-config-routine-proposal');
      li.setAttribute('data-id', p.id);
      li.setAttribute('data-action', p.action);
      li.appendChild(buildHead(p));
      li.appendChild(buildBody(p));

      var stale = el('div', { className: 'self-config-routine-stale' });
      stale.hidden = true;
      li.appendChild(stale);

      var err = App.ui.status({ state: 'danger', led: false, role: 'alert', testid: 'self-config-routine-error' });
      err.el.classList.add('self-configuration-error');
      err.el.hidden = true;
      li.appendChild(err.el);

      var word = actionWord(p.action);
      var what = word + ' of ' + (p.routine_name || 'routine');
      var actions = el('div', { className: 'revision-actions' });
      var approve = App.ui.button({
        variant: 'primary', label: 'Approve', ariaLabel: 'Approve ' + what,
        testid: 'self-config-routine-approve'
      });
      var dismiss = App.ui.button({
        variant: 'secondary', label: 'Dismiss', ariaLabel: 'Dismiss ' + what,
        testid: 'self-config-routine-dismiss'
      });
      actions.appendChild(approve);
      actions.appendChild(dismiss);
      li.appendChild(actions);

      v.el = li;
      v.approve = approve;
      v.dismiss = dismiss;
      var override = null;

      function setBusy(b) {
        approve.disabled = b;
        dismiss.disabled = b;
        if (override) override.disabled = b;
      }
      function showError(msg) {
        // An error that lands after the operator collapsed the expander opens it again.
        if (msg) queueCard.open();
        err.el.hidden = !msg;
        err.set('danger', msg || '');
      }

      // Focus goes to the next item's Approve (else the previous one's), or to the empty
      // state when the queue empties; decided before the refetch removes this item.
      function focusAfter(done) {
        var idx = Array.prototype.indexOf.call(list.children, li);
        var next = list.children[idx + 1] || list.children[idx - 1] || null;
        var nextId = next ? next.getAttribute('data-id') : null;
        return Promise.resolve(done).then(function () {
          if (ctx.destroyed) return;
          var nv = nextId && views[nextId];
          if (nv) nv.approve.focus();
          else if (!Object.keys(views).length) empty.focus();
        });
      }

      function finish(message) {
        ctx.routinesAnnounce(message);
        return focusAfter(ctx.refetchRoutines());
      }

      function renderStale(detail) {
        queueCard.open();
        stale.hidden = false;
        stale.textContent = '';
        stale.appendChild(App.ui.banner({
          tone: 'warning', role: 'alert', text: 'This routine changed since the agent asked.'
        }).el);
        var cur = columnsView(detail.current_value, detail.current_schedule_text);
        var prop = payloadView(detail.proposed_value, detail.proposed_schedule_text);
        var cols = detail.current_value || {};
        FIELD_ORDER.forEach(function (f) {
          if (!Object.prototype.hasOwnProperty.call(cols, PRIMARY_COLUMN[f])) return;
          var box = el('div', { className: 'self-config-routine-field' });
          box.setAttribute('data-field', f);
          if (f === 'prompt') {
            box.appendChild(el('div', { className: 'revision-value-label', text: 'Prompt now' }));
            box.appendChild(App.ui.codeBlock({ className: 'revision-value', text: String(cur.prompt || ''),
              testid: 'self-config-routine-stale-current' }).el);
            if (p.action !== 'delete') {
              box.appendChild(el('div', { className: 'revision-value-label', text: 'Prompt proposed' }));
              box.appendChild(App.ui.codeBlock({ className: 'revision-value', text: String(prop.prompt || ''),
                testid: 'self-config-routine-stale-proposed' }).el);
            }
          } else {
            var line = FIELD_LABELS[f] + ' now: ' + fieldWords(f, cur);
            if (p.action !== 'delete') line += '. Proposed: ' + fieldWords(f, prop);
            box.appendChild(el('span', { className: 'self-config-routine-field-value', text: line }));
          }
          stale.appendChild(box);
        });
        if (!override) {
          override = App.ui.button({
            variant: 'primary', label: 'Approve anyway', testid: 'self-config-routine-approve-override',
            ariaLabel: 'Approve ' + what + ' anyway'
          });
          override.onclick = function () { run(true); };
          actions.insertBefore(override, dismiss);
        }
        approve.hidden = true;
      }

      // Return focus to the pressed button when it is lost (body) or still inside this item;
      // never steal focus the user has moved elsewhere.
      function restoreFocus(btn) {
        var a = document.activeElement;
        if (!btn || btn.hidden) return;
        if (!a || a === document.body || li.contains(a)) btn.focus();
      }
      function run(isOverride) {
        if (!cb.approveRoutineProposal) return;
        showError('');
        var pressed = isOverride ? override : approve;
        setBusy(true);
        cb.approveRoutineProposal(ctx.agent.name, p.id, !!isOverride).then(function (done) {
          if (ctx.destroyed) return;
          if (done && done.status && done.status !== 'applied') {
            return finish('The routine is gone; the change was withdrawn.');
          }
          return finish('Approved ' + word.toLowerCase() + ' of ' + (p.routine_name || 'routine') + '.');
        }, function (e) {
          if (ctx.destroyed) return;
          var d = e && e.detail;
          if (e && e.status === 409 && d && d.error === 'stale') {
            renderStale(d);
            setBusy(false);
            if (override) override.focus();
            return;
          }
          if (e && e.status === 409 && d && d.error === 'gone') {
            return finish('The routine is gone; the change was withdrawn.');
          }
          showError(errorText(e));
          setBusy(false);
          restoreFocus(pressed);
        });
      }

      approve.onclick = function () { run(false); };
      dismiss.onclick = function () {
        if (!cb.dismissRoutineProposal) return;
        showError('');
        setBusy(true);
        cb.dismissRoutineProposal(ctx.agent.name, p.id).then(function () {
          if (ctx.destroyed) return;
          return finish('Dismissed ' + word.toLowerCase() + ' of ' + (p.routine_name || 'routine') + '.');
        }, function (e) {
          if (ctx.destroyed) return;
          showError(errorText(e));
          setBusy(false);
          restoreFocus(dismiss);
        });
      };
      return v;
    }

    function renderRoutineQueue(proposals) {
      var pending = (proposals || []).filter(function (p) { return p.status === 'pending'; });
      reconcile(list, pending, views, buildItem);
      list.hidden = pending.length === 0;
      queueCard.setCount(pending.length);
    }

    ctx.renderRoutineQueue = renderRoutineQueue;
  }

  window.App.studio.selfConfigRoutinesQueue = {
    build: build,
    actionWord: actionWord,
    statusWord: statusWord,
    buildHead: buildHead,
    reconcile: reconcile,
    errorText: errorText
  };
})();
