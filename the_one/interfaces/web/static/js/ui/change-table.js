(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var DEFAULT_CLAMP = 160;

  // App.ui.changeTable(opts) -> {el, set(opts)}  (M36 F2 L6, flight DD6)
  //
  // A native <table> of labelled values: a label column, then one value column ("Proposed") or
  // two ("Now" and "Proposed"). Used by the GleepGlorp proposal card.
  //
  // opts:
  //   columns     1 (default) or 2; anything else throws
  //   headers     [now, proposed] (two columns) or [proposed] (one): the column headers, drawn as
  //               eyebrows (<th scope="col">); a visually hidden "Field" heads the label column.
  //               Omitted, the table has no header row.
  //   rows        [{label, now?, proposed, mono?}]: text only (set with textContent, never as
  //               HTML); mono sets the value in the monospace face
  //   clampChars  a value longer than this (default 160) shows its start with an ellipsis and a
  //               "Show all {label}" button (aria-expanded) that reveals the rest in place
  //   caption     the table's accessible name, a visually hidden <caption>
  //   testid      placed on the <table> (supplied by the caller); the Show all button carries
  //               <testid>-more (one column) or <testid>-more-now / <testid>-more-proposed (two
//               columns, with data-column; named "Show all {label} (now|proposed)")
  // set(opts) replaces the rows (and, when given, the headers, caption and columns) in place;
  // the <table> element is the same node.
  App.ui.changeTable = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var root = util.el('table', { className: 'ui-change-table' });
    if (opts.testid) root.setAttribute('data-testid', opts.testid);
    var current = {};

    // `column` is 'now' | 'proposed' in a two-column table (the button then says which value it
    // reveals, and its testid and data-column carry the column), or null in a one-column table.
    function valueCell(label, text, mono, clamp, testid, column) {
      var name = column ? label + ' (' + column + ')' : label;
      var td = util.el('td', { className: 'ui-change-table-value' + (mono ? ' ui-change-table-value--mono' : '') });
      text = text === undefined || text === null ? '' : String(text);
      if (text.length <= clamp) {
        td.textContent = text;
        return td;
      }
      var shown = util.el('span', { className: 'ui-change-table-text', text: text.slice(0, clamp) + '…' });
      var more = App.ui.button({
        variant: 'ghost',
        size: 'sm',
        label: 'Show all',
        ariaLabel: 'Show all ' + name,
        className: 'ui-change-table-more'
      });
      if (testid) more.setAttribute('data-testid', testid + '-more' + (column ? '-' + column : ''));
      if (column) more.setAttribute('data-column', column);
      more.setAttribute('aria-expanded', 'false');
      more.addEventListener('click', function () {
        var open = more.getAttribute('aria-expanded') === 'true';
        open = !open;
        more.setAttribute('aria-expanded', open ? 'true' : 'false');
        shown.textContent = open ? text : text.slice(0, clamp) + '…';
        var word = open ? 'Show less' : 'Show all';
        // The button's label is its one text node (no icon).
        more.firstChild.data = word;
        more.setAttribute('aria-label', word + ' ' + name);
      });
      td.appendChild(shown);
      td.appendChild(more);
      return td;
    }

    function build(o) {
      var columns = o.columns === undefined ? 1 : o.columns;
      if (columns !== 1 && columns !== 2) {
        throw new Error('App.ui.changeTable: columns must be 1 or 2');
      }
      var clamp = typeof o.clampChars === 'number' ? o.clampChars : DEFAULT_CLAMP;
      root.textContent = '';
      root.setAttribute('data-columns', String(columns));
      if (o.caption) {
        root.appendChild(util.el('caption', { className: 'visually-hidden', text: o.caption }));
      }
      if (o.headers && o.headers.length) {
        var hr = util.el('tr', {});
        hr.appendChild(util.el('th', { scope: 'col', className: 'visually-hidden', text: 'Field' }));
        for (var h = 0; h < o.headers.length && h < columns; h++) {
          hr.appendChild(util.el('th', { scope: 'col', className: 'ui-change-table-head', text: o.headers[h] }));
        }
        root.appendChild(util.el('thead', {}, [hr]));
      }
      var body = util.el('tbody', {});
      var rows = o.rows || [];
      for (var i = 0; i < rows.length; i++) {
        var r = rows[i];
        var tr = util.el('tr', { className: 'ui-change-table-row' });
        tr.appendChild(util.el('th', { scope: 'row', className: 'ui-change-table-label', text: r.label }));
        if (columns === 2) {
          var now = valueCell(r.label, r.now, r.mono, clamp, opts.testid, 'now');
          now.classList.add('ui-change-table-now');
          tr.appendChild(now);
        }
        tr.appendChild(valueCell(r.label, r.proposed, r.mono, clamp, opts.testid,
          columns === 2 ? 'proposed' : null));
        body.appendChild(tr);
      }
      root.appendChild(body);
      current = { columns: columns, headers: o.headers, caption: o.caption, clampChars: o.clampChars };
    }

    build(opts);

    return {
      el: root,
      set: function (next) {
        next = next || {};
        build({
          columns: next.columns !== undefined ? next.columns : current.columns,
          headers: next.headers !== undefined ? next.headers : current.headers,
          caption: next.caption !== undefined ? next.caption : current.caption,
          clampChars: next.clampChars !== undefined ? next.clampChars : current.clampChars,
          rows: next.rows
        });
      }
    };
  };
})();
