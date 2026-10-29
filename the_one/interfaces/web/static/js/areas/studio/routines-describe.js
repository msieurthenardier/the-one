// App.studio.routinesDescribe -- pure display helpers for a routine (M33 F1 L8). Used by the
// Routines tab and by the create/edit form (leg 9). Every time goes through App.time (the
// operator's zone); nothing here reads a Date getter. Output is plain text: callers write it
// with textContent.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  // The server numbers days 0 = Monday ... 6 = Sunday.
  var SCHEDULE_DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  // "09:30" -> "9:30 AM" (a wall time already in the operator zone).
  function clockOfHhmm(hhmm) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || ''));
    if (!m) return String(hhmm || '');
    var hour = parseInt(m[1], 10);
    var h = hour % 12;
    if (h === 0) h = 12;
    return h + ':' + m[2] + ' ' + (hour < 12 ? 'AM' : 'PM');
  }

  function dateOf(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function describeSchedule(schedule) {
    if (!schedule || typeof schedule !== 'object') return '';
    switch (schedule.kind) {
      case 'daily':
        return 'Daily at ' + clockOfHhmm(schedule.time);
      case 'weekdays':
        return 'Weekdays at ' + clockOfHhmm(schedule.time);
      case 'weekly': {
        var days = (schedule.days || []).slice().sort(function (a, b) { return a - b; })
          .map(function (n) { return SCHEDULE_DAYS[n] || String(n); });
        return days.join(', ') + ' at ' + clockOfHhmm(schedule.time);
      }
      case 'interval': {
        var n = schedule.hours;
        return n === 1 ? 'Every hour' : 'Every ' + n + ' hours';
      }
      case 'once': {
        var d = dateOf(schedule.at);
        if (!d) return 'Once';
        var p = App.time.parts(d);
        return 'Once, ' + WEEKDAYS[p.weekday] + ' ' + MONTHS[p.month] + ' ' + p.day +
          ' at ' + App.time.formatClock(d);
      }
      default:
        return '';
    }
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
    describeSchedule: describeSchedule,
    describeTarget: describeTarget,
    describeNext: describeNext,
    describeWhen: describeWhen,
    describeTrigger: describeTrigger,
    outcomeStatus: outcomeStatus
  };
})();
