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
    name: 'Name', prompt: 'Prompt', schedule: 'Schedule', target: 'Runs in', enabled: 'Switch'
  };
  var FIELD_ORDER = ['name', 'schedule', 'target', 'enabled', 'prompt'];
  // The stale 409's maps are keyed by the stored columns; each field's primary column says
  // whether the proposal touched it (schedule and enabled also carry finished_at).
  var PRIMARY_COLUMN = {
    name: 'name', prompt: 'prompt', schedule: 'schedule', target: 'target_kind', enabled: 'enabled'
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
  function baseView(b) {
    b = b || {};
    return {
      name: b.name, prompt: b.prompt, schedule: b.schedule, enabled: b.enabled,
      target: { kind: b.target_kind, session_id: b.target_session_id }
    };
  }

  function targetWords(t) {
    if (!t || !t.kind) return '';
    if (t.kind === 'chat') {
      var title = '';
      try {
        var rows = App.store.peek('sessions');
        rows = rows && rows.rows ? rows.rows : rows;
        (Array.isArray(rows) ? rows : []).forEach(function (s) {
          if (s && s.id === t.session_id) title = s.title || 'Untitled chat';
        });
      } catch (e) { title = ''; }
      return title ? 'Chat: ' + title : 'A chosen chat';
    }
    return describe().describeTarget({ kind: t.kind });
  }

  // One field of a routine view in words (never the prompt: that is a code block).
  function fieldWords(field, view) {
    if (!view) return '';
    switch (field) {
      case 'name': return String(view.name == null ? '' : view.name);
      case 'schedule': return describe().describeSchedule(view.schedule);
      case 'target': return targetWords(view.target);
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
  function columnsView(map) {
    var v = baseView(map);
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
        target: payload.target, enabled: payload.enabled
      };
      ['schedule', 'target'].forEach(function (f) { body.appendChild(fieldBlock(f, null, v)); });
      if (payload.enabled === false) body.appendChild(fieldBlock('enabled', null, v));
      body.appendChild(fieldBlock('prompt', null, v));
    } else if (p.action === 'update') {
      var before = baseView(p.base);
      touchedFields(p).forEach(function (f) { body.appendChild(fieldBlock(f, before, payload)); });
    } else {
      var cur = baseView(p.base);
      body.appendChild(el('p', { className: 'self-config-routine-line',
        text: 'The agent asks to delete this routine and its history.' }));
      ['schedule', 'target'].forEach(function (f) { body.appendChild(fieldBlock(f, null, cur)); });
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
    var section = ctx.routinesSection;

    section.body.appendChild(el('h4', { className: 'self-config-routines-subheading', text: 'Waiting for approval' }));
    section.body.appendChild(el('p', { className: 'self-configuration-description',
      text: 'Changes the agent asked for. A one-off whose time has passed can only be dismissed.' }));

    var countStatus = App.ui.status({
      state: 'idle', text: '', led: false, live: 'off', testid: 'self-config-routine-pending-count'
    });
    countStatus.el.classList.add('self-configuration-pending-count');
    countStatus.el.tabIndex = -1;
    countStatus.el.hidden = true;
    section.body.appendChild(countStatus.el);

    var list = el('ul', { className: 'self-config-routine-proposals' });
    list.setAttribute('role', 'list');
    list.setAttribute('data-testid', 'self-config-routine-proposals');
    section.body.appendChild(list);

    var empty = App.ui.emptyState({
      title: 'Nothing waiting.', titleTag: 'p', variant: 'plain',
      testid: 'self-config-routine-proposals-empty'
    });
    empty.tabIndex = -1;
    section.body.appendChild(empty);

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
        stale.hidden = false;
        stale.textContent = '';
        stale.appendChild(App.ui.banner({
          tone: 'warning', role: 'alert', text: 'This routine changed since the agent asked.'
        }).el);
        var cur = columnsView(detail.current_value);
        var prop = detail.proposed_value || {};
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
      empty.hidden = pending.length > 0;
      list.hidden = pending.length === 0;
      countStatus.el.hidden = pending.length === 0;
      countStatus.set('idle', pending.length === 1
        ? '1 change waiting for your approval.'
        : pending.length + ' changes waiting for your approval.');
    }

    ctx.renderRoutineQueue = renderRoutineQueue;
    ctx.routineQueueEmpty = empty;
    ctx.routineQueueCount = countStatus;
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
