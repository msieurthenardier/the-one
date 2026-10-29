// App.studio.routinesCustomRecurrence -- the "Custom recurrence" dialog of the routine form
// (M33 F3 L7, flight DD7): "Repeat every" N <unit>, "Repeat on" (weeks), a month choice
// (months), "Ends" (never / on a date / after N occurrences), Cancel and Done. Pure rules
// (ranges, the result shape) live in routines-form-model.js.
//
//   App.studio.routinesCustomRecurrence.open({startDate, value: {repeat, ends}, today,
//                                             opener, onApply(value), onClose(applied)})
//     -> the App.ui.modal controller. `value` is the recurrence the form holds now (a null
//        repeat opens on "every 1 week" on the start's weekday). Done validates, calls
//        onApply({repeat, ends}) once the dialog has closed, and Cancel / Escape discard.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var shared = window.App.studio.rulesNotesShared;
  var el = shared.el;
  var model = window.App.studio.routinesFormModel;

  // Sunday first, as the form shows S M T W T F S; values are the server's (Monday = 0).
  var DAY_ORDER = [6, 0, 1, 2, 3, 4, 5];
  var DAY_NAMES = { 0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday',
    5: 'Saturday', 6: 'Sunday' };
  var END_DEFAULT_DAYS = 30;
  var COUNT_DEFAULT = 13;

  function unitLabel(unit, n) { return unit + (n === 1 ? '' : 's'); }

  function monthKey(r) {
    if (!r || !r.month_by || r.month_by.by !== 'weekday') return 'day';
    return 'nth:' + r.month_by.nth;
  }

  function open(req) {
    req = req || {};
    var start = req.startDate;
    var startWeekday = model.weekdayMon0(start);
    var today = typeof req.today === 'function' ? req.today : undefined;
    var value = req.value || {};
    var repeat = model.cleanRepeat(value.repeat) ||
      { every: 1, unit: 'week', days: [startWeekday] };
    var ends = model.cleanEnds(value.ends);
    var applied = null;
    var modal = null;

    // The values the dialog edits, held as typed.
    var st = {
      every: String(repeat.every),
      unit: repeat.unit,
      days: (repeat.days && repeat.days.length ? repeat.days : [startWeekday]).slice(),
      monthBy: monthKey(repeat),
      endsKind: ends.kind,
      endsDate: ends.kind === 'on' ? ends.date : model.addDays(start, END_DEFAULT_DAYS),
      endsCount: String(ends.kind === 'after' ? ends.count : COUNT_DEFAULT)
    };

    var body = el('div', 'routine-custom-body');

    // ── Repeat every ──────────────────────────────────────────────────
    var everyInput = App.ui.textInput({
      type: 'number', min: 1, step: 1, width: 'short', value: st.every,
      testid: 'routine-custom-every',
      onInput: function () { st.every = everyInput.value; everyField.setError(null); relabelUnits(); }
    });
    var everyField = App.ui.field({
      label: 'Repeat every', control: everyInput, flush: true, errorTestid: 'routine-custom-every-error'
    });
    var unitSelect = App.ui.select({
      options: model.UNITS.map(function (u) { return { value: u, label: unitLabel(u, 2) }; }),
      value: st.unit, testid: 'routine-custom-unit',
      onChange: function (e) { st.unit = e.target.value; everyField.setError(null); relabelUnits(); showParts(); }
    });
    var unitField = App.ui.field({ label: 'Unit of time', labelHidden: true, control: unitSelect, flush: true });
    var everyRow = el('div', 'routine-custom-every');
    everyRow.appendChild(everyField.el);
    everyRow.appendChild(unitField.el);
    body.appendChild(everyRow);

    function relabelUnits() {
      var n = /^\d+$/.test(st.every.trim()) ? parseInt(st.every, 10) : 2;
      Array.prototype.forEach.call(unitSelect.options, function (o) {
        o.textContent = unitLabel(o.value, n);
      });
    }
    relabelUnits();

    // ── Repeat on (weeks) ─────────────────────────────────────────────
    var daysGroup = App.ui.checkboxGroup({
      legend: 'Repeat on', variant: 'days', testid: 'routine-custom-days', value: st.days,
      options: DAY_ORDER.map(function (v) {
        return { value: v, label: DAY_NAMES[v], short: DAY_NAMES[v].charAt(0), testid: 'routine-custom-day-' + v };
      }),
      onChange: function (v) { st.days = v; daysError.show(''); }
    });
    var daysError = shared.buildErrorLine();
    daysError.el.setAttribute('data-testid', 'routine-custom-days-error');
    var daysWrap = el('div', 'routine-custom-part');
    daysWrap.appendChild(daysGroup.el);
    daysWrap.appendChild(daysError.el);
    body.appendChild(daysWrap);

    // ── Month choice (months) ─────────────────────────────────────────
    var monthGroup = App.ui.radioGroup({
      legend: 'Repeat on day of month', name: 'routine-custom-month-by', value: st.monthBy,
      testid: 'routine-custom-month-by', options: model.monthByOptions(start, st.monthBy),
      onChange: function (v) { st.monthBy = v; }
    });
    var monthWrap = el('div', 'routine-custom-part');
    monthWrap.appendChild(monthGroup.el);
    body.appendChild(monthWrap);

    // ── Ends ──────────────────────────────────────────────────────────
    var endsDate = App.ui.datePicker({
      ariaLabel: 'End date', value: st.endsDate, min: start, today: today,
      testid: 'routine-custom-ends-date',
      onChange: function (iso) { st.endsDate = iso; endsError.show(''); }
    });
    var countInput = App.ui.textInput({
      type: 'number', min: 1, max: model.ENDS_COUNT_MAX, step: 1, width: 'short', value: st.endsCount,
      testid: 'routine-custom-ends-count',
      onInput: function () { st.endsCount = countInput.value; endsError.show(''); }
    });
    var countField = App.ui.field({
      label: 'Number of occurrences', labelHidden: true, control: countInput, flush: true
    });
    var endsGroup = App.ui.radioGroup({
      legend: 'Ends', name: 'routine-custom-ends', value: st.endsKind, testid: 'routine-custom-ends',
      options: [
        { value: 'never', label: 'Never' },
        { value: 'on', label: 'On' },
        { value: 'after', label: 'After' }
      ],
      onChange: function (v) { st.endsKind = v; endsError.show(''); showEnds(); }
    });
    endsGroup.optionEl('on').appendChild(endsDate.el);
    var afterRow = el('div', 'routine-custom-after');
    afterRow.appendChild(countField.el);
    afterRow.appendChild(el('span', 'routine-custom-after-text', 'occurrences'));
    endsGroup.optionEl('after').appendChild(afterRow);
    var endsError = shared.buildErrorLine();
    endsError.el.setAttribute('data-testid', 'routine-custom-ends-error');
    body.appendChild(endsGroup.el);
    body.appendChild(endsError.el);

    // Only the chosen Ends control is live; the others stay in place, disabled.
    function showEnds() {
      endsDate.setDisabled(st.endsKind !== 'on');
      countInput.disabled = st.endsKind !== 'after';
    }
    function showParts() {
      if (st.unit === 'week' && !st.days.length) {
        st.days = [startWeekday];
        daysGroup.setValue(st.days);
      }
      daysWrap.hidden = st.unit !== 'week';
      monthWrap.hidden = st.unit !== 'month';
    }
    showEnds();
    showParts();

    // ── Done / Cancel ─────────────────────────────────────────────────
    function done() {
      var errors = model.validateCustom(st, start);
      everyField.setError(errors.every || null);
      daysError.show(errors.days || '');
      endsError.show(errors.ends || '');
      if (errors.every) { everyInput.focus(); return; }
      if (errors.days) { daysGroup.focus(); return; }
      if (errors.ends) {
        if (st.endsKind === 'on') endsDate.focus(); else countInput.focus();
        return;
      }
      applied = model.customToValue(st);
      modal.close('done');
    }

    var doneBtn = App.ui.button({
      variant: 'primary', label: 'Done', testid: 'routine-custom-done', onClick: done
    });
    var cancelBtn = App.ui.button({
      variant: 'ghost', label: 'Cancel', testid: 'routine-custom-cancel',
      onClick: function () { modal.close(null); }
    });
    var actions = el('div', 'routine-custom-actions');
    actions.appendChild(cancelBtn);
    actions.appendChild(doneBtn);

    modal = App.ui.modal({
      title: 'Custom recurrence', width: 460, body: body, footerEnd: actions,
      initialFocus: everyInput, testid: 'routine-custom',
      onClose: function (v) {
        endsDate.destroy();
        daysGroup.destroy();
        monthGroup.destroy();
        endsGroup.destroy();
        var result = v === 'done' ? applied : null;
        if (result && typeof req.onApply === 'function') req.onApply(result);
        if (typeof req.onClose === 'function') req.onClose(!!result);
      }
    });
    modal.open(req.opener || null);
    return modal;
  }

  window.App.studio.routinesCustomRecurrence = { open: open };
})();
