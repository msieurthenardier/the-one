// App.studio.routinesForm -- the routine create/edit form (M33 F1 L9, flight DD12).
// Opens inline above the Routines list. Built with DOM APIs on the control library; every
// string from the server (titles, errors) is written with textContent only. The pure body and
// state rules live in routines-form-model.js.
//
//   App.studio.routinesForm.open({mode: 'create'|'edit', routine, agent, panelHost, limits,
//                                 callbacks: {createRoutine, updateRoutine}, opener})
//     -> Promise<routine|null>, resolved with the saved routine (null on Cancel, on a no-op
//        edit or when the host discards the form). The promise carries `.close()` and
//        `.focus()` so the tab can discard an open form when it is left.
//
// Save model: Save sends one request (create, or an edit carrying only what changed). Unsaved
// form text is held here and discarded on Cancel or when the tab is left.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var shared = window.App.studio.rulesNotesShared;
  var el = shared.el;
  var model = window.App.studio.routinesFormModel;

  var KIND_OPTIONS = [
    { value: 'once', label: 'Once' },
    { value: 'daily', label: 'Daily' },
    { value: 'weekdays', label: 'Weekdays' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'interval', label: 'Every N hours' }
  ];
  var TARGET_OPTIONS = [
    { value: 'chat', label: 'A chat' },
    { value: 'new', label: 'A new chat each run' },
    { value: 'own', label: 'Its own chat' }
  ];

  var openForm = null;   // at most one form at a time

  function parseIntOrNaN(v) {
    var n = parseInt(v, 10);
    return isNaN(n) ? NaN : n;
  }

  // The caller stamps the select's testid with a literal (the registry guard reads literals).
  function selectField(label, options, value, onChange) {
    var sel = App.ui.select({
      options: options.map(function (o) { return { value: String(o.value), label: o.label }; }),
      value: String(value),
      onChange: function (e) { onChange(e.target.value); }
    });
    var f = App.ui.field({ label: label, labelHidden: true, control: sel, flush: true });
    return { el: f.el, select: sel };
  }

  // Hour / minute / AM-PM selects over one prefix of the form state; the testids are unique per
  // prefix, so a hidden slot never doubles one.
  function timeRow(fs, keys, groupLabel, onChange) {
    var opts = model.hourMinuteOptions(fs[keys.minute]);
    var row = el('div', 'routine-form-time');
    row.setAttribute('role', 'group');
    row.setAttribute('aria-label', groupLabel);
    var hour = selectField('Hour', opts.hours, fs[keys.hour], function (v) {
      fs[keys.hour] = parseIntOrNaN(v); onChange();
    });
    var minute = selectField('Minute', opts.minutes, fs[keys.minute], function (v) {
      fs[keys.minute] = parseIntOrNaN(v); onChange();
    });
    var ampm = selectField('AM or PM',
      [{ value: 'AM', label: 'AM' }, { value: 'PM', label: 'PM' }], fs[keys.ampm], function (v) {
        fs[keys.ampm] = v; onChange();
      });
    row.appendChild(hour.el);
    row.appendChild(el('span', 'routine-form-colon', ':'));
    row.appendChild(minute.el);
    row.appendChild(ampm.el);
    return { el: row, hour: hour.select, minute: minute.select, ampm: ampm.select };
  }

  function open(req) {
    req = req || {};
    var host = req.panelHost;
    var cbs = req.callbacks || {};
    var limits = req.limits || {};
    var mode = req.mode === 'edit' ? 'edit' : 'create';
    var routine = req.routine || null;
    var opener = req.opener || null;

    if (openForm && openForm.host === host && host && host.contains(openForm.root)) {
      openForm.focus();
      return openForm.promise;
    }

    var today = App.time.parts(new Date());
    var initial = mode === 'edit' && routine
      ? model.bodyToFormState(routine, App.time.parts, today)
      : model.defaultState(today);
    var fs = JSON.parse(JSON.stringify(initial));
    var ctx = { mode: mode, initial: initial };
    var done = false;
    var busy = false;
    var resolveFn;
    var promise = new Promise(function (resolve) { resolveFn = resolve; });

    var root = el('form', 'routine-form');
    root.setAttribute('data-testid', 'routine-form');
    root.setAttribute('novalidate', 'novalidate');
    root.setAttribute('aria-label', mode === 'edit' ? 'Edit routine' : 'New routine');
    root.appendChild(el('h4', 'routine-form-title', mode === 'edit' ? 'Edit routine' : 'New routine'));

    // ── Name and prompt ───────────────────────────────────────────────
    var nameInput = App.ui.textInput({
      value: fs.name, testid: 'routine-form-name',
      onInput: function () { fs.name = nameInput.value; nameField.setError(null); }
    });
    nameInput.maxLength = 64;
    var nameField = App.ui.field({ label: 'Name', control: nameInput });
    root.appendChild(nameField.el);

    var promptInput = App.ui.textarea({
      value: fs.prompt, rows: 5, testid: 'routine-form-prompt',
      onInput: function () { fs.prompt = promptInput.value; promptField.setError(null); }
    });
    var promptField = App.ui.field({
      label: 'Prompt', control: promptInput,
      hint: limits.prompt_chars ? 'Up to ' + String(limits.prompt_chars).replace(/\B(?=(\d{3})+$)/g, ',') + ' characters.' : ''
    });
    root.appendChild(promptField.el);

    // ── Schedule ──────────────────────────────────────────────────────
    var scheduleError = shared.buildErrorLine();
    scheduleError.el.setAttribute('data-testid', 'routine-form-schedule-error');
    var targetError = shared.buildErrorLine();
    targetError.el.setAttribute('data-testid', 'routine-form-target-error');
    var formError = shared.buildErrorLine();
    formError.el.setAttribute('data-testid', 'routine-form-error');

    function changed() { scheduleError.show(''); refresh(); }

    var timeParts = timeRow(fs, { hour: 'hour', minute: 'minute', ampm: 'ampm' },
      'Time of day', changed);
    timeParts.hour.setAttribute('data-testid', 'routine-form-hour');
    timeParts.minute.setAttribute('data-testid', 'routine-form-minute');
    timeParts.ampm.setAttribute('data-testid', 'routine-form-ampm');
    var timeShared = timeParts.el;

    var days = App.ui.checkboxGroup({
      legend: 'Days', testid: 'routine-form-days', value: fs.days,
      options: model.DAY_LABELS.map(function (label, i) {
        return { value: i, label: label, testid: 'routine-form-day-' + i };
      }),
      onChange: function (v) { fs.days = v; changed(); }
    });

    var intervalInput = App.ui.textInput({
      type: 'number', min: 1, max: limits.interval_hours_max || 168, step: 1, width: 'short',
      value: String(fs.interval), testid: 'routine-form-interval',
      onInput: function () { fs.interval = intervalInput.value; changed(); }
    });
    var intervalField = App.ui.field({ label: 'Hours between runs', control: intervalInput });

    // Once: "In" or "At"
    var inAmount = App.ui.textInput({
      type: 'number', min: 1, step: 1, width: 'short', value: String(fs.inAmount),
      testid: 'routine-form-in-amount',
      onInput: function () { fs.inAmount = inAmount.value; changed(); }
    });
    var inAmountField = App.ui.field({ label: 'Amount', labelHidden: true, control: inAmount, flush: true });
    var inUnit = selectField('Unit', [
      { value: 'minutes', label: 'minutes' }, { value: 'hours', label: 'hours' },
      { value: 'days', label: 'days' }
    ], fs.inUnit, function (v) { fs.inUnit = v; changed(); });
    inUnit.select.setAttribute('data-testid', 'routine-form-in-unit');
    var inRow = el('div', 'routine-form-inline');
    inRow.appendChild(inAmountField.el);
    inRow.appendChild(inUnit.el);

    var dayChoices = model.dayOptions(today, mode === 'edit' ? initial.atDay : null);
    var atDay = selectField('Day', dayChoices, fs.atDay, function (v) {
      fs.atDay = v; changed();
    });
    atDay.select.setAttribute('data-testid', 'routine-form-at-day');
    var atParts = timeRow(fs, { hour: 'atHour', minute: 'atMinute', ampm: 'atAmpm' }, 'Time',
      changed);
    atParts.hour.setAttribute('data-testid', 'routine-form-at-hour');
    atParts.minute.setAttribute('data-testid', 'routine-form-at-minute');
    atParts.ampm.setAttribute('data-testid', 'routine-form-at-ampm');
    var atTime = atParts.el;
    var atRow = el('div', 'routine-form-inline');
    atRow.appendChild(atDay.el);
    atRow.appendChild(atTime);

    var onceMode = App.ui.radioGroup({
      legend: 'When', name: 'routine-once-mode', value: fs.onceMode, testid: 'routine-form-once-mode',
      options: [{ value: 'in', label: 'In' }, { value: 'at', label: 'At' }],
      onChange: function (v) { fs.onceMode = v; changed(); }
    });
    onceMode.el.classList.add('routine-form-nested');
    onceMode.optionEl('in').appendChild(inRow);
    onceMode.optionEl('at').appendChild(atRow);

    var kindGroup = App.ui.radioGroup({
      legend: 'Schedule', name: 'routine-schedule-kind', value: fs.kind,
      testid: 'routine-form-schedule', options: KIND_OPTIONS,
      onChange: function (v) { fs.kind = v; changed(); }
    });
    kindGroup.optionEl('once').appendChild(onceMode.el);
    kindGroup.optionEl('weekly').appendChild(days.el);
    kindGroup.optionEl('interval').appendChild(intervalField.el);
    var timeKinds = ['daily', 'weekdays', 'weekly'];
    root.appendChild(kindGroup.el);
    root.appendChild(scheduleError.el);

    // ── Target ────────────────────────────────────────────────────────
    var chatLine = el('p', 'routine-form-chat', '');
    chatLine.setAttribute('data-testid', 'routine-form-chat');
    var chooseBtn = App.ui.button({
      variant: 'secondary', size: 'sm', label: 'Choose chat', testid: 'routine-target-picker',
      onClick: function () { openChooser(chooseBtn); }
    });
    var targetGroup = App.ui.radioGroup({
      legend: 'Run in', name: 'routine-target-kind', value: fs.targetKind,
      testid: 'routine-form-target', options: TARGET_OPTIONS,
      onChange: function (v) { fs.targetKind = v; targetError.show(''); refresh(); }
    });
    var chatSlot = targetGroup.optionEl('chat');
    chatSlot.appendChild(chatLine);
    chatSlot.appendChild(chooseBtn);
    root.appendChild(targetGroup.el);
    root.appendChild(targetError.el);
    root.appendChild(formError.el);

    // ── Buttons ───────────────────────────────────────────────────────
    var actions = el('div', 'routine-form-actions');
    var saveBtn = App.ui.button({
      variant: 'primary', label: 'Save', testid: 'routine-form-save', onClick: function () { save(); }
    });
    var cancelBtn = App.ui.button({
      variant: 'ghost', label: 'Cancel', testid: 'routine-form-cancel', onClick: function () { finish(null, true); }
    });
    actions.appendChild(saveBtn);
    actions.appendChild(cancelBtn);
    root.appendChild(actions);
    root.addEventListener('submit', function (e) { e.preventDefault(); save(); });

    // Show only the selected kind's fields; the one shared time row follows the kind.
    function refresh() {
      KIND_OPTIONS.forEach(function (o) {
        kindGroup.optionEl(o.value).hidden = o.value !== fs.kind;
      });
      var timeSlot = timeKinds.indexOf(fs.kind) !== -1 ? kindGroup.optionEl(fs.kind) : null;
      if (timeSlot && timeShared.parentNode !== timeSlot) timeSlot.insertBefore(timeShared, timeSlot.firstChild);
      onceMode.optionEl('in').hidden = fs.onceMode !== 'in';
      onceMode.optionEl('at').hidden = fs.onceMode !== 'at';
      chatSlot.hidden = fs.targetKind !== 'chat';
      chatLine.textContent = fs.chatId ? fs.chatLabel : 'No chat chosen.';
      // The button's name carries the choice (visible text stays first, WCAG 2.5.3).
      chooseBtn.setAttribute('aria-label',
        'Choose chat, current: ' + (fs.chatId ? fs.chatLabel : 'none'));
    }
    refresh();

    // ── The chat chooser ──────────────────────────────────────────────
    var sessions = { rows: [], loaded: false, failed: false };
    function agentRows() {
      return sessions.rows.filter(function (s) { return s.agent_name === req.agent; })
        .sort(function (a, b) {
          var ta = Date.parse(a.updated_at || a.created_at || '') || 0;
          var tb = Date.parse(b.updated_at || b.created_at || '') || 0;
          return tb - ta;
        });
    }
    function chatItem(s) {
      var d = new Date(s.updated_at || s.created_at || '');
      return {
        id: s.id,
        label: s.title || 'Untitled chat',
        description: s.platform ? App.chat.chatsList.platformName(s.platform) : '',
        meta: isNaN(d.getTime()) ? '' : App.time.formatDate(d),
        dataset: { sessionId: s.id }
      };
    }
    function chooserSource(query) {
      var q = String(query || '').trim().toLowerCase();
      var items = agentRows().filter(function (s) {
        if (!q) return true;
        var hay = ((s.title || 'Untitled chat') + ' ' +
          (s.platform ? App.chat.chatsList.platformName(s.platform) : '')).toLowerCase();
        return hay.indexOf(q) !== -1;
      }).map(chatItem);
      return [{ id: 'chats', label: q ? items.length + ' matching' : 'Chats', items: items }];
    }
    function chooserEmpty(query) {
      if (sessions.failed) return 'Couldn’t load chats.';
      if (!sessions.loaded) return 'Loading chats…';
      if (!agentRows().length) return 'This agent has no chats yet.';
      return 'No chats match "' + String(query || '').trim() + '".';
    }
    function openChooser(openerEl) {
      var picked = null;
      var modal = null;
      var list = App.ui.searchList({
        label: 'Find a chat', placeholder: 'Find a chat by title or platform',
        variant: 'chooser', inputTestid: 'routine-chat-search', rowTestid: 'routine-chat-option',
        source: chooserSource, emptyText: chooserEmpty,
        onPick: function (item) { picked = item; modal.close(item.id); }
      });
      var chooserBody = el('div', 'routine-chat-chooser-body');
      chooserBody.appendChild(list.el);
      modal = App.ui.modal({
        title: 'Choose a chat', layout: 'chooser', width: 560, top: 72, dismissible: true,
        closeButton: { label: 'Esc', ariaLabel: 'Close (Esc)', testid: 'routine-chat-chooser-close' },
        body: chooserBody,
        initialFocus: list.input, testid: 'routine-chat-chooser',
        onClose: function (value) {
          list.destroy();
          // After focus returned to Choose chat.
          if (picked && value === picked.id && !done) {
            fs.chatId = picked.id;
            fs.chatLabel = picked.label;
            targetError.show('');
            refresh();
          }
        }
      });
      modal.open(openerEl);
      sessions.loaded = false;
      sessions.failed = false;
      list.refresh();
      App.store.get('sessions').then(function (rows) {
        sessions.rows = rows || [];
        sessions.loaded = true;
        list.refresh();
      }, function () {
        sessions.failed = true;
        list.refresh();
      });
    }

    // ── Save / close ──────────────────────────────────────────────────
    function setBusy(flag) {
      busy = flag;
      saveBtn.disabled = flag;
      cancelBtn.disabled = flag;
    }

    function finish(value, restoreFocus) {
      if (done) return;
      done = true;
      if (openForm && openForm.root === root) openForm = null;
      if (root.parentNode) root.parentNode.removeChild(root);
      days.destroy();
      kindGroup.destroy();
      onceMode.destroy();
      targetGroup.destroy();
      if (restoreFocus && opener && opener.isConnected && !opener.disabled) opener.focus();
      resolveFn(value);
    }

    function showErrors(errors) {
      var first = null;
      if (errors.name) { nameField.setError(errors.name); first = first || nameInput; }
      if (errors.prompt) { promptField.setError(errors.prompt); first = first || promptInput; }
      if (errors.schedule) {
        scheduleError.show(errors.schedule);
        first = first || (fs.kind === 'weekly' && !fs.days.length ? { focus: days.focus } : kindGroup.input(fs.kind));
      }
      if (errors.target) { targetError.show(errors.target); first = first || targetGroup.input(fs.targetKind); }
      if (first) first.focus();
    }

    function save() {
      if (busy || done) return;
      nameField.setError(null);
      promptField.setError(null);
      scheduleError.show('');
      targetError.show('');
      formError.show('');
      var pre = model.precheck(fs, App.time.parts(new Date()), ctx, limits);
      if (Object.keys(pre).length) { showErrors(pre); return; }
      var body = model.formToBody(fs, ctx);
      if (mode === 'edit' && !Object.keys(body).length) { finish(null, true); return; }
      setBusy(true);
      var call = mode === 'edit'
        ? cbs.updateRoutine(req.agent, routine.id, body)
        : cbs.createRoutine(req.agent, body);
      Promise.resolve(call).then(function (saved) {
        if (done) return;
        setBusy(false);
        finish(saved || { id: routine && routine.id }, false);
      }, function (err) {
        if (done) return;
        setBusy(false);
        var mapped = App.api.fieldErrors(err, ['name', 'prompt', 'schedule', 'target']);
        var f = mapped.fields;
        var errors = {};
        if (f.name) errors.name = f.name;
        if (f.prompt) errors.prompt = f.prompt;
        if (f.schedule) errors.schedule = f.schedule;
        if (f.target) errors.target = f.target;
        showErrors(errors);
        if (mapped.text && !Object.keys(f).length) formError.show(mapped.text);
        else if (mapped.rest.length) formError.show(mapped.text);
      });
    }

    host.insertBefore(root, host.firstChild);
    nameInput.focus();
    var entry = {
      host: host, root: root, promise: promise,
      focus: function () { nameInput.focus(); }
    };
    openForm = entry;
    promise.close = function () { finish(null, false); };
    promise.focus = entry.focus;
    return promise;
  }

  window.App.studio.routinesForm = { open: open };
})();
