// App.studio.mcpEditor.envHeaders — the MCP source editor's Environment variables /
// Headers section, built from the control library (M31 F5 L07, DD4, DD5).
//
//   create({source, type, onChange}) -> {el, values(), isDirty(), revert(), setType(type),
//     partition(plaintextDict, secretsDict), remaskAfterSave(submitted, response), destroy()}
//
// el is an App.ui.section (stack layout, testid mcp-env-headers-section) titled
// "Environment variables" (stdio) or "Headers" (streamable-http) holding one
// App.ui.keyValueTable (testid mcp-kv-table, Add row testid kv-add-row-btn) with a Key
// column, a Value column (a secret column: stored mode for a stored mask) and a Sensitive
// switch column. The section is hidden while no type is chosen (A17).
//
// Row model: {_rid, key, value, sensitive, _originalMasked}. `_rid` is a stable id this
// module gives every row (a non-column key the table round-trips), so nothing is matched
// by position. `_originalMasked` is the server's mask for a stored secret (value starts
// equal to it); the table's stored mode, the rename rule and clearOnUnmask run off it.
//
// The module keeps its own baseline rows (the mount's rows, then the last Save's), so
// isDirty() and revert() do not depend on the controller's stale `source`:
//   isDirty()  compares by _rid on key, value and sensitive; the set of _rids matters
//              too (a row added or removed); order never does.
//   revert()   sets the table to the baseline rows, silently.
//   remaskAfterSave(submitted, response)  `submitted` is partition()'s record from the
//              Save click. A submitted sensitive row that is unchanged since the click and
//              whose key the server stored goes to stored mode with the server's mask
//              (defect 4); one sent as __MASKED__ that the server dropped leaves stored
//              mode and clears. Then the baseline becomes the live rows, except rows
//              edited, removed or added during the request, which keep the submitted
//              values (or stay out), so the form is clean after a Save but not after an
//              edit made while the PUT was in flight.
//   partition(plain, secrets)  fills the two dicts exactly as the server's contract wants
//              (DD5): a blank key is skipped; a sensitive row whose value still equals its
//              stored mask sends the __MASKED__ sentinel (never the mask shape); any other
//              sensitive row sends its value (an empty one sends ''); a plain row goes to
//              `plain`; for a duplicate key the last row wins. Returns the per-row record
//              {_rid -> {rawKey, rawValue, sensitive, origMasked, sent, key, sentValue,
//              won}} that the controller stashes at the Save click.
//   setType(type)  swaps the title and rebuilds the table under the new label with the
//              current rows ('' hides the section).
// No attribute ever holds a secret: values travel through the inputs' .value only.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  // The title, hint, row source and column definitions are shared with the agent tile
  // (mcp-editor-shared.js, sortie 09 L06).
  var shared = window.App.studio.mcpEditor.shared;
  var MASKED_SENTINEL = shared.MASKED_SENTINEL;
  var titleFor = shared.titleFor;
  var hintFor = shared.hintFor;
  var rowsFromSource = shared.rowsFromSource;

  function create(opts) {
    opts = opts || {};
    var ui = window.App.ui;
    var alive = true;
    var ridCounter = 0;
    var currentType = opts.type || '';
    var built = null;
    var table = null;

    function nextRid() {
      ridCounter += 1;
      return 'r' + ridCounter;
    }
    function report() { if (alive && opts.onChange) opts.onChange(); }

    function snapshotOf(row) {
      return {
        _rid: row._rid, key: String(row.key), value: String(row.value),
        sensitive: !!row.sensitive, _originalMasked: String(row._originalMasked || '')
      };
    }

    var baseline = rowsFromSource(opts.source, currentType).map(function (r) {
      r._rid = nextRid();
      return r;
    });

    function removeLabel(n, row) {
      var key = String(row.key || '').trim();
      return key ? 'Remove ' + key : 'Remove row ' + n;
    }

    function buildTable(type, rows) {
      if (built) built.destroy();
      var cols = shared.tableColumns(false);
      var t = ui.keyValueTable({
        label: titleFor(type),
        testid: 'mcp-kv-table',
        addTestid: 'kv-add-row-btn',
        addAriaLabel: 'Add row to ' + titleFor(type),
        keyColumn: 'key',
        columns: cols.columns,
        rows: rows,
        removeLabel: removeLabel,
        onChange: function () {
          if (table) liveRows();
          report();
        }
      });
      cols.finish(t);
      built = cols;
      return t;
    }

    table = buildTable(currentType, baseline.map(function (r) { return snapshotOf(r); }));
    var section = ui.section({
      title: titleFor(currentType), layout: 'stack', testid: 'mcp-env-headers-section',
      description: hintFor(currentType),
      descriptionTestid: 'mcp-env-headers-hint',
      children: [table.el]
    });
    section.el.hidden = !currentType;

    // The table's rows, with a _rid on every one (a row the Add button just made has none).
    function liveRows() {
      var vals = table.values();
      for (var i = 0; i < vals.length; i++) {
        if (!vals[i]._rid) {
          vals[i]._rid = nextRid();
          table.setRow(i, { _rid: vals[i]._rid });
        }
      }
      return vals;
    }

    function indexOfRid(rows, rid) {
      for (var i = 0; i < rows.length; i++) if (rows[i]._rid === rid) return i;
      return -1;
    }

    function isDirty() {
      var live = liveRows();
      if (live.length !== baseline.length) return true;
      var byRid = Object.create(null);
      var i;
      for (i = 0; i < baseline.length; i++) byRid[baseline[i]._rid] = baseline[i];
      for (i = 0; i < live.length; i++) {
        var b = byRid[live[i]._rid];
        if (!b) return true;
        if (b.key !== live[i].key || b.value !== live[i].value ||
            !!b.sensitive !== !!live[i].sensitive) return true;
      }
      return false;
    }

    function revert() {
      table.setValues(baseline.map(snapshotOf));
    }

    function setType(type) {
      type = type || '';
      section.el.hidden = !type;
      if (titleFor(type) === titleFor(currentType)) {
        currentType = type;
        return;
      }
      currentType = type;
      section.setTitle(titleFor(type));
      var hintEl = section.el.querySelector('[data-testid="mcp-env-headers-hint"]');
      if (hintEl) hintEl.textContent = hintFor(type);
      var old = table;
      var rows = liveRows();
      table = buildTable(type, rows);
      old.destroy();
      section.el.replaceChild(table.el, old.el);
    }

    function partition(plain, secrets) {
      var live = liveRows();
      var record = {};
      var last = Object.create(null);
      var i;
      for (i = 0; i < live.length; i++) {
        var row = live[i];
        var key = String(row.key).trim();
        var sensitive = !!row.sensitive;
        var orig = String(row._originalMasked || '');
        var value = String(row.value);
        var rec = {
          rawKey: String(row.key), rawValue: value, sensitive: sensitive, origMasked: orig,
          sent: false, key: key, sentValue: null, won: false
        };
        record[row._rid] = rec;
        if (!key) continue; // a blank key is skipped
        rec.sent = true;
        if (sensitive) {
          rec.sentValue = (orig && value === orig) ? MASKED_SENTINEL : value;
          secrets[key] = rec.sentValue;
        } else {
          rec.sentValue = value;
          plain[key] = value;
        }
        last[(sensitive ? 's:' : 'p:') + key] = row._rid;
      }
      for (var rid in record) {
        if (!Object.prototype.hasOwnProperty.call(record, rid) || !record[rid].sent) continue;
        record[rid].won = last[(record[rid].sensitive ? 's:' : 'p:') + record[rid].key] === rid;
      }
      return record;
    }

    function remaskAfterSave(submitted, response) {
      if (!alive) return;
      var secrets = (response && response.secrets) || {};
      var live = liveRows();
      var unchanged = Object.create(null);
      var rid;
      for (rid in submitted || {}) {
        if (!Object.prototype.hasOwnProperty.call(submitted, rid)) continue;
        var rec = submitted[rid];
        var idx = indexOfRid(live, rid);
        if (idx === -1) continue;
        var row = live[idx];
        if (row.key === rec.rawKey && row.value === rec.rawValue &&
            !!row.sensitive === rec.sensitive && String(row._originalMasked || '') === rec.origMasked) {
          unchanged[rid] = true;
        } else {
          continue; // edited during the request: left alone
        }
        if (!rec.sent || !rec.won || !rec.sensitive) continue;
        if (Object.prototype.hasOwnProperty.call(secrets, rec.key)) {
          var mask = String(secrets[rec.key] == null ? '' : secrets[rec.key]);
          table.setRow(idx, { value: mask, _originalMasked: mask });
        } else if (rec.sentValue === MASKED_SENTINEL) {
          // The server dropped the key: the row is no longer a stored secret.
          table.setRow(idx, { value: '', _originalMasked: '' });
        }
      }
      var after = liveRows();
      var next = [];
      for (rid in submitted || {}) {
        if (!Object.prototype.hasOwnProperty.call(submitted, rid)) continue;
        var s = submitted[rid];
        var at = indexOfRid(after, rid);
        if (at !== -1 && unchanged[rid]) {
          next.push(snapshotOf(after[at]));
        } else {
          next.push({
            _rid: rid, key: s.rawKey, value: s.rawValue, sensitive: s.sensitive,
            _originalMasked: s.origMasked
          });
        }
      }
      baseline = next;
    }

    // ── The silent handles for a GleepGlorp fill and an approval's follow (M36 F4 L4b) ──
    // None fires onChange; the controller recomputes dirty itself.

    // Header names compare case-insensitively, environment names exactly.
    function fold(key) {
      key = String(key).trim();
      return currentType === 'streamable-http' ? key.toLowerCase() : key;
    }

    function liveIndexOf(rows, key) {
      var f = fold(key);
      for (var i = 0; i < rows.length; i++) if (fold(rows[i].key) === f) return i;
      return -1;
    }

    // What the table holds for `key` now: {exists, value, sensitive, masked, dirty}. A row is
    // dirty when it differs from the baseline row of the same _rid, or has none (a row added
    // here is not in the baseline).
    function rowState(key) {
      var live = liveRows();
      var i = liveIndexOf(live, key);
      if (i === -1) return { exists: false };
      var row = live[i];
      var b = null;
      for (var j = 0; j < baseline.length; j++) if (baseline[j]._rid === row._rid) b = baseline[j];
      var dirty = !b || b.key !== row.key || b.value !== row.value ||
        !!b.sensitive !== !!row.sensitive;
      return {
        exists: true, value: String(row.value), sensitive: !!row.sensitive,
        masked: !!row._originalMasked, dirty: dirty
      };
    }

    // Merge {key, value} entries by key: an existing row takes the value; a new row is
    // appended with a fresh _rid. An empty value is the handoff: the row is added Sensitive
    // and unstored, for the operator to fill in. Every other row stays as it is.
    function setRows(entries) {
      var live = liveRows();
      var added = [];
      entries.forEach(function (e) {
        var i = liveIndexOf(live, e.key);
        if (i !== -1) {
          table.setRow(i, { value: e.value });
          live[i].value = e.value;
        } else {
          added.push({
            _rid: nextRid(), key: e.key, value: e.value,
            sensitive: e.value === '', _originalMasked: ''
          });
        }
      });
      if (added.length) table.setValues(liveRows().concat(added));
    }

    // The note under the table: placed after it, and described by the table itself.
    function placeTableNote(note) {
      section.el.appendChild(note);
      var t = table.el.querySelector('table');
      return t ? [t] : [];
    }

    // Take an approved change from the stored `rows` (rowsFromSource form). Per row, by key:
    // a new row is added to the table and the baseline; a clean row takes the new value; a
    // dirty row keeps the operator's value while its baseline moves to the stored one. A row
    // the stored side no longer has is left alone (an approval never removes one).
    function rebaseTo(rows) {
      var live = liveRows();
      var next = baseline.map(snapshotOf);
      var added = [];
      rows.forEach(function (n) {
        var li = liveIndexOf(live, n.key);
        var bi = -1;
        var f = fold(n.key);
        for (var j = 0; j < next.length; j++) if (fold(next[j].key) === f) bi = j;
        var stored = {
          key: String(n.key), value: String(n.value), sensitive: !!n.sensitive,
          _originalMasked: String(n._originalMasked || '')
        };
        if (li === -1) {
          if (bi !== -1) {
            // The operator removed the row: it stays removed (dirty); only the baseline moves.
            next[bi] = Object.assign({ _rid: next[bi]._rid }, stored);
          } else {
            var rid = nextRid();
            next.push(Object.assign({ _rid: rid }, stored));
            added.push(Object.assign({ _rid: rid }, stored));
          }
          return;
        }
        var row = live[li];
        var old = null;
        for (var k = 0; k < next.length; k++) if (next[k]._rid === row._rid) old = next[k];
        var clean = !!old && old.key === row.key && old.value === row.value &&
          !!old.sensitive === !!row.sensitive;
        if (clean) {
          table.setRow(li, {
            key: stored.key, value: stored.value, sensitive: stored.sensitive,
            _originalMasked: stored._originalMasked
          });
        }
        var entry = Object.assign({ _rid: row._rid }, stored);
        if (old) next[next.indexOf(old)] = entry;
        else next.push(entry);
      });
      baseline = next;
      if (added.length) table.setValues(liveRows().concat(added));
    }

    return {
      el: section.el,
      rowState: rowState,
      setRows: setRows,
      placeTableNote: placeTableNote,
      rebaseTo: rebaseTo,
      rowKind: function () { return currentType === 'streamable-http' ? 'headers' : 'env'; },
      values: liveRows,
      isDirty: isDirty,
      revert: revert,
      setType: setType,
      partition: partition,
      remaskAfterSave: remaskAfterSave,
      destroy: function () {
        alive = false;
        table.destroy();
        if (built) built.destroy();
      }
    };
  }

  window.App.studio.mcpEditor.envHeaders = { create: create };
})();
