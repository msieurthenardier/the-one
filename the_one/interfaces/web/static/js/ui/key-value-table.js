(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var CELL_TYPES = { text: true, secret: true, toggle: true };
  var RENAME_HINT = 'Sensitive values must be re-entered when the key changes.';

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
  //   its stored mask and the cell's hint reads "Sensitive values must be re-entered when the key changes." (one
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
  //   Row options (sortie 09 L05, flight DD12; each is inert when not passed):
  //   readOnly (construct-time): every input is read-only and focusable, no Add row, no remove
  //   column or header, toggles are disabled, and a 'secret' column renders as plain text showing
  //   the row's value as given (the caller passes the mask string or the clear value); it wins
  //   over lockBy and removableBy. lockBy '<row field>': the field is a space-separated list of
  //   'key' (the key input is read-only), 'row' (every input read-only, toggle and remove disabled)
  //   and 'toggle' (the Sensitive-style toggles are checked and disabled, the rest stays editable;
  //   sortie 09 L06), e.g. 'key toggle'. onBeforeRemove(row, index): returning false cancels
  //   the splice (no onChange; focus returns to that row's remove button).
  //   markerBy '<row field>' + markerLabel: a row whose field is truthy shows a pill of real
  //   text (.ui-kv-marker) in the key cell, linked to the key input by aria-describedby. removableBy '<row field>': a row whose field is false has a natively
  //   disabled remove button (not focusable; it keeps its name). setRow re-evaluates these from a
  //   patch without rebuilding the row or moving focus.
  //   Sortie 18 L01 (flight DD3, DD4, DD10; each inert when not passed):
  //   movable (construct-time): each row's actions cell holds Move up, Move down and Remove
  //   (icon-only ghost buttons, .ui-kv-move, chevron-up/down; moveUpTestid, moveDownTestid;
  //   names "Move row n up|down" or moveLabel(n, rowCopy, 'up'|'down'), refreshed by
  //   renumber and on typing in the key column). The first row's Move up and the last row's
  //   Move down are natively disabled (renumber owns the edge state). A move reorders values(),
  //   moves the NEIGHBOUR's tr so the pressed row's DOM node and any setError stay with it,
  //   puts focus on the pressed button (or the row's other move button when it became
  //   disabled), writes "Moved to row n of total." to one visually hidden role=status node
  //   (.ui-kv-live, after Add; emptied then written a tick later; none without movable or
  //   with readOnly) and fires onChange(values, {type: 'move'}) once. A click on a disabled
  //   move button does nothing. readOnly builds no move buttons; movable with lockBy,
  //   removableBy or markerBy throws.
  //   fill: true gives a table with no secret or toggle column the fixed layout (full width of
  //   the root; a column width then applies). headHidden: true puts every column label inside
  //   span.visually-hidden in its th and adds ui-kv-table--head-hidden (the head row takes no
  //   height; emptyHidesHead still hides the thead). focus(): the first row's first input,
  //   else the Add row button; nothing for a readOnly table with no rows.
  //   addAriaLabel (a string; sortie 18 HAT fix, inert when absent or empty: no aria-label
  //   attribute at all): the Add button's accessible name, with the visible addLabel unchanged,
  //   so a page with several tables can tell its Add buttons apart. The name deliberately omits
  //   the "+" of the visible label. Not built under readOnly (there is no Add button).
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
    var readOnly = opts.readOnly === true;
    var lockBy = opts.lockBy || null;
    var markerBy = opts.markerBy || null;
    var removableBy = opts.removableBy || null;
    var movableOpt = opts.movable === true;
    var headHidden = opts.headHidden === true;
    if (movableOpt) {
      if (lockBy) throw new Error('App.ui.keyValueTable: movable cannot be combined with lockBy');
      if (removableBy) throw new Error('App.ui.keyValueTable: movable cannot be combined with removableBy');
      if (markerBy) throw new Error('App.ui.keyValueTable: movable cannot be combined with markerBy');
    }
    var movable = movableOpt && !readOnly;
    if (opts.fill === true) fixed = true;
    var rows = [];
    var keyCounter = 0;
    var destroyed = false;
    var announceTimer = null;

    function typeOf(column) {
      return column.type || 'text';
    }

    var root = util.el('div', { className: 'ui-kv' });
    var table = util.el('table', {
      className: 'ui-kv-table' + (fixed ? ' ui-kv-table--fixed' : '') +
        (headHidden ? ' ui-kv-table--head-hidden' : ''),
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
      if (!readOnly) {
        var actionsCol = util.el('col');
        // Three 24px buttons, two 4px gaps and the cell's 16px padding when movable.
        actionsCol.style.width = movable ? '104px' : '48px';
        colgroup.appendChild(actionsCol);
      }
      table.appendChild(colgroup);
    }
    var thead = util.el('thead', { className: 'ui-kv-head' });
    var headRow = util.el('tr');
    var labelText = [];
    for (c = 0; c < columns.length; c++) {
      var lab = columns[c].label;
      var th = util.el('th', { scope: 'col' });
      var holder = headHidden ? util.el('span', { className: 'visually-hidden' }) : th;
      if (headHidden) th.appendChild(holder);
      if (lab && typeof lab === 'object') {
        holder.appendChild(lab);
        labelText.push((lab.textContent || '').trim());
      } else {
        holder.textContent = lab === undefined || lab === null ? '' : String(lab);
        labelText.push(holder.textContent);
      }
      headRow.appendChild(th);
    }
    if (!readOnly) {
      var actionsTh = util.el('th', { scope: 'col' });
      actionsTh.appendChild(util.el('span', { className: 'visually-hidden', text: 'Actions' }));
      headRow.appendChild(actionsTh);
    }
    thead.appendChild(headRow);
    var tbody = util.el('tbody', { className: 'ui-kv-body' });
    table.appendChild(thead);
    table.appendChild(tbody);

    var addBtn = App.ui.button({
      variant: 'secondary',
      label: opts.addLabel || '+ Add row',
      className: 'ui-kv-add',
      ariaLabel: typeof opts.addAriaLabel === 'string' && opts.addAriaLabel ? opts.addAriaLabel : null,
      testid: opts.addTestid
    });
    root.appendChild(table);
    if (!readOnly) root.appendChild(addBtn);
    var liveEl = null;
    if (movable) {
      liveEl = util.el('div', { className: 'ui-kv-live visually-hidden', role: 'status' });
      root.appendChild(liveEl);
    }

    // Empties the status node, then writes the text a tick later, so an identical
    // announcement is spoken again.
    function announce(text) {
      if (!liveEl) return;
      if (announceTimer) clearTimeout(announceTimer);
      liveEl.textContent = '';
      announceTimer = setTimeout(function () {
        announceTimer = null;
        if (destroyed) return;
        liveEl.textContent = text;
      }, 0);
    }

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
      if (readOnly) return false;
      return column.maskedBy ? !!row.data[column.maskedBy] : true;
    }

    // Row state from the row options: which inputs are read-only, whether the toggle and
    // remove are disabled, and the marker pill. Safe to call at any point of a row's build.
    // The lock field is a space-separated list of 'key', 'row' and 'toggle'.
    function lockHas(row, token) {
      var lock = lockBy ? row.data[lockBy] : null;
      if (typeof lock !== 'string' || !lock) return false;
      return (' ' + lock + ' ').indexOf(' ' + token + ' ') !== -1;
    }

    function inputLocked(column, row) {
      if (readOnly) return true;
      return lockHas(row, 'row') || (lockHas(row, 'key') && column.key === keyColumn);
    }

    // 'toggle' lock: every toggle column of the row is checked and cannot change.
    function enforceToggleLock(row) {
      if (readOnly || !lockHas(row, 'toggle')) return;
      for (var i = 0; i < columns.length; i++) {
        if (typeOf(columns[i]) === 'toggle') row.data[columns[i].key] = true;
      }
    }

    function applyMarker(row) {
      if (!row.marker) return;
      var on = !!row.data[markerBy];
      row.marker.hidden = !on;
      var keyInput = row.inputs[keyColumn];
      if (!keyInput) return;
      if (on) util.addDescribedBy(keyInput, row.marker.id);
      else util.removeDescribedBy(keyInput, row.marker.id);
    }

    function applyRowState(row) {
      if (!readOnly && !lockBy && !markerBy && !removableBy) return;
      var rowLocked = !readOnly && lockHas(row, 'row');
      var toggleLocked = !readOnly && lockHas(row, 'toggle');
      for (var i = 0; i < columns.length; i++) {
        var column = columns[i];
        var ctl = row.inputs[column.key];
        if (!ctl) continue;
        if (typeOf(column) === 'toggle') {
          row.toggles[column.key].setDisabled(readOnly || rowLocked || toggleLocked);
        } else {
          ctl.readOnly = inputLocked(column, row);
        }
      }
      if (row.remove) {
        row.remove.disabled =
          !!rowLocked || (!!removableBy && row.data[removableBy] === false);
      }
      applyMarker(row);
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
          if (column.key === keyColumn) {
            checkRename(row);
            if (row.remove) {
              row.remove.setAttribute('aria-label', removeName(row, rows.indexOf(row) + 1));
            }
            nameMoves(row, rows.indexOf(row));
          }
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
      var mv = movable ? t.closest('.ui-kv-move') : null;
      if (mv) {
        // WebKit can deliver a click on a disabled button's children.
        if (mv.disabled) return;
        var mover = rowOfNode(mv);
        if (mover) moveRow(mover, mv.getAttribute('data-move') === 'up' ? -1 : 1, mv);
        return;
      }
      var rm = t.closest('.ui-kv-remove');
      if (rm) {
        // WebKit can deliver a click on a disabled button's children.
        if (rm.disabled) return;
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

    function moveName(row, n, direction) {
      if (typeof opts.moveLabel === 'function') return opts.moveLabel(n, copyData(row), direction);
      return 'Move row ' + n + ' ' + direction;
    }

    // Names and edge state of a row's move buttons (renumber owns both).
    function nameMoves(row, idx) {
      if (!row.up) return;
      row.up.setAttribute('aria-label', moveName(row, idx + 1, 'up'));
      row.down.setAttribute('aria-label', moveName(row, idx + 1, 'down'));
      row.up.disabled = idx === 0;
      row.down.disabled = idx === rows.length - 1;
    }

    // Moves the neighbour's tr, not the pressed row's, so the pressed row's nodes (and its
    // button, which holds focus) never leave the document.
    function moveRow(row, delta, pressed) {
      var idx = rows.indexOf(row);
      var to = idx + delta;
      if (idx === -1 || to < 0 || to >= rows.length) return;
      var other = rows[to];
      rows[idx] = other;
      rows[to] = row;
      if (delta < 0) tbody.insertBefore(other.tr, row.tr.nextSibling);
      else tbody.insertBefore(other.tr, row.tr);
      renumber();
      // A click does not focus a button in WebKit, so focus explicitly: the pressed button,
      // or the row's other move button when the pressed one is now disabled.
      var target = pressed.disabled ? (pressed === row.up ? row.down : row.up) : pressed;
      target.focus();
      announce('Moved to row ' + (to + 1) + ' of ' + rows.length + '.');
      fire('move');
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
      if (inputLocked(column, row)) input.readOnly = true;
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
        secrets: {}, toggles: {}, baseline: {}, tr: null, remove: null, up: null, down: null
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
      enforceToggleLock(row);
      captureBaselines(row);
      var tr = util.el('tr', { className: 'ui-kv-row' });
      if (opts.rowTestid) tr.setAttribute('data-testid', opts.rowTestid);
      if (typeof opts.rowDataset === 'function') util.applyDataset(tr, opts.rowDataset(copyData(row)));
      for (i = 0; i < columns.length; i++) tr.appendChild(buildCell(columns[i], i, row));
      if (!readOnly) {
        var td = util.el('td', { className: 'ui-kv-cell' });
        row.remove = App.ui.button({
          variant: 'ghost',
          iconOnly: true,
          icon: 'trash',
          ariaLabel: 'Remove row',
          className: 'ui-kv-remove',
          testid: opts.removeTestid
        });
        var actions = [row.remove];
        if (movable) {
          row.up = App.ui.button({
            variant: 'ghost', iconOnly: true, icon: 'chevron-up', ariaLabel: 'Move row up',
            className: 'ui-kv-move', testid: opts.moveUpTestid
          });
          row.down = App.ui.button({
            variant: 'ghost', iconOnly: true, icon: 'chevron-down', ariaLabel: 'Move row down',
            className: 'ui-kv-move', testid: opts.moveDownTestid
          });
          row.up.setAttribute('data-move', 'up');
          row.down.setAttribute('data-move', 'down');
          actions = [row.up, row.down, row.remove];
        }
        td.appendChild(util.el('div', {
          className: movable ? 'ui-kv-center ui-kv-center--actions' : 'ui-kv-center'
        }, actions));
        tr.appendChild(td);
      }
      if (markerBy && row.cells[keyColumn]) {
        row.marker = util.el('span', {
          className: 'ui-kv-marker',
          id: util.uid('kv-mark'),
          text: opts.markerLabel || ''
        });
        row.cells[keyColumn].insertBefore(row.marker, row.errors[keyColumn]);
      }
      row.tr = tr;
      applyRowState(row);
      return row;
    }

    function renumber() {
      for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        row.tr.setAttribute('data-row-idx', String(r));
        for (var i = 0; i < columns.length; i++) nameCell(row, i, r + 1);
        if (row.remove) row.remove.setAttribute('aria-label', removeName(row, r + 1));
        nameMoves(row, r);
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
      if (typeof opts.onBeforeRemove === 'function' && opts.onBeforeRemove(copyData(row), idx) === false) {
        // A click does not focus a button in WebKit, so put focus back explicitly.
        if (row.remove) row.remove.focus();
        return;
      }
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
      enforceToggleLock(row);
      for (var ci = 0; ci < columns.length; ci++) {
        var sk = columns[ci].storedKey;
        if (sk && Object.prototype.hasOwnProperty.call(patch, sk) && row.data[sk]) {
          row.baseline[columns[ci].key] = trimmedKey(row);
        }
        // Squawk 0270: a patch that re-baselines the stored value ends the one-off rename hint.
        if (sk && Object.prototype.hasOwnProperty.call(patch, sk) && row.secrets[columns[ci].key]) {
          row.secrets[columns[ci].key].setHint(null);
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
      applyRowState(row);
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

    function focus() {
      if (rows.length) focusInput(rows[0], null);
      else if (!readOnly) addBtn.focus();
    }

    setValues(opts.rows);

    return {
      focus: focus,
      el: root,
      values: values,
      setValues: setValues,
      setRow: setRow,
      setError: setError,
      focusRow: focusRow,
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        if (announceTimer) clearTimeout(announceTimer);
        announceTimer = null;
        root.removeEventListener('input', onInput);
        root.removeEventListener('change', onChangeEvt);
        root.removeEventListener('click', onClick);
      }
    };
  };
})();
