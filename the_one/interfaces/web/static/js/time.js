// App.time - operator-zone clock formatting (M25 F6 L4b DD14; zone-aware since M28 F2 L1).
// Every clock time, weekday and day grouping the app shows goes through parts(), which reads
// the operator's time zone (setZone) and falls back to the browser's local zone. Clock text is
// hand-formatted (never toLocaleString) so every engine and locale draws the same label.
// This is the ONLY module allowed to call the Date getters (tests/test_time_getters_static.py).
(function () {
  'use strict';

  var WEEKDAY_INDEX = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  var OFFSET_RE = /^([+-])(\d{2}):(\d{2})$/;

  var key = null;        // the effective zone key, or null for browser-local
  var fmt = null;        // cached Intl.DateTimeFormat for an IANA key
  var offsetMs = null;   // set for a hand-built offset key (no Intl)
  var listeners = [];

  function build(k) {
    // Returns {fmt, offsetMs} for a key, or throws RangeError.
    var m = OFFSET_RE.exec(k);
    if (m) {
      var mins = parseInt(m[2], 10) * 60 + parseInt(m[3], 10);
      return { fmt: null, offsetMs: (m[1] === '-' ? -1 : 1) * mins * 60000 };
    }
    return {
      fmt: new Intl.DateTimeFormat('en-US', {
        timeZone: k, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric',
        weekday: 'short', hour: 'numeric', minute: 'numeric'
      }),
      offsetMs: null
    };
  }

  function setZone(k) {
    var next = (typeof k === 'string' && k) ? k : null;
    var nextFmt = null;
    var nextOffset = null;
    if (next !== null) {
      try {
        var b = build(next);
        nextFmt = b.fmt;
        nextOffset = b.offsetMs;
      } catch (e) {
        if (typeof console !== 'undefined' && console.warn) {
          console.warn('App.time: unknown time zone "' + next + '"; using the browser zone');
        }
        next = null;
      }
    }
    if (next === key) return;
    key = next;
    fmt = nextFmt;
    offsetMs = nextOffset;
    var fns = listeners.slice();
    for (var i = 0; i < fns.length; i++) {
      try { fns[i](key); } catch (e2) { /* a listener must not break the others */ }
    }
  }

  function zone() { return key; }

  function onChange(fn) {
    listeners.push(fn);
    return function () {
      var i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    };
  }

  // {year, month (0-11), day, weekday (0-6, Sunday 0), hour (0-23), minute} in the zone.
  function parts(d) {
    if (key === null) {
      return {
        year: d.getFullYear(), month: d.getMonth(), day: d.getDate(),
        weekday: d.getDay(), hour: d.getHours(), minute: d.getMinutes()
      };
    }
    if (offsetMs !== null) {
      var u = new Date(d.getTime() + offsetMs);
      return {
        year: u.getUTCFullYear(), month: u.getUTCMonth(), day: u.getUTCDate(),
        weekday: u.getUTCDay(), hour: u.getUTCHours(), minute: u.getUTCMinutes()
      };
    }
    var out = {};
    var list = fmt.formatToParts(d);
    for (var i = 0; i < list.length; i++) out[list[i].type] = list[i].value;
    return {
      year: parseInt(out.year, 10),
      month: parseInt(out.month, 10) - 1,
      day: parseInt(out.day, 10),
      weekday: WEEKDAY_INDEX[out.weekday],
      hour: parseInt(out.hour, 10) % 24,
      minute: parseInt(out.minute, 10)
    };
  }

  function formatClock(d) {
    var p = parts(d);
    var h = p.hour % 12;
    if (h === 0) h = 12;
    return h + ':' + (p.minute < 10 ? '0' + p.minute : String(p.minute)) + ' ' +
      (p.hour < 12 ? 'AM' : 'PM');
  }

  // The calendar day in the zone as a whole number (days since 1970-01-01).
  function dayNumber(d) {
    var p = parts(d);
    return Date.UTC(p.year, p.month, p.day) / 86400000;
  }

  // The zone key from a GET /api/time-settings body. Prefers the canonical name, so it can
  // differ from a stored alias; an unnamed system zone with a "UTC+05:30" offset gives
  // "+05:30"; anything else (or a malformed body) gives null.
  function zoneFromSettings(s) {
    try {
      var e = s && s.effective;
      if (!e || typeof e !== 'object') return null;
      if (typeof e.canonical === 'string' && e.canonical) return e.canonical;
      if (typeof e.zone === 'string' && e.zone) return e.zone;
      var m = typeof e.offset === 'string' && /^UTC([+-]\d{2}:\d{2})$/.exec(e.offset);
      return m ? m[1] : null;
    } catch (err) {
      return null;
    }
  }

  window.App = window.App || {};
  window.App.time = {
    setZone: setZone,
    zone: zone,
    parts: parts,
    formatClock: formatClock,
    dayNumber: dayNumber,
    onChange: onChange,
    zoneFromSettings: zoneFromSettings
  };
})();
