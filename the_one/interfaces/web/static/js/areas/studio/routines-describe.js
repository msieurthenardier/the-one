// App.studio.routinesDescribe -- pure display helpers for a routine (M33 F1 L8). Used by the
// Routines tab and by the create/edit form (leg 9). The schedule sentence is the server's
// (`schedule_text`); nothing here words a schedule. Every time goes through App.time (the
// operator's zone); nothing here reads a Date getter. Output is plain text: callers write it
// with textContent.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function dateOf(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  // A moment, short: the clock today, "Wed 9:00 AM" within the last six days, else
  // "Oct 3, 9:00 AM". `now` is injectable for tests.
  function describeWhen(iso, now) {
    var d = dateOf(iso);
    if (!d) return '';
    var diff = App.time.dayNumber(now || new Date()) - App.time.dayNumber(d);
    var p = App.time.parts(d);
    var clock = App.time.formatClock(d);
    if (diff === 0) return clock;
    if (diff > 0 && diff <= 6) return WEEKDAYS[p.weekday] + ' ' + clock;
    return MONTHS[p.month] + ' ' + p.day + ', ' + clock;
  }

  // The row's next-run cell. Precedence: Done, Off, then the moment: "Today 8:30 PM",
  // "Tomorrow 9:00 AM", "Fri 9:00 AM" within the week, else "Nov 3, 9:00 AM".
  function describeNext(row, now) {
    if (row.finished_at) return 'Done';
    if (!row.enabled) return 'Off';
    var d = dateOf(row.next_run_at);
    if (!d) return 'Not scheduled';
    var diff = App.time.dayNumber(d) - App.time.dayNumber(now || new Date());
    var clock = App.time.formatClock(d);
    if (diff === 0) return 'Today ' + clock;
    if (diff === 1) return 'Tomorrow ' + clock;
    if (diff > 1 && diff <= 6) return WEEKDAYS[App.time.parts(d).weekday] + ' ' + clock;
    return describeWhen(row.next_run_at, now);
  }

  // A run instant for the form's preview line: "Fri, Oct 30 at 9:00 AM" (the year joins
  // when it is not the current one), in the operator zone.
  function describeRunAt(iso, now) {
    var d = dateOf(iso);
    if (!d) return '';
    var p = App.time.parts(d);
    var year = App.time.parts(now || new Date()).year;
    return WEEKDAYS[p.weekday] + ', ' + MONTHS[p.month] + ' ' + p.day +
      (p.year !== year ? ', ' + p.year : '') + ' at ' + App.time.formatClock(d);
  }

  // The preview line: the server's sentence, the next run, and the last occurrence when
  // the series ends: "Every day at 9:00 AM · Next: Fri, Oct 30 at 9:00 AM · Last: Jan 28, 2027".
  function describePreview(res, now) {
    if (!res) return '';
    var out = res.text || '';
    var next = res.next_runs && res.next_runs[0];
    // An "Immediately" start: the first run is the save itself (M33 F4 L4).
    if (res.immediate) out += (out ? ' · ' : '') + 'First run: when you save';
    else if (next) out += (out ? ' \u00b7 ' : '') + 'Next: ' + describeRunAt(next, now);
    var last = dateOf(res.last_occurrence);
    if (last) out += ' \u00b7 Last: ' + App.time.formatDate(last);
    return out;
  }

  // The form's "In N units" result: "Today at 9:52 PM", "Tomorrow at 9:00 AM", else the
  // run-at wording, for an instant (ms) in the operator zone.
  function describeStartAt(ms, now) {
    var d = new Date(ms);
    var diff = App.time.dayNumber(d) - App.time.dayNumber(now || new Date());
    if (diff === 0) return 'Today at ' + App.time.formatClock(d);
    if (diff === 1) return 'Tomorrow at ' + App.time.formatClock(d);
    return describeRunAt(d.toISOString(), now);
  }

  var OUTCOMES = {
    ok: { state: 'success', verb: 'Ran' },
    failed: { state: 'danger', verb: 'Failed' },
    skipped: { state: 'warning', verb: 'Skipped' },
    missed: { state: 'warning', verb: 'Missed' },
    interrupted: { state: 'warning', verb: 'Interrupted' },
    stopped: { state: 'idle', verb: 'Stopped' }
  };

  // The outcome of a run-shaped value ({outcome, reason, finished_at, started_at, due_at}) or
  // null (never run), in parts: {state, verb, when, reason, label, text}. `label` is the verb
  // and the time ("Ran Thu 9:00 AM": the row's last-run cell), `text` the verb and the stored
  // reason, once ("Skipped: the previous run was still going": a run's line). A reason that
  // already opens with the verb stands alone, so the verb is never repeated. `running` forces
  // Running (a live row).
  function outcomeStatus(run, running) {
    if (running || (run && run.outcome === 'running')) {
      return { state: 'pending', verb: 'Running', when: '', reason: '', label: 'Running…', text: 'Running…' };
    }
    var o = run && OUTCOMES[run.outcome];
    if (!o) {
      return { state: 'idle', verb: '', when: '', reason: '', label: 'Not run yet', text: 'Not run yet' };
    }
    var when = describeWhen(run.finished_at || run.started_at || run.due_at);
    var reason = run.reason ? String(run.reason) : '';
    var opens = reason.toLowerCase().indexOf(o.verb.toLowerCase()) === 0;
    return {
      state: o.state, verb: o.verb, when: when, reason: reason,
      label: o.verb + (when ? ' ' + when : ''),
      text: !reason ? o.verb : (opens ? reason : o.verb + ': ' + reason)
    };
  }

  var TRIGGERS = { schedule: 'Scheduled', catch_up: 'Caught up', manual: 'Run now' };
  function describeTrigger(kind) { return TRIGGERS[kind] || ''; }

  window.App.studio.routinesDescribe = {
    describeNext: describeNext,
    describeWhen: describeWhen,
    describeRunAt: describeRunAt,
    describePreview: describePreview,
    describeStartAt: describeStartAt,
    describeTrigger: describeTrigger,
    outcomeStatus: outcomeStatus
  };
})();
