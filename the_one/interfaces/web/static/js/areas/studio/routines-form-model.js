// App.studio.routinesFormModel -- the pure model behind the routine create/edit form
// (M33 F1 L9, flight DD12). No DOM, no network. Every date and time is a plain value in the
// operator's zone; the one place a Date is built is the calendar walk in `dayOptions`, which
// uses UTC arithmetic on a date with no time of day (no Date getter of local time is read).
//
// Form state (all fields always present; only the active kind's fields are sent):
//   { name, prompt, kind: 'once'|'daily'|'weekdays'|'weekly'|'interval',
//     hour (1-12), minute (0-59), ampm ('AM'|'PM'),            daily / weekdays / weekly time
//     days [0..6] (Monday = 0, as the server numbers them),     weekly
//     onceMode 'in'|'at', inAmount, inUnit, atDay 'YYYY-MM-DD',
//     atHour, atMinute, atAmpm,                                 once
//     interval,                                                 every N hours
//     targetKind 'chat'|'new'|'own', chatId, chatLabel }        target
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  var DAY_COUNT = 60;

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  // 12-hour clock to the server's 24-hour "HH:MM".
  function to24(hour, minute, ampm) {
    var h = (parseInt(hour, 10) || 12) % 12;
    if (ampm === 'PM') h += 12;
    return pad2(h) + ':' + pad2(parseInt(minute, 10) || 0);
  }

  // 24-hour hour/minute to {hour (1-12), minute, ampm}.
  function from24(h24, minute) {
    var h = h24 % 12;
    return { hour: h === 0 ? 12 : h, minute: minute, ampm: h24 < 12 ? 'AM' : 'PM' };
  }

  function dateString(y, m, d) { return y + '-' + pad2(m + 1) + '-' + pad2(d); }

  function defaultState(todayParts) {
    var days = dayOptions(todayParts, null);
    return {
      name: '', prompt: '', kind: 'daily',
      hour: 9, minute: 0, ampm: 'AM', days: [],
      onceMode: 'in', inAmount: 1, inUnit: 'hours',
      atDay: days.length > 1 ? days[1].value : (days[0] ? days[0].value : ''),
      atHour: 9, atMinute: 0, atAmpm: 'AM',
      interval: 6,
      targetKind: 'new', chatId: null, chatLabel: ''
    };
  }

  // The schedule part of a request body for the form state.
  function scheduleBody(s) {
    switch (s.kind) {
      case 'daily':
      case 'weekdays':
        return { kind: s.kind, time: to24(s.hour, s.minute, s.ampm) };
      case 'weekly':
        return {
          kind: 'weekly',
          days: (s.days || []).slice().sort(function (a, b) { return a - b; }),
          time: to24(s.hour, s.minute, s.ampm)
        };
      case 'interval':
        return { kind: 'interval', hours: parseInt(s.interval, 10) };
      case 'once':
        if (s.onceMode === 'in') {
          return { kind: 'once', 'in': { amount: parseInt(s.inAmount, 10), unit: s.inUnit } };
        }
        return { kind: 'once', on: { date: s.atDay, time: to24(s.atHour, s.atMinute, s.atAmpm) } };
      default:
        return { kind: s.kind };
    }
  }

  function targetBody(s) {
    if (s.targetKind === 'chat') return { kind: 'chat', session_id: s.chatId };
    return { kind: s.targetKind };
  }

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  // The request body. Create sends name, prompt, schedule and target. Edit sends only what
  // changed against `initial` (the state the form opened with): a changed-then-reverted
  // field counts as untouched, so a past one-off awaiting catch-up is not re-validated.
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
    if (prompt !== String(initial.prompt || '').trim()) body.prompt = prompt;
    if (!same(scheduleBody(state), scheduleBody(initial))) body.schedule = scheduleBody(state);
    if (!same(targetBody(state), targetBody(initial))) body.target = targetBody(state);
    return body;
  }

  // Form state from a routine row. `zoneParts(date)` is App.time.parts (the operator zone).
  function bodyToFormState(row, zoneParts, todayParts) {
    var s = defaultState(todayParts || zoneParts(new Date()));
    s.name = row.name || '';
    s.prompt = row.prompt || '';
    var sch = row.schedule || {};
    s.kind = sch.kind || 'daily';
    var t;
    if (sch.kind === 'daily' || sch.kind === 'weekdays' || sch.kind === 'weekly') {
      t = /^(\d{1,2}):(\d{2})$/.exec(sch.time || '');
      if (t) {
        var c = from24(parseInt(t[1], 10), parseInt(t[2], 10));
        s.hour = c.hour; s.minute = c.minute; s.ampm = c.ampm;
      }
      if (sch.kind === 'weekly') s.days = (sch.days || []).slice().sort(function (a, b) { return a - b; });
    } else if (sch.kind === 'interval') {
      s.interval = sch.hours;
    } else if (sch.kind === 'once') {
      s.onceMode = 'at';
      var at = new Date(sch.at);
      if (!isNaN(at.getTime())) {
        var p = zoneParts(at);
        s.atDay = dateString(p.year, p.month, p.day);
        var a = from24(p.hour, p.minute);
        s.atHour = a.hour; s.atMinute = a.minute; s.atAmpm = a.ampm;
      }
    }
    var tg = row.target || {};
    s.targetKind = tg.kind || 'new';
    if (s.targetKind === 'chat') {
      s.chatId = tg.session_id || null;
      s.chatLabel = tg.missing ? 'Chat gone' : (tg.title || 'Untitled chat');
    }
    return s;
  }

  // The next 60 days from today (operator zone) plus `extraDate` ('YYYY-MM-DD') when it is
  // outside that run, as [{value, label}] in date order.
  function dayOptions(todayParts, extraDate) {
    var out = [];
    var seen = {};
    for (var i = 0; i < DAY_COUNT; i++) {
      var d = new Date(Date.UTC(todayParts.year, todayParts.month, todayParts.day + i));
      var iso = d.toISOString().slice(0, 10);
      var label = WEEKDAYS[d.getUTCDay()] + ' ' + MONTHS[d.getUTCMonth()] + ' ' + d.getUTCDate();
      if (i === 0) label += ' (today)';
      else if (i === 1) label += ' (tomorrow)';
      out.push({ value: iso, label: label });
      seen[iso] = true;
    }
    if (extraDate && !seen[extraDate]) {
      var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(extraDate);
      if (m) {
        var e = new Date(Date.UTC(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10)));
        out.push({
          value: extraDate,
          label: WEEKDAYS[e.getUTCDay()] + ' ' + MONTHS[e.getUTCMonth()] + ' ' + e.getUTCDate() +
            ', ' + e.getUTCFullYear()
        });
        out.sort(function (a, b) { return a.value < b.value ? -1 : a.value > b.value ? 1 : 0; });
      }
    }
    return out;
  }

  // Hour 1-12 and minute (five-minute steps plus `extraMinute`) option lists.
  function hourMinuteOptions(extraMinute) {
    var hours = [];
    for (var h = 1; h <= 12; h++) hours.push({ value: h, label: String(h) });
    var mins = [];
    for (var m = 0; m < 60; m += 5) mins.push(m);
    if (typeof extraMinute === 'number' && mins.indexOf(extraMinute) === -1) {
      mins.push(extraMinute);
      mins.sort(function (a, b) { return a - b; });
    }
    return {
      hours: hours,
      minutes: mins.map(function (n) { return { value: n, label: pad2(n) }; })
    };
  }

  // Client-side checks run before a send (the server stays the authority). Returns
  // {name, prompt, schedule, target} messages; empty object when fine. `nowParts` is the
  // operator-zone parts of the present moment; `ctx` is formToBody's.
  function precheck(state, nowParts, ctx, limits) {
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
      var sc = body.schedule;
      if (sc.kind === 'weekly' && !sc.days.length) errors.schedule = 'Pick at least one day.';
      else if (sc.kind === 'interval' && !(sc.hours >= 1 && sc.hours <= ((limits && limits.interval_hours_max) || 168))) {
        errors.schedule = 'Hours must be a whole number from 1 to ' +
          ((limits && limits.interval_hours_max) || 168) + '.';
      } else if (sc.kind === 'once' && sc['in'] && !(sc['in'].amount >= 1)) {
        errors.schedule = 'Give a whole number of minutes, hours or days, at least 1.';
      } else if (sc.kind === 'once' && sc.on) {
        var nowKey = dateString(nowParts.year, nowParts.month, nowParts.day) + ' ' +
          pad2(nowParts.hour) + ':' + pad2(nowParts.minute);
        if (sc.on.date + ' ' + sc.on.time <= nowKey) errors.schedule = 'That time has already passed.';
      }
    }
    if (body.target && body.target.kind === 'chat' && !body.target.session_id) {
      errors.target = 'Pick a chat.';
    }
    return errors;
  }

  window.App.studio.routinesFormModel = {
    DAY_LABELS: DAY_LABELS,
    defaultState: defaultState,
    scheduleBody: scheduleBody,
    targetBody: targetBody,
    formToBody: formToBody,
    bodyToFormState: bodyToFormState,
    dayOptions: dayOptions,
    hourMinuteOptions: hourMinuteOptions,
    precheck: precheck,
    to24: to24
  };
})();
