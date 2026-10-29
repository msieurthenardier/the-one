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

  function describeTarget(target) {
    if (!target) return '';
    if (target.kind === 'new') return 'New chat each run';
    if (target.kind === 'own') return 'Its own chat';
    if (target.missing) return 'Chat gone, a new one starts on the next run';
    var text = target.title || 'Untitled chat';
    if (target.platform) text += ' · ' + App.chat.chatsList.platformName(target.platform);
    return text;
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

  // The row's next-run line. Precedence: Running, Done, Off, Next.
  function describeNext(row) {
    if (row.running) return 'Running';
    if (row.finished_at) return 'Done';
    if (!row.enabled) return 'Off';
    var d = dateOf(row.next_run_at);
    if (!d) return 'Not scheduled';
    return 'Next ' + WEEKDAYS[App.time.parts(d).weekday] + ' ' + App.time.formatClock(d);
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
    if (next) out += (out ? ' \u00b7 ' : '') + 'Next: ' + describeRunAt(next, now);
    var last = dateOf(res.last_occurrence);
    if (last) out += ' \u00b7 Last: ' + App.time.formatDate(last);
    return out;
  }

  // {state, label} for an App.ui.status from a run-shaped value ({outcome, reason, finished_at,
  // started_at}) or null (never run). `running` forces Running (a live row).
  function outcomeStatus(run, running) {
    if (running || (run && run.outcome === 'running')) return { state: 'pending', label: 'Running' };
    if (!run) return { state: 'idle', label: 'Not run yet' };
    var when = describeWhen(run.finished_at || run.started_at || run.due_at);
    var reason = run.reason ? ': ' + run.reason : '';
    switch (run.outcome) {
      case 'ok': return { state: 'success', label: 'Ran ' + when };
      case 'failed': return { state: 'danger', label: 'Failed ' + when + reason };
      case 'skipped': return { state: 'warning', label: 'Skipped ' + when + reason };
      case 'missed': return { state: 'warning', label: 'Missed' + reason };
      case 'interrupted': return { state: 'warning', label: 'Interrupted ' + when };
      case 'stopped': return { state: 'idle', label: 'Stopped ' + when };
      default: return { state: 'idle', label: 'Not run yet' };
    }
  }

  var TRIGGERS = { schedule: 'Scheduled', catch_up: 'Caught up', manual: 'Run now' };
  function describeTrigger(kind) { return TRIGGERS[kind] || ''; }

  window.App.studio.routinesDescribe = {
    describeTarget: describeTarget,
    describeNext: describeNext,
    describeWhen: describeWhen,
    describeRunAt: describeRunAt,
    describePreview: describePreview,
    describeTrigger: describeTrigger,
    outcomeStatus: outcomeStatus
  };
})();
