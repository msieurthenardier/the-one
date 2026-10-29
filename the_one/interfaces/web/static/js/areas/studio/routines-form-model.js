// App.studio.routinesFormModel -- the pure model behind the routine create/edit form
// (M33 F1 L9, rebuilt on the calendar recurrence in M33 F3 L7, flight DD1/DD7). No DOM, no
// network, and no local-time Date getter: every date is a plain "YYYY-MM-DD" string in the
// operator's zone, and the calendar arithmetic uses UTC math on a date with no time of day.
//
// Form state:
//   { name, prompt,
//     startDate 'YYYY-MM-DD'|null, startTime 'HH:MM'|null,       the start (operator zone)
//     mode,                a Repeat preset key (PRESET_KEYS) or 'current'
//     repeat, ends,        the recurrence held when mode is 'current' (a Custom result or an
//                          existing routine that matches no preset); ignored for a preset
//     currentLabel,        the sentence shown for mode 'current'
//     targetKind 'chat'|'new'|'own', chatId, chatLabel }
// A preset is stored as a KEY, not a value, so it keeps its meaning when the start date moves
// ("Weekly on Thursday" follows the new weekday, as Google Calendar does).
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
    'September', 'October', 'November', 'December'];
  var ORDINALS = { 1: 'first', 2: 'second', 3: 'third', 4: 'fourth', '-1': 'last' };
  var UNITS = ['minute', 'hour', 'day', 'week', 'month', 'year'];
  // The DD1 ranges (the server is the authority; these give the dialog its field errors).
  var EVERY_MAX = { minute: 1439, hour: 168, day: 365, week: 52, month: 12, year: 10 };
  var ENDS_COUNT_MAX = 1000;
  var PRESET_KEYS = ['none', 'day', 'weekday', 'weekly', 'monthday', 'monthnth', 'monthlast',
    'annual'];

  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  // ── Calendar arithmetic on ISO dates ──────────────────────────────────

  function parseIso(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
    return m ? { y: parseInt(m[1], 10), m: parseInt(m[2], 10) - 1, d: parseInt(m[3], 10) } : null;
  }
  function isoOf(y, m, d) {
    return new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10);
  }
  function addDays(iso, n) {
    var p = parseIso(iso);
    return p ? isoOf(p.y, p.m, p.d + n) : null;
  }
  // Monday = 0 ... Sunday = 6, as the server numbers them.
  function weekdayMon0(iso) {
    var p = parseIso(iso);
    return (new Date(Date.UTC(p.y, p.m, p.d)).getUTCDay() + 6) % 7;
  }
  function daysInMonth(y, m) { return new Date(Date.UTC(y, m + 1, 0)).getUTCDate(); }
  function nameOfWeekday(mon0) { return WEEKDAYS[(mon0 + 1) % 7]; }
  // The nth (1-5) of this weekday in its month, and whether it is in the last 7 days.
  function nthOf(iso) { return Math.ceil(parseIso(iso).d / 7); }
  function isLastWeek(iso) {
    var p = parseIso(iso);
    return p.d > daysInMonth(p.y, p.m) - 7;
  }

  // ── Repeat presets, computed from the start date ──────────────────────

  // The presets that apply to `startIso`, in Google's order: [{value, label}].
  function presets(startIso) {
    var p = parseIso(startIso);
    if (!p) return [{ value: 'none', label: 'Does not repeat' }];
    var wd = nameOfWeekday(weekdayMon0(startIso));
    var out = [
      { value: 'none', label: 'Does not repeat' },
      { value: 'day', label: 'Every day' },
      { value: 'weekday', label: 'Every weekday (Monday to Friday)' },
      { value: 'weekly', label: 'Weekly on ' + wd },
      { value: 'monthday', label: 'Monthly on day ' + p.d }
    ];
    var nth = nthOf(startIso);
    if (nth <= 4) {
      out.push({ value: 'monthnth', label: 'Monthly on the ' + ORDINALS[nth] + ' ' + wd });
    }
    if (isLastWeek(startIso)) {
      out.push({ value: 'monthlast', label: 'Monthly on the last ' + wd });
    }
    out.push({ value: 'annual', label: 'Annually on ' + MONTHS[p.m] + ' ' + p.d });
    return out;
  }

  // The repeat object a preset means for `startIso` (null for "Does not repeat"), or
  // undefined when the preset does not apply to that date.
  function presetRepeat(key, startIso) {
    switch (key) {
      case 'none': return null;
      case 'day': return { every: 1, unit: 'day' };
      case 'weekday': return { every: 1, unit: 'week', days: [0, 1, 2, 3, 4] };
      case 'weekly': return { every: 1, unit: 'week', days: [weekdayMon0(startIso)] };
      case 'monthday': return { every: 1, unit: 'month', month_by: { by: 'day' } };
      case 'monthnth':
        return nthOf(startIso) <= 4
          ? { every: 1, unit: 'month', month_by: { by: 'weekday', nth: nthOf(startIso) } }
          : undefined;
      case 'monthlast':
        return isLastWeek(startIso)
          ? { every: 1, unit: 'month', month_by: { by: 'weekday', nth: -1 } }
          : undefined;
      case 'annual': return { every: 1, unit: 'year' };
      default: return undefined;
    }
  }

  // A preset that no longer applies to a moved start date falls back to its family.
  function availableMode(mode, startIso) {
    if (mode === 'current') return mode;
    if (!parseIso(startIso)) return mode;
    return presetRepeat(mode, startIso) === undefined ? 'monthday' : mode;
  }

  // A repeat in one fixed key order and form (so two equal recurrences compare equal).
  function cleanRepeat(r) {
    if (!r) return null;
    var out = { every: parseInt(r.every, 10), unit: r.unit };
    if (r.unit === 'week' && Array.isArray(r.days)) {
      var days = [];
      r.days.forEach(function (d) { if (days.indexOf(d) === -1) days.push(d); });
      out.days = days.sort(function (a, b) { return a - b; });
    }
    if (r.unit === 'month' && r.month_by) {
      out.month_by = r.month_by.by === 'weekday'
        ? { by: 'weekday', nth: parseInt(r.month_by.nth, 10) }
        : { by: 'day' };
    }
    return out;
  }
  function cleanEnds(e) {
    if (!e || e.kind === 'never' || !e.kind) return { kind: 'never' };
    if (e.kind === 'on') return { kind: 'on', date: e.date };
    return { kind: 'after', count: parseInt(e.count, 10) };
  }

  // The preset key that means exactly this recurrence for `startIso`, or null.
  function matchPreset(repeat, ends, startIso) {
    if (cleanEnds(ends).kind !== 'never' || !parseIso(startIso)) return null;
    var rep = cleanRepeat(repeat);
    for (var i = 0; i < PRESET_KEYS.length; i++) {
      var want = presetRepeat(PRESET_KEYS[i], startIso);
      if (want !== undefined && same(rep, want)) return PRESET_KEYS[i];
    }
    return null;
  }

  function effectiveRepeat(state) {
    if (state.mode === 'current') return cleanRepeat(state.repeat);
    var r = presetRepeat(state.mode, state.startDate);
    return r === undefined ? null : r;
  }
  function effectiveEnds(state) {
    return state.mode === 'current' ? cleanEnds(state.ends) : { kind: 'never' };
  }

  // The "Month" choices of the Custom dialog for the start date: [{value, label}], values
  // 'day' or 'nth:N'. `currentKey` is added when the stored nth is not one of the start's.
  function monthByOptions(startIso, currentKey) {
    var p = parseIso(startIso);
    var wd = nameOfWeekday(weekdayMon0(startIso));
    var out = [{ value: 'day', label: 'On day ' + p.d }];
    var nth = nthOf(startIso);
    if (nth <= 4) out.push({ value: 'nth:' + nth, label: 'On the ' + ORDINALS[nth] + ' ' + wd });
    if (isLastWeek(startIso)) out.push({ value: 'nth:-1', label: 'On the last ' + wd });
    if (currentKey && currentKey !== 'day' && !out.some(function (o) { return o.value === currentKey; })) {
      var n = parseInt(currentKey.slice(4), 10);
      if (ORDINALS[n]) out.push({ value: currentKey, label: 'On the ' + ORDINALS[n] + ' ' + wd });
    }
    return out;
  }

  // ── Starts ────────────────────────────────────────────────────────────

  // The next whole hour in the operator zone, after `nowMs`: {date, time}.
  function defaultStart(nowMs, zoneParts) {
    var p = zoneParts(new Date(nowMs));
    var t = Math.floor(nowMs / 60000) * 60000 + (60 - p.minute) * 60000;
    var q = zoneParts(new Date(t));
    return { date: isoOf(q.year, q.month, q.day), time: pad2(q.hour) + ':' + pad2(q.minute) };
  }

  // Now plus an amount, rounded up to the minute, as {date, time} in the operator zone.
  function startFromIn(nowMs, amount, unit, zoneParts) {
    var ms = unit === 'minutes' ? 60000 : unit === 'hours' ? 3600000 : 86400000;
    var t = Math.ceil((nowMs + amount * ms) / 60000) * 60000;
    var q = zoneParts(new Date(t));
    return { date: isoOf(q.year, q.month, q.day), time: pad2(q.hour) + ':' + pad2(q.minute) };
  }

  // ── State and body ────────────────────────────────────────────────────

  function defaultState(nowMs, zoneParts) {
    var st = defaultStart(nowMs, zoneParts);
    return {
      name: '', prompt: '', startDate: st.date, startTime: st.time,
      mode: 'none', repeat: null, ends: { kind: 'never' }, currentLabel: '',
      targetKind: 'new', chatId: null, chatLabel: ''
    };
  }

  // The schedule part of a request body for the form state: always the canonical shape.
  function scheduleBody(s) {
    return {
      start: { date: s.startDate, time: s.startTime },
      repeat: effectiveRepeat(s),
      ends: effectiveEnds(s)
    };
  }

  function targetBody(s) {
    if (s.targetKind === 'chat') return { kind: 'chat', session_id: s.chatId };
    return { kind: s.targetKind };
  }

  // The request body. Create sends name, prompt, schedule and target. Edit sends only what
  // changed against `initial` (the state the form opened with): a changed-then-reverted
  // field counts as untouched, so a stored schedule is never re-sent unchanged.
  function formToBody(state, ctx) {
    var mode = ctx && ctx.mode;
    var initial = ctx && ctx.initial;
    var name = String(state.name || '').trim();
    var prompt = String(state.prompt || '').trim();
    if (mode !== 'edit' || !initial) {
      return { name: name, prompt: prompt, schedule: scheduleBody(state), target: targetBody(state) };
    }
    var body = {};
    if (name !== String(initial.name || '').trim()) body.name = name;
    // Saving a flagged routine's form is the operator's review (M33 F2 DD7): the prompt is
    // always sent, so the server clears the flag even when the text is unchanged.
    if (ctx.flagged || prompt !== String(initial.prompt || '').trim()) body.prompt = prompt;
    if (!same(scheduleBody(state), scheduleBody(initial))) body.schedule = scheduleBody(state);
    if (!same(targetBody(state), targetBody(initial))) body.target = targetBody(state);
    return body;
  }

  // Form state from a routine row (the canonical schedule the server stores and returns).
  function bodyToFormState(row) {
    var sch = row.schedule || {};
    var start = sch.start || {};
    var rep = cleanRepeat(sch.repeat);
    var ends = cleanEnds(sch.ends);
    var key = matchPreset(rep, ends, start.date);
    var s = {
      name: row.name || '', prompt: row.prompt || '',
      startDate: start.date || null, startTime: start.time || null,
      mode: key || 'current', repeat: rep, ends: ends,
      currentLabel: key ? '' : (row.schedule_text || ''),
      targetKind: 'new', chatId: null, chatLabel: ''
    };
    var tg = row.target || {};
    s.targetKind = tg.kind || 'new';
    if (s.targetKind === 'chat') {
      s.chatId = tg.session_id || null;
      s.chatLabel = tg.missing ? 'Chat gone' : (tg.title || 'Untitled chat');
    }
    return s;
  }

  // Check a Custom recurrence's numbers against the DD1 ranges. `v` is
  // {every (string|number), unit, days, endsKind, endsDate, endsCount (string|number)};
  // returns {every, days, ends} messages (an empty object when fine).
  function validateCustom(v, startIso) {
    var errors = {};
    var max = EVERY_MAX[v.unit];
    var every = /^\d+$/.test(String(v.every).trim()) ? parseInt(v.every, 10) : NaN;
    if (!(every >= 1 && every <= max)) {
      errors.every = 'Repeat every must be a whole number from 1 to ' + max + '.';
    }
    if (v.unit === 'week' && !(v.days && v.days.length)) errors.days = 'Pick at least one day.';
    if (v.endsKind === 'on') {
      if (!parseIso(v.endsDate)) errors.ends = 'Pick an end date.';
      else if (v.endsDate < startIso) errors.ends = 'The end date must be on or after the start.';
    } else if (v.endsKind === 'after') {
      var count = /^\d+$/.test(String(v.endsCount).trim()) ? parseInt(v.endsCount, 10) : NaN;
      if (!(count >= 1 && count <= ENDS_COUNT_MAX)) {
        errors.ends = 'The number of occurrences must be a whole number from 1 to ' +
          ENDS_COUNT_MAX + '.';
      }
    }
    return errors;
  }

  // The repeat and ends the Custom dialog builds from valid values.
  function customToValue(v) {
    var repeat = { every: parseInt(v.every, 10), unit: v.unit };
    if (v.unit === 'week') repeat.days = v.days.slice().sort(function (a, b) { return a - b; });
    if (v.unit === 'month') {
      repeat.month_by = v.monthBy === 'day' || !v.monthBy
        ? { by: 'day' }
        : { by: 'weekday', nth: parseInt(String(v.monthBy).slice(4), 10) };
    }
    var ends = { kind: 'never' };
    if (v.endsKind === 'on') ends = { kind: 'on', date: v.endsDate };
    else if (v.endsKind === 'after') ends = { kind: 'after', count: parseInt(v.endsCount, 10) };
    return { repeat: repeat, ends: ends };
  }

  // Client-side checks run before a send (the server stays the authority). Returns
  // {name, prompt, schedule, target} messages; empty object when fine. `ctx` is formToBody's.
  function precheck(state, ctx, limits) {
    var errors = {};
    var body = formToBody(state, ctx);
    var edit = ctx && ctx.mode === 'edit';
    if (!edit || 'name' in body) {
      if (!String(state.name || '').trim()) errors.name = 'Give the routine a name.';
    }
    if (!edit || 'prompt' in body) {
      var p = String(state.prompt || '').trim();
      if (!p) errors.prompt = 'The prompt cannot be empty.';
      else if (limits && limits.prompt_chars && p.length > limits.prompt_chars) {
        errors.prompt = 'The prompt is limited to ' + limits.prompt_chars + ' characters.';
      }
    }
    if (body.schedule) {
      if (!state.startDate) errors.schedule = 'Choose a start date.';
      else if (!state.startTime) errors.schedule = 'Enter a start time like 9:30 AM.';
    }
    if (body.target && body.target.kind === 'chat' && !body.target.session_id) {
      errors.target = 'Pick a chat.';
    }
    return errors;
  }

  window.App.studio.routinesFormModel = {
    WEEKDAYS: WEEKDAYS,
    UNITS: UNITS,
    EVERY_MAX: EVERY_MAX,
    ENDS_COUNT_MAX: ENDS_COUNT_MAX,
    PRESET_KEYS: PRESET_KEYS,
    parseIso: parseIso,
    isoOf: isoOf,
    addDays: addDays,
    weekdayMon0: weekdayMon0,
    nameOfWeekday: nameOfWeekday,
    nthOf: nthOf,
    isLastWeek: isLastWeek,
    presets: presets,
    presetRepeat: presetRepeat,
    availableMode: availableMode,
    cleanRepeat: cleanRepeat,
    cleanEnds: cleanEnds,
    matchPreset: matchPreset,
    effectiveRepeat: effectiveRepeat,
    effectiveEnds: effectiveEnds,
    monthByOptions: monthByOptions,
    defaultStart: defaultStart,
    startFromIn: startFromIn,
    defaultState: defaultState,
    scheduleBody: scheduleBody,
    targetBody: targetBody,
    formToBody: formToBody,
    bodyToFormState: bodyToFormState,
    validateCustom: validateCustom,
    customToValue: customToValue,
    precheck: precheck
  };
})();
