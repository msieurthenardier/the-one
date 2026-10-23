(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var CELL_TYPES = { text: true };

  // App.ui.keyValueTable(opts) -> {el, values(), setValues(rows), setError(rowIndex, colKey, text|null),
  //   focusRow(i, colKey), destroy()} (M31 F3 L04, flight DD4). A column-defined table of text
  //   inputs, one row per model entry, an "Add row" button and an icon-only remove per row.
  //   columns [{key, label (string or Node), placeholder, inputTestid, mono, type ('text', the only
  //   type; anything else throws; Flight 5 adds 'sensitive' through buildCell)}] (at least one,
  //   keys unique); rows [{<colKey>: value, ...}] (keys that are not columns are kept on the row and
  //   round-trip through values()/setValues); rowDataset(row) -> object (extra data-* on each tr);
  //   addLabel ('+ Add row'), addTestid; rowTestid, removeTestid, removeLabel(n, row) ('Remove row n');
  //   onChange(values, {type: 'input'|'add'|'remove'}); testid (the table); label (the table's
  //   aria-label); emptyHidesHead (default true).
  //   The model is an array of rows with a stable internal key: input writes go straight into it,
  //   remove splices by key and the surviving rows keep their DOM nodes (only data-row-idx and the
  //   input and remove names are re-numbered). values() returns fresh objects in display order,
  //   empty rows included; the caller normalises. setValues rebuilds the rows; focus that was inside
  //   the table moves to the first input (or Add when there are no rows). Add focuses the new row's
  //   first input; remove focuses the next row's first input, else the previous, else Add.
  //   setError resolves rowIndex to the row at call time, so the error follows the row through
  //   re-numbering; it renders a small line under the input, linked by aria-describedby, and sets
  //   aria-invalid. destroy removes the listeners and leaves the DOM; the caller removes el.
  App.ui.keyValueTable = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var columns = opts.columns;
    if (!columns || !columns.length) throw new Error('App.ui.keyValueTable: columns is required');
    var seen = Object.create(null);
    var c;
    for (c = 0; c < columns.length; c++) {
      var col = columns[c];
      if (!col || !col.key) throw new Error('App.ui.keyValueTable: every column needs a key');
      if (seen[col.key]) throw new Error('App.ui.keyValueTable: duplicate column key "' + col.key + '"');
      seen[col.key] = true;
      if (col.type !== undefined && !CELL_TYPES[col.type]) {
        throw new Error('App.ui.keyValueTable: unknown column type "' + col.type + '"');
      }
    }
    var emptyHidesHead = opts.emptyHidesHead !== false;
    var rows = [];
    var keyCounter = 0;
    var destroyed = false;

    var root = util.el('div', { className: 'ui-kv' });
    var table = util.el('table', {
      className: 'ui-kv-table',
      'aria-label': opts.label || null
    });
    if (opts.testid) table.setAttribute('data-testid', opts.testid);
    var thead = util.el('thead', { className: 'ui-kv-head' });
    var headRow = util.el('tr');
    var labelText = [];
    for (c = 0; c < columns.length; c++) {
      var lab = columns[c].label;
      var th = util.el('th', { scope: 'col' });
      if (lab && typeof lab === 'object') {
        th.appendChild(lab);
        labelText.push((lab.textContent || '').trim());
      } else {
        th.textContent = lab === undefined || lab === null ? '' : String(lab);
        labelText.push(th.textContent);
      }
      headRow.appendChild(th);
    }
    var actionsTh = util.el('th', { scope: 'col' });
    actionsTh.appendChild(util.el('span', { className: 'visually-hidden', text: 'Actions' }));
    headRow.appendChild(actionsTh);
    thead.appendChild(headRow);
    var tbody = util.el('tbody', { className: 'ui-kv-body' });
    table.appendChild(thead);
    table.appendChild(tbody);

    var addBtn = App.ui.button({
      variant: 'secondary',
      label: opts.addLabel || '+ Add row',
      className: 'ui-kv-add',
      testid: opts.addTestid
    });
    root.appendChild(table);
    root.appendChild(addBtn);

    function rowOfNode(node) {
      var tr = node && node.closest ? node.closest('tr.ui-kv-row') : null;
      for (var r = 0; r < rows.length; r++) if (rows[r].tr === tr) return rows[r];
      return null;
    }

    // Delegated listeners on the wrapper: one pair, removed by destroy.
    function onInput(e) {
      var row = rowOfNode(e.target);
      if (!row) return;
      for (var i = 0; i < columns.length; i++) {
        if (row.inputs[columns[i].key] === e.target) {
          row.data[columns[i].key] = e.target.value;
          fire('input');
          return;
        }
      }
    }
    function onClick(e) {
      var t = e.target;
      if (!t || !t.closest) return;
      if (t.closest('.ui-kv-add') === addBtn) {
        var row = newRow({});
        rows.push(row);
        tbody.appendChild(row.tr);
        renumber();
        syncHead();
        focusInput(row, null);
        fire('add');
        return;
      }
      var rm = t.closest('.ui-kv-remove');
      if (rm) {
        var owner = rowOfNode(rm);
        if (owner) removeByKey(owner.key);
      }
    }
    root.addEventListener('input', onInput);
    root.addEventListener('click', onClick);

    function syncHead() {
      thead.hidden = emptyHidesHead && rows.length === 0;
    }

    function fire(type) {
      if (typeof opts.onChange === 'function') opts.onChange(values(), { type: type });
    }

    function inputName(colIdx, n) {
      return labelText[colIdx] + ', row ' + n;
    }

    function removeName(row, n) {
      if (typeof opts.removeLabel === 'function') return opts.removeLabel(n, copyData(row));
      return 'Remove row ' + n;
    }

    function copyData(row) {
      var out = {};
      var k;
      for (k in row.data) {
        if (Object.prototype.hasOwnProperty.call(row.data, k)) out[k] = row.data[k];
      }
      return out;
    }

    // One internal cell builder per column type; Flight 5 adds 'sensitive' here.
    function buildCell(column, colIdx, row) {
      var input = App.ui.textInput({
        placeholder: column.placeholder,
        value: row.data[column.key],
        testid: column.inputTestid
      });
      input.className += ' ui-kv-input';
      if (column.mono) input.className += ' ui-kv-input--mono';
      var td = util.el('td', { className: 'ui-kv-cell' });
      td.appendChild(input);
      var err = util.el('div', { className: 'ui-kv-error', id: util.uid('kv-err') });
      err.hidden = true;
      td.appendChild(err);
      row.inputs[column.key] = input;
      row.errors[column.key] = err;
      return td;
    }

    function newRow(data) {
      keyCounter += 1;
      var row = { key: keyCounter, data: {}, inputs: {}, errors: {}, tr: null, remove: null };
      var k;
      for (k in data) {
        if (Object.prototype.hasOwnProperty.call(data, k)) row.data[k] = data[k];
      }
      for (var i = 0; i < columns.length; i++) {
        var v = row.data[columns[i].key];
        row.data[columns[i].key] = v === undefined || v === null ? '' : String(v);
      }
      var tr = util.el('tr', { className: 'ui-kv-row' });
      if (opts.rowTestid) tr.setAttribute('data-testid', opts.rowTestid);
      if (typeof opts.rowDataset === 'function') util.applyDataset(tr, opts.rowDataset(copyData(row)));
      for (i = 0; i < columns.length; i++) tr.appendChild(buildCell(columns[i], i, row));
      var td = util.el('td', { className: 'ui-kv-cell' });
      row.remove = App.ui.button({
        variant: 'ghost',
        iconOnly: true,
        icon: 'trash',
        ariaLabel: 'Remove row',
        className: 'ui-kv-remove',
        testid: opts.removeTestid
      });
      td.appendChild(row.remove);
      tr.appendChild(td);
      row.tr = tr;
      return row;
    }

    function renumber() {
      for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        row.tr.setAttribute('data-row-idx', String(r));
        for (var i = 0; i < columns.length; i++) {
          row.inputs[columns[i].key].setAttribute('aria-label', inputName(i, r + 1));
        }
        row.remove.setAttribute('aria-label', removeName(row, r + 1));
      }
    }

    function indexOfKey(key) {
      for (var r = 0; r < rows.length; r++) if (rows[r].key === key) return r;
      return -1;
    }

    function focusInput(row, colKey) {
      var input = row.inputs[colKey || columns[0].key];
      if (input) input.focus();
    }

    function removeByKey(key) {
      var idx = indexOfKey(key);
      if (idx === -1) return;
      var row = rows[idx];
      rows.splice(idx, 1);
      if (row.tr.parentNode) row.tr.parentNode.removeChild(row.tr);
      renumber();
      syncHead();
      if (rows[idx]) focusInput(rows[idx], null);
      else if (rows[idx - 1]) focusInput(rows[idx - 1], null);
      else addBtn.focus();
      fire('remove');
    }

    function values() {
      var out = [];
      for (var r = 0; r < rows.length; r++) out.push(copyData(rows[r]));
      return out;
    }

    function setValues(list) {
      var hadFocus = root.contains(document.activeElement);
      rows = [];
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
      list = list || [];
      for (var i = 0; i < list.length; i++) {
        var row = newRow(list[i] || {});
        rows.push(row);
        tbody.appendChild(row.tr);
      }
      renumber();
      syncHead();
      if (hadFocus) {
        if (rows.length) focusInput(rows[0], null);
        else addBtn.focus();
      }
    }

    function setError(rowIndex, colKey, text) {
      var row = rows[rowIndex];
      if (!row || !row.inputs[colKey]) return;
      var input = row.inputs[colKey];
      var err = row.errors[colKey];
      if (text === null || text === undefined || text === '') {
        err.textContent = '';
        err.hidden = true;
        input.removeAttribute('aria-invalid');
        input.removeAttribute('aria-describedby');
        input.classList.remove('is-invalid');
      } else {
        err.textContent = String(text);
        err.hidden = false;
        input.setAttribute('aria-invalid', 'true');
        input.setAttribute('aria-describedby', err.id);
        input.classList.add('is-invalid');
      }
    }

    function focusRow(i, colKey) {
      if (rows[i]) focusInput(rows[i], colKey);
    }

    setValues(opts.rows);

    return {
      el: root,
      values: values,
      setValues: setValues,
      setError: setError,
      focusRow: focusRow,
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        root.removeEventListener('input', onInput);
        root.removeEventListener('click', onClick);
      }
    };
  };
})();
