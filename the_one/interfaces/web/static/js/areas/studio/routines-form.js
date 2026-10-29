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
  var describe = window.App.studio.routinesDescribe;

  var TARGET_OPTIONS = [
    { value: 'chat', label: 'A chat' },
    { value: 'new', label: 'A new chat each run' },
    { value: 'own', label: 'Its own chat' }
  ];

  var openForm = null;   // at most one form at a time

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

  var PREVIEW_DELAY_MS = 300;

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

    // The operator-zone date, for the pickers' "today" and minimum.
    function todayIso() {
      var p = App.time.parts(new Date());
      return model.isoOf(p.year, p.month, p.day);
    }
    var initial = mode === 'edit' && routine
      ? model.bodyToFormState(routine)
      : model.defaultState(Date.now(), App.time.parts);
    var fs = JSON.parse(JSON.stringify(initial));
    var ctx = { mode: mode, initial: initial, flagged: !!(routine && routine.untrusted) };
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
      hint: (limits.prompt_chars ? 'Up to ' + String(limits.prompt_chars).replace(/\B(?=(\d{3})+$)/g, ',') + ' characters.' : '') +
        (ctx.flagged ? (limits.prompt_chars ? ' ' : '') + 'Saving marks this routine as checked.' : '')
    });
    root.appendChild(promptField.el);

    // ── Schedule: starts, repeat, preview ─────────────────────────────
    var scheduleError = shared.buildErrorLine();
    scheduleError.el.setAttribute('data-testid', 'routine-form-schedule-error');
    var targetError = shared.buildErrorLine();
    targetError.el.setAttribute('data-testid', 'routine-form-target-error');
    var formError = shared.buildErrorLine();
    formError.el.setAttribute('data-testid', 'routine-form-error');

    var lastStart = fs.startDate;       // the last valid start date (presets follow it)
    var latest = App.ui.util.latest();
    var previewTimer = null;
    var customModal = null;

    var minDate = todayIso();
    if (mode === 'edit' && fs.startDate && fs.startDate < minDate) minDate = fs.startDate;

    var startDate = App.ui.datePicker({
      label: 'Start date', value: fs.startDate, min: minDate, today: todayIso,
      testid: 'routine-form-start-date',
      onChange: function (iso) {
        fs.startDate = iso;
        if (iso) lastStart = iso;
        startChanged();
      }
    });
    var startTime = App.ui.timeField({
      label: 'Start time', value: fs.startTime, testid: 'routine-form-start-time',
      onChange: function (hhmm) { fs.startTime = hhmm; scheduleChanged(); }
    });

    // "Or start in N minutes / hours / days" fills the two fields from now.
    var inAmount = App.ui.textInput({
      type: 'number', min: 1, step: 1, width: 'short', value: '',
      testid: 'routine-form-in-amount', onInput: function () { applyIn(); }
    });
    var inAmountField = App.ui.field({ label: 'Start in, amount', labelHidden: true, control: inAmount, flush: true });
    var inUnit = selectField('Start in, unit', [
      { value: 'minutes', label: 'minutes' }, { value: 'hours', label: 'hours' },
      { value: 'days', label: 'days' }
    ], 'hours', function () { applyIn(); });
    inUnit.select.setAttribute('data-testid', 'routine-form-in-unit');
    var inRow = el('div', 'routine-form-inline');
    inRow.appendChild(el('span', 'routine-form-in-text', 'Or start in'));
    inRow.appendChild(inAmountField.el);
    inRow.appendChild(inUnit.el);

    var startRow = el('div', 'routine-form-start');
    startRow.appendChild(startDate.el);
    startRow.appendChild(startTime.el);
    var startGroup = el('div', 'routine-form-starts');
    startGroup.setAttribute('role', 'group');
    startGroup.setAttribute('aria-label', 'Starts');
    startGroup.appendChild(startRow);
    startGroup.appendChild(inRow);
    root.appendChild(startGroup);

    var repeatSelect = App.ui.select({
      options: [{ value: 'none', label: 'Does not repeat' }], value: 'none',
      testid: 'routine-form-repeat',
      onChange: function (e) {
        var v = e.target.value;
        if (v === 'custom') { openCustom(); return; }
        if (v === 'current') return;
        fs.mode = v;
        scheduleChanged();
      }
    });
    var repeatField = App.ui.field({
      label: 'Repeat', control: repeatSelect, hintTestid: 'routine-form-schedule-hint'
    });
    root.appendChild(repeatField.el);

    var preview = App.ui.status({ state: 'idle', led: false, testid: 'routine-form-preview' });
    preview.el.classList.add('routine-form-preview');
    preview.el.hidden = true;
    root.appendChild(preview.el);
    root.appendChild(scheduleError.el);

    // The schedule error line names the control it concerns: aria-invalid plus its id in
    // that control's aria-describedby (re-applied after the Repeat field rewrites its own
    // hint ids).
    var errorTarget = null;
    var rawShow = scheduleError.show;
    var rawSetHint = repeatField.setHint;
    if (!scheduleError.el.id) scheduleError.el.id = App.ui.util.uid('routine-schedule-error');
    function errorControl(msg) {
      if (!fs.startDate) return startDate.input;
      if (!fs.startTime) return startTime.input;
      return /\bstart/i.test(msg) ? startDate.input : repeatSelect;
    }
    function applyScheduleA11y(msg) {
      if (errorTarget) {
        errorTarget.removeAttribute('aria-invalid');
        App.ui.util.removeDescribedBy(errorTarget, scheduleError.el.id);
        errorTarget = null;
      }
      if (msg) {
        errorTarget = errorControl(msg);
        errorTarget.setAttribute('aria-invalid', 'true');
        App.ui.util.addDescribedBy(errorTarget, scheduleError.el.id);
      }
    }
    var shownMsg = '';
    scheduleError.show = function (msg) {
      shownMsg = msg || '';
      rawShow(msg);
      applyScheduleA11y(shownMsg);
    };
    repeatField.setHint = function (m) {
      rawSetHint(m);
      if (errorTarget === repeatSelect) applyScheduleA11y(shownMsg);
    };

    // The Repeat options follow the start date; the selected preset keeps its meaning.
    function renderRepeat() {
      var opts = model.presets(fs.startDate || lastStart);
      if (fs.mode === 'current') {
        opts.push({ value: 'current', label: fs.currentLabel || 'Custom recurrence' });
      }
      opts.push({ value: 'custom', label: 'Custom…' });
      repeatSelect.textContent = '';
      opts.forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o.value;
        opt.textContent = o.label;
        repeatSelect.appendChild(opt);
      });
      repeatSelect.value = fs.mode;
    }

    function startChanged() {
      fs.mode = model.availableMode(fs.mode, fs.startDate || lastStart);
      renderRepeat();
      scheduleChanged();
    }

    function scheduleChanged() {
      scheduleError.show('');
      previewSoon(PREVIEW_DELAY_MS);
    }

    function applyIn() {
      var n = /^\d+$/.test(inAmount.value.trim()) ? parseInt(inAmount.value, 10) : 0;
      if (n < 1) return;
      var s = model.startFromIn(Date.now(), n, inUnit.select.value, App.time.parts);
      fs.startDate = s.date;
      fs.startTime = s.time;
      lastStart = s.date;
      startDate.setValue(s.date);
      startTime.setValue(s.time);
      startChanged();
    }

    function openCustom() {
      var base = fs.startDate || lastStart;
      customModal = App.studio.routinesCustomRecurrence.open({
        startDate: base,
        value: { repeat: model.effectiveRepeat(fs), ends: model.effectiveEnds(fs) },
        today: todayIso, opener: repeatSelect,
        onApply: function (v) {
          var key = model.matchPreset(v.repeat, v.ends, base);
          fs.mode = key || 'current';
          fs.repeat = v.repeat;
          fs.ends = v.ends;
          fs.currentLabel = '';
        },
        onClose: function () {
          customModal = null;
          if (done) return;
          renderRepeat();
          scheduleChanged();
        }
      });
    }

    // ── The preview line ──────────────────────────────────────────────
    function previewCall(schedule) {
      if (typeof cbs.previewSchedule === 'function') return cbs.previewSchedule(req.agent, schedule);
      return App.api.fetchJson(
        '/api/agents/' + encodeURIComponent(req.agent) + '/routines/preview',
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ schedule: schedule }) }
      );
    }
    function clearPreview() {
      preview.set('idle', '');
      preview.el.hidden = true;
      repeatField.setHint(null);
    }
    function previewSoon(delay) {
      if (previewTimer) clearTimeout(previewTimer);
      previewTimer = setTimeout(runPreview, delay);
    }
    function runPreview() {
      previewTimer = null;
      if (done) return;
      if (!fs.startDate || !fs.startTime) {
        latest.invalidate();
        clearPreview();
        return;
      }
      var token = latest.next();
      Promise.resolve(previewCall(model.scheduleBody(fs))).then(function (res) {
        if (done || !latest.isCurrent(token)) return;
        scheduleError.show('');
        preview.set('idle', describe.describePreview(res));
        preview.el.hidden = false;
        repeatField.setHint(res.warnings && res.warnings.length ? res.warnings.join(' ') : null);
        if (fs.mode === 'current' && res.text && fs.currentLabel !== res.text) {
          fs.currentLabel = res.text;
          renderRepeat();
        }
      }, function (err) {
        if (done || !latest.isCurrent(token)) return;
        var mapped = App.api.fieldErrors(err, ['schedule']);
        clearPreview();
        scheduleError.show(mapped.fields.schedule || mapped.text);
      });
    }
    renderRepeat();
    previewSoon(0);

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

    // Show the chosen-chat line only for the "A chat" target.
    function refresh() {
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
      if (previewTimer) clearTimeout(previewTimer);
      latest.invalidate();
      if (customModal) customModal.close(null);
      startDate.destroy();
      startTime.destroy();
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
        first = first || (!fs.startDate ? startDate : !fs.startTime ? startTime : repeatSelect);
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
      var pre = model.precheck(fs, ctx, limits);
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
