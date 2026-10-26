(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var CELL_TYPES = { text: true, secret: true, toggle: true };
  var RENAME_HINT = 'Type the value again for the new name.';

  // App.ui.keyValueTable(opts) -> {el, values(), setValues(rows), setRow(i, patch),
  //   setError(rowIndex, colKey, text|null), focusRow(i, colKey), destroy()} (M31 F3 L04, flight
  //   DD4; secret and toggle columns, setRow, M31 F5 L04, flight DD5). A column-defined table,
  //   one row per model entry, an "Add row" button and an icon-only remove per row.
  //   columns [{key, label (string or Node), placeholder, inputTestid, mono, type, width}] (at least
  //   one, keys unique). width (a CSS length such as '120px', M31 F5 L07) sets the column's width in
  //   a fixed-layout table (a table with a secret or toggle column); a toggle column is 88px
  //   without it, which fits a one-word label but not a label with an info button. type is 'text' (default), 'secret' or 'toggle'; anything else throws.
  //   A 'secret' column adds {maskedBy: '<toggle column key>', storedKey: '<row key holding the
  //   stored mask>', clearOnUnmask}: while row[maskedBy] is true (always, with no maskedBy) the
  //   cell is an App.ui.secretInput (eye named "Show value, row n", stored mode when
  //   row[storedKey] is set); while false it is a plain text input with no eye. Switching
  //   rebuilds only that cell. clearOnUnmask: unticking a row whose value still equals its stored
  //   mask clears the value and row[storedKey]. A 'toggle' column adds {ariaLabel, inputTestid}: an
  //   App.ui.toggle named "{ariaLabel or label}, row n" (ariaLabel is required when label is a
  //   Node); the row value is a boolean; the change fires onChange(values, {type: 'toggle'}).
  //   keyColumn (default columns[0].key): when a row has a stored mask and its trimmed key differs
  //   from the key captured when the mask was loaded, a value still equal to the mask clears with
  //   its stored mask and the cell's hint reads "Type the value again for the new name." (one
  //   onChange). No attribute ever holds a secret: values travel only through .value.
  //   rows [{<colKey>: value, ...}] (keys that are not columns are kept on the row and
  //   round-trip through values()/setValues); rowDataset(row) -> object (extra data-* on each tr);
  //   addLabel ('+ Add row'), addTestid; rowTestid, removeTestid, removeLabel(n, row) ('Remove row n');
  //   onChange(values, {type: 'input'|'add'|'remove'|'toggle'}); testid (the table); label (the
  //   table's aria-label); emptyHidesHead (default true).
  //   The model is an array of rows with a stable internal key: input writes go straight into it,
  //   remove splices by key and the surviving rows keep their DOM nodes (only data-row-idx and the
  //   input, toggle, eye and remove names are re-numbered). values() returns fresh objects in
  //   display order, empty rows included; the caller normalises. setValues rebuilds the rows; focus
  //   that was inside the table moves to the first input (or Add when there are no rows).
  //   setRow(i, patch) MERGES keys into row i (column and non-column, storedKey and toggles
  //   included), applies them all before any cell re-renders, and patches only the cells whose
  //   value or masking changed, without moving focus (a focused input keeps its selection); a
  //   patched cell loses its error. It never fires onChange. Add focuses the new row's first
  //   input; remove focuses the next row's first input, else the previous, else Add.
  //   setError resolves rowIndex to the row at call time, so the error follows the row through
  //   re-numbering; it renders a small line under the input, linked by an aria-describedby token,
  //   and sets aria-invalid. destroy removes the listeners and leaves the DOM; the caller removes el.
  App.ui.keyValueTable = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var columns = opts.columns;
    if (!columns || !columns.length) throw new Error('App.ui.keyValueTable: columns is required');
    var seen = Object.create(null);
    var c;
    var fixed = false;
    for (c = 0; c < columns.length; c++) {
      var col = columns[c];
      if (!col || !col.key) throw new Error('App.ui.keyValueTable: every column needs a key');
      if (seen[col.key]) throw new Error('App.ui.keyValueTable: duplicate column key "' + col.key + '"');
      seen[col.key] = true;
      if (col.type !== undefined && !CELL_TYPES[col.type]) {
        throw new Error('App.ui.keyValueTable: unknown column type "' + col.type + '"');
      }
      if (col.type === 'toggle' && col.label && typeof col.label === 'object' && !col.ariaLabel) {
        throw new Error('App.ui.keyValueTable: a toggle column with a Node label needs ariaLabel');
      }
      if (col.type === 'secret' || col.type === 'toggle') fixed = true;
    }
    var keyColumn = opts.keyColumn || columns[0].key;
    var emptyHidesHead = opts.emptyHidesHead !== false;
    var rows = [];
    var keyCounter = 0;
    var destroyed = false;

    function typeOf(column) {
      return column.type || 'text';
    }

    var root = util.el('div', { className: 'ui-kv' });
    var table = util.el('table', {
      className: 'ui-kv-table' + (fixed ? ' ui-kv-table--fixed' : ''),
      'aria-label': opts.label || null
    });
    if (opts.testid) table.setAttribute('data-testid', opts.testid);
    if (fixed) {
      var colgroup = util.el('colgroup');
      for (c = 0; c < columns.length; c++) {
        var colEl = util.el('col');
        if (typeOf(columns[c]) === 'toggle') colEl.style.width = '88px';
        if (columns[c].width) colEl.style.width = String(columns[c].width);
        colgroup.appendChild(colEl);
      }
      var actionsCol = util.el('col');
      actionsCol.style.width = '48px';
      colgroup.appendChild(actionsCol);
      table.appendChild(colgroup);
    }
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

    function trimmedKey(row) {
      return String(row.data[keyColumn] === undefined ? '' : row.data[keyColumn]).trim();
    }

    function captureBaselines(row) {
      for (var i = 0; i < columns.length; i++) {
        var sk = columns[i].storedKey;
        if (typeOf(columns[i]) === 'secret' && sk && row.data[sk]) {
          row.baseline[columns[i].key] = trimmedKey(row);
        }
      }
    }

    // The key-rename rule: a renamed key on a row whose value still equals its stored mask
    // drops both, and the cell says why. Returns true when something was cleared.
    function checkRename(row) {
      var cleared = false;
      for (var i = 0; i < columns.length; i++) {
        var column = columns[i];
        var sk = column.storedKey;
        if (typeOf(column) !== 'secret' || !sk) continue;
        var mask = row.data[sk];
        if (!mask || row.baseline[column.key] === undefined) continue;
        if (trimmedKey(row) === row.baseline[column.key]) continue;
        if (row.data[column.key] !== mask) continue;
        row.data[column.key] = '';
        row.data[sk] = '';
        delete row.baseline[column.key];
        var ctl = row.secrets[column.key];
        if (ctl) {
          ctl.input.value = '';
          ctl.setStored(null);
          ctl.sync();
          ctl.setHint(RENAME_HINT);
          placeHint(row, column.key);
        }
        cleared = true;
      }
      return cleared;
    }

    function isMasked(column, row) {
      return column.maskedBy ? !!row.data[column.maskedBy] : true;
    }

    // Delegated listeners on the wrapper: removed by destroy.
    function onInput(e) {
      var row = rowOfNode(e.target);
      if (!row) return;
      for (var i = 0; i < columns.length; i++) {
        var column = columns[i];
        if (typeOf(column) === 'toggle') continue;
        if (row.inputs[column.key] === e.target) {
          row.data[column.key] = e.target.value;
          if (column.key === keyColumn) checkRename(row);
          fire('input');
          return;
        }
      }
    }
    function onChangeEvt(e) {
      var row = rowOfNode(e.target);
      if (!row) return;
      for (var i = 0; i < columns.length; i++) {
        var column = columns[i];
        if (typeOf(column) !== 'toggle' || row.inputs[column.key] !== e.target) continue;
        row.data[column.key] = !!e.target.checked;
        for (var j = 0; j < columns.length; j++) {
          var sc = columns[j];
          if (typeOf(sc) !== 'secret' || sc.maskedBy !== column.key) continue;
          if (!e.target.checked && sc.clearOnUnmask && sc.storedKey) {
            var mask = row.data[sc.storedKey];
            if (mask && row.data[sc.key] === mask) {
              row.data[sc.key] = '';
              row.data[sc.storedKey] = '';
              delete row.baseline[sc.key];
            }
          }
          rebuildSecret(row, sc, j);
        }
        renumber();
        fire('toggle');
        return;
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
    root.addEventListener('change', onChangeEvt);
    root.addEventListener('click', onClick);

    function syncHead() {
      thead.hidden = emptyHidesHead && rows.length === 0;
    }

    function fire(type) {
      if (typeof opts.onChange === 'function') opts.onChange(values(), { type: type });
    }

    function inputName(colIdx, n) {
      var column = columns[colIdx];
      var base = typeOf(column) === 'toggle' && column.ariaLabel ? column.ariaLabel : labelText[colIdx];
      return base + ', row ' + n;
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

    function decorate(column, el) {
      el.classList.add('ui-kv-input');
      if (column.mono) el.classList.add('ui-kv-input--mono');
      return el;
    }

    // Builds the value control of a text or secret cell and returns its nodes
    // [control, hint?]; repoints row.inputs / row.secrets.
    function buildValueControl(column, row) {
      var value = row.data[column.key];
      var secret = null;
      var input;
      var node;
      if (typeOf(column) === 'secret' && isMasked(column, row)) {
        var mask = column.storedKey ? row.data[column.storedKey] : '';
        secret = App.ui.secretInput({
          placeholder: column.placeholder,
          value: value,
          testid: column.inputTestid,
          autocomplete: 'new-password',
          stored: mask || undefined
        });
        input = secret.input;
        decorate(column, input);
        node = secret.el;
      } else {
        input = decorate(column, App.ui.textInput({
          placeholder: column.placeholder,
          value: value,
          testid: column.inputTestid
        }));
        node = input;
      }
      row.inputs[column.key] = input;
      if (secret) row.secrets[column.key] = secret;
      else delete row.secrets[column.key];
      return node;
    }

    function placeHint(row, colKey) {
      var ctl = row.secrets[colKey];
      var td = row.cells[colKey];
      if (!ctl || !ctl.hintEl || !td || ctl.hintEl.parentNode) return;
      td.insertBefore(ctl.hintEl, row.errors[colKey]);
    }

    function applyError(row, colKey) {
      var input = row.inputs[colKey];
      var err = row.errors[colKey];
      var text = row.errText[colKey];
      if (!input || !err) return;
      if (!text) {
        err.textContent = '';
        err.hidden = true;
        err.removeAttribute('role');
        input.removeAttribute('aria-invalid');
        util.removeDescribedBy(input, err.id);
        input.classList.remove('is-invalid');
      } else {
        err.textContent = text;
        // Squawk 0238 (M31 F4 L03b): role=alert on show (a hidden pre-existing alert
        // is unreliable), removed on clear; the input stays linked through aria-describedby.
        err.setAttribute('role', 'alert');
        err.hidden = false;
        input.setAttribute('aria-invalid', 'true');
        util.addDescribedBy(input, err.id);
        input.classList.add('is-invalid');
      }
    }

    function nameCell(row, colIdx, n) {
      var column = columns[colIdx];
      var name = inputName(colIdx, n);
      row.inputs[column.key].setAttribute('aria-label', name);
      var ctl = row.secrets[column.key];
      if (ctl) ctl.setLabels('Show value, row ' + n, 'Hide value, row ' + n);
    }

    // One internal cell builder per column type.
    function buildCell(column, colIdx, row) {
      var td = util.el('td', { className: 'ui-kv-cell' });
      row.cells[column.key] = td;
      var type = typeOf(column);
      if (type === 'toggle') {
        td.classList.add('ui-kv-toggle');
        var tg = App.ui.toggle({
          label: column.ariaLabel || labelText[colIdx],
          labelHidden: true,
          checked: !!row.data[column.key],
          testid: column.inputTestid
        });
        row.toggles[column.key] = tg;
        row.inputs[column.key] = tg.control;
        td.appendChild(util.el('div', { className: 'ui-kv-center' }, [tg.el]));
      } else {
        if (type === 'secret') td.classList.add('ui-kv-secret');
        td.appendChild(buildValueControl(column, row));
      }
      var err = util.el('div', { className: 'ui-kv-error', id: util.uid('kv-err') });
      err.hidden = true;
      td.appendChild(err);
      row.errors[column.key] = err;
      row.errText[column.key] = '';
      placeHint(row, column.key);
      return td;
    }

    // Rebuilds only one secret cell's control (masking switched), carrying over the error
    // state, the names, and focus when the value input had it.
    function rebuildSecret(row, column, colIdx) {
      var td = row.cells[column.key];
      var old = row.inputs[column.key];
      var hadFocus = document.activeElement === old;
      var oldCtl = row.secrets[column.key];
      var oldNodes = [oldCtl ? oldCtl.el : old];
      if (oldCtl && oldCtl.hintEl) oldNodes.push(oldCtl.hintEl);
      var node = buildValueControl(column, row);
      td.insertBefore(node, oldNodes[0]);
      oldNodes.forEach(function (n) {
        if (n.parentNode === td) td.removeChild(n);
      });
      placeHint(row, column.key);
      var r = rows.indexOf(row);
      nameCell(row, colIdx, r + 1);
      applyError(row, column.key);
      if (hadFocus) row.inputs[column.key].focus();
    }

    function newRow(data) {
      keyCounter += 1;
      var row = {
        key: keyCounter, data: {}, inputs: {}, errors: {}, errText: {}, cells: {},
        secrets: {}, toggles: {}, baseline: {}, tr: null, remove: null
      };
      var k;
      for (k in data) {
        if (Object.prototype.hasOwnProperty.call(data, k)) row.data[k] = data[k];
      }
      for (var i = 0; i < columns.length; i++) {
        var v = row.data[columns[i].key];
        if (typeOf(columns[i]) === 'toggle') row.data[columns[i].key] = !!v;
        else row.data[columns[i].key] = v === undefined || v === null ? '' : String(v);
        var sk = columns[i].storedKey;
        if (sk && row.data[sk] !== undefined && row.data[sk] !== null) row.data[sk] = String(row.data[sk]);
      }
      captureBaselines(row);
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
      td.appendChild(util.el('div', { className: 'ui-kv-center' }, [row.remove]));
      tr.appendChild(td);
      row.tr = tr;
      return row;
    }

    function renumber() {
      for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        row.tr.setAttribute('data-row-idx', String(r));
        for (var i = 0; i < columns.length; i++) nameCell(row, i, r + 1);
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

    function setRow(i, patch) {
      var row = rows[i];
      if (!row || !patch) return;
      var before = copyData(row);
      var k;
      for (k in patch) {
        if (!Object.prototype.hasOwnProperty.call(patch, k)) continue;
        var column = null;
        for (var c2 = 0; c2 < columns.length; c2++) if (columns[c2].key === k) column = columns[c2];
        var v = patch[k];
        if (column && typeOf(column) === 'toggle') row.data[k] = !!v;
        else if (column || isStoredKey(k)) row.data[k] = v === undefined || v === null ? '' : String(v);
        else row.data[k] = v;
      }
      for (var ci = 0; ci < columns.length; ci++) {
        var sk = columns[ci].storedKey;
        if (sk && Object.prototype.hasOwnProperty.call(patch, sk) && row.data[sk]) {
          row.baseline[columns[ci].key] = trimmedKey(row);
        }
      }
      for (var j = 0; j < columns.length; j++) {
        var col2 = columns[j];
        var key = col2.key;
        var type = typeOf(col2);
        var input = row.inputs[key];
        if (type === 'toggle') {
          if (row.data[key] !== before[key]) row.toggles[key].setChecked(row.data[key]);
          continue;
        }
        var maskChanged = type === 'secret' && isMasked(col2, row) !== !!row.secrets[key];
        var storedChanged = type === 'secret' && col2.storedKey && row.data[col2.storedKey] !== before[col2.storedKey];
        var valueChanged = row.data[key] !== before[key];
        if (maskChanged) {
          rebuildSecret(row, col2, j);
          row.errText[key] = '';
          applyError(row, key);
          continue;
        }
        if (!valueChanged && !storedChanged) continue;
        var focused = document.activeElement === input;
        var s0 = focused ? input.selectionStart : 0;
        var s1 = focused ? input.selectionEnd : 0;
        var ctl = row.secrets[key];
        if (ctl) {
          if (storedChanged) ctl.setStored(row.data[col2.storedKey] || null);
          if (valueChanged || storedChanged) ctl.setValue(row.data[key]);
        } else {
          input.value = row.data[key];
        }
        if (focused) {
          var len = input.value.length;
          try { input.setSelectionRange(Math.min(s0, len), Math.min(s1, len)); } catch (err) { /* not selectable */ }
        }
        if (valueChanged) {
          row.errText[key] = '';
          applyError(row, key);
        }
        placeHint(row, key);
      }
      renumber();
    }

    function isStoredKey(k) {
      for (var i = 0; i < columns.length; i++) if (columns[i].storedKey === k) return true;
      return false;
    }

    function setError(rowIndex, colKey, text) {
      var row = rows[rowIndex];
      if (!row || !row.inputs[colKey]) return;
      row.errText[colKey] = text === null || text === undefined ? '' : String(text);
      applyError(row, colKey);
    }

    function focusRow(i, colKey) {
      if (rows[i]) focusInput(rows[i], colKey);
    }

    setValues(opts.rows);

    return {
      el: root,
      values: values,
      setValues: setValues,
      setRow: setRow,
      setError: setError,
      focusRow: focusRow,
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        root.removeEventListener('input', onInput);
        root.removeEventListener('change', onChangeEvt);
        root.removeEventListener('click', onClick);
      }
    };
  };
})();
