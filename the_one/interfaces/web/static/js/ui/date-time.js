(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.datePicker and App.ui.timeField (M33 F3 L6, DD7). Both are a text
  // input that parses what people type and re-shows it in the display form, one
  // sentence of error text linked by aria-describedby, and a silent setValue.
  // Library factories may not read App globals other than App.ui and App.icons,
  // so "today" is supplied by the caller (the datePicker `today` option, a
  // function returning the operator-zone date as "YYYY-MM-DD"). Without it there
  // is no today mark; the Date getters are never used as a fallback.

  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December'];
  var DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  var DAY_HEADS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function isoOf(y, m, d) { return y + '-' + pad(m + 1) + '-' + pad(d); }
  function daysIn(y, m) { return new Date(Date.UTC(y, m + 1, 0)).getUTCDate(); }
  function weekdayOf(y, m, d) { return new Date(Date.UTC(y, m, d)).getUTCDay(); }
  function parseIso(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || '');
    if (!m) return null;
    var y = +m[1], mo = +m[2] - 1, d = +m[3];
    if (mo < 0 || mo > 11 || d < 1 || d > daysIn(y, mo)) return null;
    return { y: y, m: mo, d: d };
  }
  // Shift a {y,m,d} by whole days (UTC arithmetic, zone-free).
  function addDays(p, n) {
    var t = new Date(Date.UTC(p.y, p.m, p.d + n));
    return { y: t.getUTCFullYear(), m: t.getUTCMonth(), d: t.getUTCDate() };
  }
  // Shift by whole months, clamping the day to the target month's length.
  function addMonths(p, n) {
    var idx = p.y * 12 + p.m + n;
    var y = Math.floor(idx / 12), m = idx - y * 12;
    return { y: y, m: m, d: Math.min(p.d, daysIn(y, m)) };
  }
  function display(p) {
    return DAYS[weekdayOf(p.y, p.m, p.d)].slice(0, 3) + ', ' + MONTHS[p.m].slice(0, 3) + ' ' +
      p.d + ', ' + p.y;
  }
  function short(p) { return MONTHS[p.m].slice(0, 3) + ' ' + p.d + ', ' + p.y; }
  function monthIndex(word) {
    var w = word.toLowerCase();
    if (w.length < 3) return -1;
    for (var i = 0; i < 12; i++) {
      if (MONTHS[i].toLowerCase().indexOf(w) === 0) return i;
    }
    return -1;
  }
  function build(y, m, d) {
    if (m < 0 || m > 11 || d < 1 || y < 1000 || y > 9999 || d > daysIn(y, m)) return null;
    return { y: y, m: m, d: d };
  }
  // Every accepted typed form; null when unreadable.
  function parseDate(text, yr) {
    var s = String(text || '').trim();
    var m;
    // A leading weekday ("Thu, " / "Thursday ") is dropped.
    m = /^([A-Za-z]{3,9})\.?,?\s+(.+)$/.exec(s);
    if (m) {
      var lead = m[1].toLowerCase();
      for (var i = 0; i < 7; i++) {
        if (lead.length >= 3 && DAYS[i].toLowerCase().indexOf(lead) === 0 && monthIndex(m[1]) === -1) {
          s = m[2].trim();
          break;
        }
      }
    }
    if ((m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(s))) return build(+m[1], +m[2] - 1, +m[3]);
    if ((m = /^(\d{1,2})\/(\d{1,2})(?:\/(\d{4}|\d{2}))?$/.exec(s))) {
      var y = m[3] ? (m[3].length === 2 ? 2000 + +m[3] : +m[3]) : yr;
      if (y == null) return null;
      return build(y, +m[1] - 1, +m[2]);
    }
    if ((m = /^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:\s*,\s*|\s+)?(\d{4})?$/.exec(s))) {
      var mi = monthIndex(m[1]);
      if (mi === -1) return null;
      if (!m[3] && yr == null) return null;
      return build(m[3] ? +m[3] : yr, mi, +m[2]);
    }
    return null;
  }
  function cmp(a, b) { return (a.y - b.y) || (a.m - b.m) || (a.d - b.d); }

  var SVG_NS = 'http://www.w3.org/2000/svg';
  // A calendar glyph built with DOM APIs (the icon set has none).
  function calendarIcon() {
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    var shapes = [['rect', { x: 3, y: 4, width: 18, height: 18, rx: 2 }],
      ['path', { d: 'M16 2v4' }], ['path', { d: 'M8 2v4' }], ['path', { d: 'M3 10h18' }]];
    shapes.forEach(function (s) {
      var n = document.createElementNS(SVG_NS, s[0]);
      for (var k in s[1]) {
        if (Object.prototype.hasOwnProperty.call(s[1], k)) n.setAttribute(k, String(s[1][k]));
      }
      svg.appendChild(n);
    });
    return svg;
  }

  // Shared pieces: the labelled input and the error sentence.
  function makeInput(opts, who, prefix) {
    var util = App.ui.util;
    if (!opts.label && !opts.ariaLabel) throw new Error(who + ': label or ariaLabel is required');
    var input = util.el('input', { type: 'text', className: 'field-input', autocomplete: 'off' });
    input.id = opts.id || util.uid(prefix);
    input.setAttribute('data-ui-own-label', 'true');
    if (opts.ariaLabel) input.setAttribute('aria-label', opts.ariaLabel);
    if (opts.disabled) input.disabled = true;
    if (opts.testid) input.setAttribute('data-testid', opts.testid + '-input');
    return input;
  }
  function makeErrorState(input) {
    var util = App.ui.util;
    var node = util.el('div', { className: 'field-error ui-date-time-error', id: util.uid('dt-err') });
    // Always in the DOM (and polite) so the sentence is announced when it fills.
    node.setAttribute('aria-live', 'polite');
    node.style.display = 'none';
    return {
      node: node,
      set: function (text) {
        node.style.display = '';
        node.textContent = text;
        input.setAttribute('aria-invalid', 'true');
        util.addDescribedBy(input, node.id);
      },
      clear: function () {
        node.textContent = '';
        node.style.display = 'none';
        input.removeAttribute('aria-invalid');
        util.removeDescribedBy(input, node.id);
      }
    };
  }

  // App.ui.datePicker(opts) -> {el, input, value(), setValue(iso), setMin(iso),
  //   setMax(iso), setDisabled(bool), focus(), destroy()}.
  //   label (visible) or ariaLabel, value ("YYYY-MM-DD" or null), min, max (ISO),
  //   onChange(iso|null), testid, disabled, describedBy, id, today (a function
  //   returning the operator-zone date as "YYYY-MM-DD"; without it no day is
  //   marked today and a year-less typed date takes its year from the current
  //   value, else min, else is unreadable; with it the year is today's).
  //   Test ids: {testid}-input, -button, -calendar, -day (data-date on each),
  //   -prev, -next.
  //   el is div.ui-date-picker holding the label, the row (input + button), the
  //   error sentence and the calendar popover (div[role=dialog], non-modal, a
  //   DOM descendant of el). Typed forms: 2026-10-29, 10/29/2026, 10/29, Oct 29,
  //   2026, Oct 29 and the display form "Thu, Oct 29, 2026"; parsed on blur and
  //   Enter. An unreadable or out-of-range entry keeps the text, sets
  //   aria-invalid with one sentence, and value() is null. A document pointerdown
  //   listener exists only while the calendar is open. Escape in the open
  //   calendar closes it (stopPropagation, so an enclosing modal stays open) and
  //   returns focus to the button. The month grid is a role=grid table (Sunday
  //   first); aria-selected sits on the selected day's gridcell, aria-current=date
  //   on today's day button. setValue and setMin/setMax are silent.
  App.ui.datePicker = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var input = makeInput(opts, 'App.ui.datePicker', 'date');
    input.placeholder = 'Oct 29, 2026';
    var err = makeErrorState(input);
    if (opts.describedBy) util.addDescribedBy(input, opts.describedBy);
    var min = parseIso(opts.min), max = parseIso(opts.max);
    var current = parseIso(opts.value);
    var viewing = null;     // {y, m, d}: the keyboard-focused date while open
    var isOpen = false;
    var ctl;

    var button = App.ui.button({
      iconOnly: true, ariaLabel: 'Choose date', variant: 'secondary',
      testid: opts.testid ? opts.testid + '-button' : null, disabled: !!opts.disabled
    });
    button.appendChild(calendarIcon());
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-expanded', 'false');

    var cal = util.el('div', {
      className: 'ui-date-cal', role: 'dialog', id: util.uid('cal'), hidden: true
    });
    button.setAttribute('aria-controls', cal.id);
    if (opts.testid) cal.setAttribute('data-testid', opts.testid + '-calendar');
    var prev = App.ui.button({
      iconOnly: true, ariaLabel: 'Previous month', variant: 'ghost', size: 'sm', icon: 'chevron-right',
      className: 'ui-date-cal-prev', testid: opts.testid ? opts.testid + '-prev' : null
    });
    var next = App.ui.button({
      iconOnly: true, ariaLabel: 'Next month', variant: 'ghost', size: 'sm', icon: 'chevron-right',
      testid: opts.testid ? opts.testid + '-next' : null
    });
    var title = util.el('div', { className: 'ui-date-cal-title', 'aria-live': 'polite' });
    var head = util.el('div', { className: 'ui-date-cal-head' }, [prev, title, next]);
    var grid = util.el('table', { className: 'ui-date-cal-grid', role: 'grid' });
    var thead = util.el('thead');
    var hr = util.el('tr');
    DAY_HEADS.forEach(function (h, i) {
      hr.appendChild(util.el('th', { scope: 'col', abbr: DAYS[i], text: h }));
    });
    thead.appendChild(hr);
    var tbody = util.el('tbody');
    grid.appendChild(thead);
    grid.appendChild(tbody);
    cal.appendChild(head);
    cal.appendChild(grid);

    var row = util.el('div', { className: 'ui-date-picker-row' }, [input, button]);
    var kids = [];
    if (opts.label) {
      var lab = util.el('label', { className: 'ui-date-picker-label', text: opts.label });
      lab.htmlFor = input.id;
      kids.push(lab);
    }
    kids.push(row, err.node, cal);
    var el = util.el('div', { className: 'ui-date-picker' }, kids);

    function inRange(p) {
      return !((min && cmp(p, min) < 0) || (max && cmp(p, max) > 0));
    }
    function clamp(p) {
      if (min && cmp(p, min) < 0) return min;
      if (max && cmp(p, max) > 0) return max;
      return p;
    }
    function rangeSentence(p) {
      if (min && cmp(p, min) < 0) return 'Choose a date on or after ' + short(min) + '.';
      return 'Choose a date on or before ' + short(max) + '.';
    }

    function todayP() {
      return typeof opts.today === 'function' ? parseIso(opts.today()) : null;
    }
    function renderCal() {
      title.textContent = MONTHS[viewing.m] + ' ' + viewing.y;
      cal.setAttribute('aria-label', MONTHS[viewing.m] + ' ' + viewing.y);
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
      var t = todayP();
      var lead = weekdayOf(viewing.y, viewing.m, 1);
      var total = daysIn(viewing.y, viewing.m);
      var d = 1 - lead;
      while (d <= total) {
        var tr = util.el('tr');
        for (var c = 0; c < 7; c++, d++) {
          var td = util.el('td', { role: 'gridcell' });
          if (d >= 1 && d <= total) {
            var p = { y: viewing.y, m: viewing.m, d: d };
            var b = util.el('button', {
              type: 'button', className: 'ui-date-day', text: String(d), tabindex: d === viewing.d ? '0' : '-1',
              'aria-label': DAYS[weekdayOf(p.y, p.m, p.d)] + ', ' + MONTHS[p.m] + ' ' + p.d + ', ' + p.y
            });
            b.setAttribute('data-date', isoOf(p.y, p.m, p.d));
            if (opts.testid) b.setAttribute('data-testid', opts.testid + '-day');
            if (!inRange(p)) b.disabled = true;
            if (t && cmp(p, t) === 0) b.setAttribute('aria-current', 'date');
            if (current && cmp(p, current) === 0) {
              td.setAttribute('aria-selected', 'true');
              b.classList.add('ui-date-day--selected');
            }
            td.appendChild(b);
          }
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      prev.disabled = !!(min && cmp(addDays({ y: viewing.y, m: viewing.m, d: 1 }, -1), min) < 0);
      next.disabled = !!(max && cmp(addDays({ y: viewing.y, m: viewing.m, d: total }, 1), max) > 0);
    }
    function focusDay() {
      var b = tbody.querySelector('button[data-date="' + isoOf(viewing.y, viewing.m, viewing.d) + '"]');
      if (b) b.focus();
    }
    function moveTo(p) {
      viewing = clamp(p);
      renderCal();
      focusDay();
    }

    function onDocPointerdown(e) {
      if (!el.isConnected) {
        document.removeEventListener('pointerdown', onDocPointerdown, true);
        isOpen = false;
        return;
      }
      if (!el.contains(e.target)) close(false);
    }
    function close(restoreFocus) {
      if (!isOpen) return;
      isOpen = false;
      document.removeEventListener('pointerdown', onDocPointerdown, true);
      cal.hidden = true;
      button.setAttribute('aria-expanded', 'false');
      if (restoreFocus && el.isConnected) button.focus();
    }
    function open() {
      if (isOpen || input.disabled) return;
      isOpen = true;
      var t0 = todayP();
      var start = current || (t0 ? clamp(t0) : (min || max || { y: 2000, m: 0, d: 1 }));
      viewing = { y: start.y, m: start.m, d: start.d };
      renderCal();
      cal.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      document.addEventListener('pointerdown', onDocPointerdown, true);
      focusDay();
    }

    var last = current ? isoOf(current.y, current.m, current.d) : null;
    function fire() {
      var now = ctl.value();
      if (now === last) return;
      last = now;
      if (typeof opts.onChange === 'function') opts.onChange(now);
    }
    function showCurrent() {
      input.value = current ? display(current) : '';
    }
    // Parse the input text; keep it and flag when it cannot be used.
    function commit() {
      var text = input.value.trim();
      if (!text) {
        current = null;
        err.clear();
        return;
      }
      var t1 = todayP();
      var p = parseDate(text, t1 ? t1.y : (current ? current.y : (min ? min.y : null)));
      if (!p) {
        current = null;
        err.set('Enter a date like Oct 29, 2026.');
        return;
      }
      if (!inRange(p)) {
        current = null;
        err.set(rangeSentence(p));
        return;
      }
      current = p;
      err.clear();
      showCurrent();
    }
    function pick(p) {
      current = p;
      err.clear();
      showCurrent();
      close(true);
      fire();
    }

    function onBlur() { commit(); fire(); }
    function onInputKey(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        commit();
        fire();
      }
    }
    function onButtonClick() {
      if (isOpen) close(true);
      else open();
    }
    function onCalClick(e) {
      var b = e.target.closest ? e.target.closest('.ui-date-day') : null;
      if (b && !b.disabled && cal.contains(b)) pick(parseIso(b.getAttribute('data-date')));
    }
    function onPrev() { moveTo(addMonths(viewing, -1)); }
    function onNext() { moveTo(addMonths(viewing, 1)); }
    function onWrapKeydown(e) {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        close(true);
        return;
      }
      if (!e.target.classList || !e.target.classList.contains('ui-date-day')) return;
      if (e.ctrlKey || e.altKey || e.metaKey) return;
      var k = e.key, handled = true;
      if (k === 'ArrowLeft') moveTo(addDays(viewing, -1));
      else if (k === 'ArrowRight') moveTo(addDays(viewing, 1));
      else if (k === 'ArrowUp') moveTo(addDays(viewing, -7));
      else if (k === 'ArrowDown') moveTo(addDays(viewing, 7));
      else if (k === 'PageUp') moveTo(addMonths(viewing, e.shiftKey ? -12 : -1));
      else if (k === 'PageDown') moveTo(addMonths(viewing, e.shiftKey ? 12 : 1));
      else if (k === 'Home') moveTo(addDays(viewing, -weekdayOf(viewing.y, viewing.m, viewing.d)));
      else if (k === 'End') moveTo(addDays(viewing, 6 - weekdayOf(viewing.y, viewing.m, viewing.d)));
      else if (k === 'Enter' || k === ' ') {
        if (!e.target.disabled) pick(parseIso(e.target.getAttribute('data-date')));
      } else handled = false;
      if (handled) e.preventDefault();
    }
    function onWrapFocusout(e) {
      if (!isOpen) return;
      var nextEl = e.relatedTarget;
      if (nextEl && !el.contains(nextEl)) close(false);
    }
    // Keep focus on a day button on a mouse press (WebKit does not focus buttons).
    function onCalMousedown(e) { e.preventDefault(); }

    input.addEventListener('blur', onBlur);
    input.addEventListener('keydown', onInputKey);
    button.addEventListener('click', onButtonClick);
    cal.addEventListener('click', onCalClick);
    cal.addEventListener('mousedown', onCalMousedown);
    prev.addEventListener('click', onPrev);
    next.addEventListener('click', onNext);
    el.addEventListener('keydown', onWrapKeydown);
    el.addEventListener('focusout', onWrapFocusout);

    showCurrent();

    ctl = {
      el: el,
      input: input,
      value: function () { return current ? isoOf(current.y, current.m, current.d) : null; },
      setValue: function (iso) {
        current = parseIso(iso);
        last = current ? isoOf(current.y, current.m, current.d) : null;
        err.clear();
        showCurrent();
        if (isOpen) close(false);
      },
      setMin: function (iso) {
        min = parseIso(iso);
        if (input.value.trim()) { commit(); last = ctl.value(); }
        if (isOpen) renderCal();
      },
      setMax: function (iso) {
        max = parseIso(iso);
        if (input.value.trim()) { commit(); last = ctl.value(); }
        if (isOpen) renderCal();
      },
      setDisabled: function (flag) {
        input.disabled = !!flag;
        button.disabled = !!flag;
        if (flag) close(false);
      },
      focus: function () { input.focus(); },
      destroy: function () {
        close(false);
        input.removeEventListener('blur', onBlur);
        input.removeEventListener('keydown', onInputKey);
        button.removeEventListener('click', onButtonClick);
        cal.removeEventListener('click', onCalClick);
        cal.removeEventListener('mousedown', onCalMousedown);
        prev.removeEventListener('click', onPrev);
        next.removeEventListener('click', onNext);
        el.removeEventListener('keydown', onWrapKeydown);
        el.removeEventListener('focusout', onWrapFocusout);
      }
    };
    return ctl;
  };

  // "HH:MM" from a typed time; null when unreadable.
  function parseTime(text) {
    var s = String(text || '').trim().toLowerCase();
    var m = /^(\d{1,4})(?::(\d{2}))?\s*(?:([ap])\.?(?:m\.?)?)?$/.exec(s);
    if (!m) return null;
    var digits = m[1], h, mi, suffix = m[3] || null;
    if (m[2] !== undefined) {
      if (digits.length > 2) return null;
      h = +digits;
      mi = +m[2];
    } else if (digits.length <= 2) {
      h = +digits;
      mi = 0;
    } else {
      h = +digits.slice(0, digits.length - 2);
      mi = +digits.slice(-2);
    }
    if (mi > 59) return null;
    if (suffix) {
      if (h < 1 || h > 12) return null;
      h = h % 12 + (suffix === 'p' ? 12 : 0);
    } else if (h > 23) {
      return null;
    }
    return pad(h) + ':' + pad(mi);
  }
  function showTime(hhmm) {
    var m = /^(\d{2}):(\d{2})$/.exec(hhmm || '');
    if (!m) return '';
    var h = +m[1];
    return ((h % 12) || 12) + ':' + m[2] + ' ' + (h < 12 ? 'AM' : 'PM');
  }
  function validTime(v) {
    var m = /^(\d{2}):(\d{2})$/.exec(v || '');
    return m && +m[1] < 24 && +m[2] < 60 ? v : null;
  }

  // App.ui.timeField(opts) -> {el, input, value(), setValue(hhmm),
  //   setDisabled(bool), focus(), destroy()}.
  //   label (visible) or ariaLabel, value ("HH:MM" 24-hour or null),
  //   onChange(hhmm|null), testid (-input on the field), disabled, describedBy, id.
  //   Shows "9:30 AM" (M25 DD14). Accepts 9:30 AM, 9:30am, 9:30 a, 9:30p, 21:30,
  //   0930, 930pm, 9 am, 9pm, 12 pm (noon), 12 am (midnight); parsed on blur and
  //   Enter. An unreadable entry keeps its text, sets aria-invalid with "Enter a
  //   time like 9:30 AM." and value() is null. setValue is silent.
  App.ui.timeField = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var input = makeInput(opts, 'App.ui.timeField', 'time');
    input.placeholder = '9:30 AM';
    input.classList.add('ui-input--short');
    var err = makeErrorState(input);
    if (opts.describedBy) util.addDescribedBy(input, opts.describedBy);
    var current = validTime(opts.value);
    var last = current;
    var kids = [];
    if (opts.label) {
      var lab = util.el('label', { className: 'ui-date-picker-label', text: opts.label });
      lab.htmlFor = input.id;
      kids.push(lab);
    }
    kids.push(input, err.node);
    var el = util.el('div', { className: 'ui-time-field' }, kids);
    var ctl;

    function show() { input.value = current ? showTime(current) : ''; }
    function commit() {
      var text = input.value.trim();
      if (!text) {
        current = null;
        err.clear();
        return;
      }
      var v = parseTime(text);
      if (!v) {
        current = null;
        err.set('Enter a time like 9:30 AM.');
        return;
      }
      current = v;
      err.clear();
      show();
    }
    function fire() {
      if (current === last) return;
      last = current;
      if (typeof opts.onChange === 'function') opts.onChange(current);
    }
    function onBlur() { commit(); fire(); }
    function onKey(e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        commit();
        fire();
      }
    }
    input.addEventListener('blur', onBlur);
    input.addEventListener('keydown', onKey);
    show();
    ctl = {
      el: el,
      input: input,
      value: function () { return current; },
      setValue: function (hhmm) {
        current = validTime(hhmm);
        last = current;
        err.clear();
        show();
      },
      setDisabled: function (flag) { input.disabled = !!flag; },
      focus: function () { input.focus(); },
      destroy: function () {
        input.removeEventListener('blur', onBlur);
        input.removeEventListener('keydown', onKey);
      }
    };
    return ctl;
  };
})();
