// App.studio.mcpEditor.envHeaders — the MCP source editor's Environment
// Variables / Custom Headers key-value table (M31 F5 L02, split out of
// mcp-server-editor.js, moved verbatim).
//
// Holds: collectExistingKvRows, renderKvTable / renderKvRow (the string-built
// table), updateKvHeadVisibility, handleSensitiveToggle, partitionKvRows (the
// payload split into plaintext and secrets, with the per-key __MASKED__
// round-trip) and wire(container, onChange), the delegated input / change /
// click handlers and the Add-row button.
// Exposes: collectExistingKvRows, renderKvTable, renderKvRow,
// updateKvHeadVisibility, handleSensitiveToggle, partitionKvRows, wire.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var MASKED_SENTINEL = window.App.studio.mcpEditor.shared.MASKED_SENTINEL;

  function collectExistingKvRows(source, type) {
    /* Walk source.config.env (stdio) or source.config.headers
       (streamable-http) AND source.secrets to build the kv-row union list.
       Per-row data shape: { key, value, sensitive, _originalMasked }.
       For sensitive rows the value field is the masked tail, captured into
       _originalMasked for round-trip preservation. */
    var rows = [];
    if (!source) return rows;
    var cfg = source.config || {};
    var plaintextDict = (type === 'streamable-http') ? (cfg.headers || {}) : (cfg.env || {});
    var secrets = source.secrets || {};
    var seen = Object.create(null);

    // Plaintext rows first (in dict-iteration order).
    for (var k in plaintextDict) {
      if (Object.prototype.hasOwnProperty.call(plaintextDict, k)) {
        rows.push({ key: k, value: String(plaintextDict[k]), sensitive: false, _originalMasked: '' });
        seen[k] = true;
      }
    }
    // Sensitive rows.
    for (var sk in secrets) {
      if (!Object.prototype.hasOwnProperty.call(secrets, sk)) continue;
      if (seen[sk]) continue; // operator may have a duplicate key; plaintext wins.
      var maskedVal = String(secrets[sk] == null ? '' : secrets[sk]);
      rows.push({ key: sk, value: maskedVal, sensitive: true, _originalMasked: maskedVal });
    }
    return rows;
  }

  // F9 L1: hint copy migrated from a `<p class="kv-hint">` paragraph below
  // the table to the title attribute of an info icon next to the
  // "Sensitive" column header. Single source of truth for the tooltip text.
  var SENSITIVE_HINT = 'Sensitive values are encrypted at rest. ' +
    'Unchecking Sensitive on a stored secret clears the value — re-type to keep it.';

  function renderKvTable(source, type) {
    var escapeAttr = window.App.escapeAttr;
    var escapeHtml = window.App.escapeHtml;
    var existingRows = collectExistingKvRows(source, type);
    // F9 L1: thead is hidden when the table has zero rows (empty state).
    // The `is-hidden` class is toggled at row-add / row-remove time so the
    // header reveals itself with the first data row.
    var headHiddenClass = existingRows.length === 0 ? ' is-hidden' : '';
    // F9 L1: info icon (existing studio pattern from tools-form-helpers.js)
    // next to the "Sensitive" column header. Tooltip explains the
    // encrypted-at-rest contract and the unchecking-clears-value rule.
    var infoIconHtml = (window.App && window.App.icon) ? window.App.icon('info') : 'ⓘ';
    var sensitiveHeader = 'Sensitive ' +
      '<button type="button" class="field-info-icon mcp-kv-sensitive-info" ' +
      'title="' + escapeAttr(SENSITIVE_HINT) + '" ' +
      'aria-label="' + escapeAttr(SENSITIVE_HINT) + '" ' +
      'data-testid="mcp-kv-sensitive-info">' + infoIconHtml + '</button>';
    var html = '<table class="mcp-kv-table" data-testid="mcp-kv-table">';
    html += '<thead class="mcp-kv-thead' + headHiddenClass + '" data-testid="mcp-kv-thead">' +
            '<tr><th>Key</th><th>Value</th>' +
            '<th class="mcp-kv-th-sensitive">' + sensitiveHeader + '</th>' +
            '<th aria-label="Actions"></th></tr></thead>';
    html += '<tbody data-testid="mcp-kv-tbody">';
    for (var i = 0; i < existingRows.length; i++) {
      html += renderKvRow(existingRows[i], i);
    }
    html += '</tbody></table>';
    html += '<button type="button" class="btn-outlined-primary kv-add-row-btn" data-testid="kv-add-row-btn">+ Add row</button>';
    // Suppress unused-var warning in legacy environments — referenced indirectly above.
    void escapeHtml;
    return html;
  }

  function renderKvRow(row, idx) {
    var escapeAttr = window.App.escapeAttr;
    var sensitive = !!row.sensitive;
    var inputType = sensitive ? 'password' : 'text';
    var origMasked = row._originalMasked || '';
    var html = '';
    html += '<tr class="mcp-kv-row" data-row-idx="' + idx + '">';
    html += '<td><input class="field-input kv-key-input" data-field="kv-key" data-row="' + idx + '" value="' + escapeAttr(row.key || '') + '" placeholder="KEY" /></td>';
    html += '<td><div class="api-key-wrap">';
    html += '<input class="field-input kv-value-input' + (sensitive ? ' kv-value-secret' : '') + '" type="' + inputType + '" data-field="kv-value" data-row="' + idx + '" value="' + escapeAttr(row.value || '') + '" data-original-masked="' + escapeAttr(origMasked) + '" placeholder="value" />';
    if (sensitive) {
      html += '<button class="api-key-eye kv-eye-btn" type="button" data-row="' + idx + '" aria-label="Show value">' + window.App.icon('eye') + '</button>';
    }
    html += '</div></td>';
    // F9 L1: per-row sensitive control switched from <input type="checkbox">
    // to the studio iOS-style toggle pattern (`tool-enable-switch` + track).
    // The checkbox is visually-hidden inside the label; CSS in admin.css
    // renders the toggle. The class name `kv-sensitive-checkbox` is kept
    // on the input element so partitionKvRows / handleSensitiveToggle /
    // getFormSnapshot continue to match the same selector.
    html += '<td class="mcp-kv-sensitive-cell">';
    html += '<label class="tool-enable-switch mcp-kv-sensitive-switch" aria-label="Mark sensitive">';
    html += '<input type="checkbox" class="kv-sensitive-checkbox" data-field="kv-sensitive" data-row="' + idx + '"' + (sensitive ? ' checked' : '') + ' aria-label="Mark sensitive" />';
    html += '<span class="tool-enable-switch-track" aria-hidden="true"></span>';
    html += '</label>';
    html += '</td>';
    // F9 L1: per-row remove affordance switched from the `x` close-icon to
    // the studio `trash` icon used elsewhere for destructive row actions.
    html += '<td><button type="button" class="kv-remove-row-btn" data-row="' + idx + '" aria-label="Remove row" title="Remove row">' + window.App.icon('trash') + '</button></td>';
    html += '</tr>';
    return html;
  }

  // ── KV table head visibility (F9 L1) ────────────────────────────────
  // The thead is hidden when the table has zero rows (empty-state UX) and
  // revealed once the operator adds the first row. Toggled in three call
  // sites: add-row click, remove-row click, and cancel-revert (where the
  // tbody is rebuilt from the source object).

  function updateKvHeadVisibility(container) {
    var thead = container.querySelector('.mcp-kv-thead');
    if (!thead) return;
    var rowCount = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row').length;
    thead.classList.toggle('is-hidden', rowCount === 0);
  }

  // ── Sensitive toggle helpers ────────────────────────────────────────

  function handleSensitiveToggle(checkbox) {
    /* Toggle the value input's type between password/text + render or
       remove the eye-toggle. Critical: when unchecking sensitive on a
       row whose value still equals _originalMasked, clear the value
       field — otherwise the masked tail leaks into plaintext on save. */
    var row = checkbox.closest('tr.mcp-kv-row');
    if (!row) return;
    var valueInput = row.querySelector('.kv-value-input');
    var wrap = row.querySelector('.api-key-wrap');
    if (!valueInput || !wrap) return;

    if (checkbox.checked) {
      // → sensitive
      valueInput.type = 'password';
      valueInput.classList.add('kv-value-secret');
      // Add eye button if missing.
      if (!wrap.querySelector('.kv-eye-btn')) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'api-key-eye kv-eye-btn';
        btn.setAttribute('data-row', valueInput.dataset.row || '');
        btn.setAttribute('aria-label', 'Show value');
        btn.innerHTML = window.App.icon('eye');
        wrap.appendChild(btn);
      }
    } else {
      // → plaintext
      var origMasked = valueInput.dataset.originalMasked || '';
      if (origMasked && valueInput.value === origMasked) {
        // Clear the masked tail so it doesn't leak into config.env / config.headers.
        valueInput.value = '';
      }
      valueInput.type = 'text';
      valueInput.classList.remove('kv-value-secret');
      var eye = wrap.querySelector('.kv-eye-btn');
      if (eye) eye.parentNode.removeChild(eye);
    }
  }

  function partitionKvRows(container, plaintextDict, secretsDict) {
    var rows = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row');
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var keyEl = row.querySelector('.kv-key-input');
      var valueEl = row.querySelector('.kv-value-input');
      var sensEl = row.querySelector('.kv-sensitive-checkbox');
      if (!keyEl || !valueEl) continue;
      var key = (keyEl.value || '').trim();
      if (!key) continue; // empty key → silently skip
      var value = valueEl.value || '';
      var sensitive = !!(sensEl && sensEl.checked);
      var origMasked = valueEl.dataset.originalMasked || '';
      if (sensitive) {
        if (origMasked && value === origMasked) {
          // Per-row MASKED_SENTINEL — preserves stored secret backend-side.
          secretsDict[key] = MASKED_SENTINEL;
        } else {
          secretsDict[key] = value;
        }
      } else {
        plaintextDict[key] = value;
      }
    }
  }

  // The key/value table's event delegation and the Add-row button, wired once per
  // mount. `onChange` is the controller's dirty check. nextRowIdx starts at the
  // rendered row count and is not reset by Cancel's row rebuild (as before).
  function wire(container, onChange) {
    var checkDirty = onChange;
    var nextRowIdx = container.querySelectorAll('.mcp-kv-table tbody tr.mcp-kv-row').length;

    // ── kv table delegated events ─────────────────────────────────────
    var kvTable = container.querySelector('.mcp-kv-table');
    if (kvTable) {
      // Input/keyup on key/value inputs.
      kvTable.addEventListener('input', function (e) {
        var target = e.target;
        if (!target) return;
        if (target.classList && (target.classList.contains('kv-key-input') || target.classList.contains('kv-value-input'))) {
          checkDirty();
        }
      });

      // Change on sensitive checkbox + click on remove / eye buttons.
      kvTable.addEventListener('change', function (e) {
        var target = e.target;
        if (!target) return;
        if (target.classList && target.classList.contains('kv-sensitive-checkbox')) {
          handleSensitiveToggle(target);
          checkDirty();
        }
      });

      kvTable.addEventListener('click', function (e) {
        var target = e.target;
        if (!target) return;
        // Eye toggle (button OR svg inside)
        var eyeBtn = target.closest && target.closest('.kv-eye-btn');
        if (eyeBtn) {
          var row = eyeBtn.closest('tr.mcp-kv-row');
          if (row) {
            var valueInput = row.querySelector('.kv-value-input');
            if (valueInput) {
              if (valueInput.type === 'password') {
                valueInput.type = 'text';
                eyeBtn.innerHTML = window.App.icon('eye-off');
                eyeBtn.setAttribute('aria-label', 'Hide value');
              } else {
                valueInput.type = 'password';
                eyeBtn.innerHTML = window.App.icon('eye');
                eyeBtn.setAttribute('aria-label', 'Show value');
              }
            }
          }
          return;
        }
        // Remove row
        var removeBtn = target.closest && target.closest('.kv-remove-row-btn');
        if (removeBtn) {
          var rrow = removeBtn.closest('tr.mcp-kv-row');
          if (rrow) {
            rrow.parentNode.removeChild(rrow);
            updateKvHeadVisibility(container);
            checkDirty();
          }
          return;
        }
      });
    }

    // ── Add-row button ────────────────────────────────────────────────
    var addRowBtn = container.querySelector('.kv-add-row-btn');
    if (addRowBtn) {
      addRowBtn.addEventListener('click', function () {
        var tbody = container.querySelector('.mcp-kv-table tbody');
        if (!tbody) return;
        var idx = nextRowIdx++;
        var emptyRow = { key: '', value: '', sensitive: false, _originalMasked: '' };
        var tmp = document.createElement('tbody');
        tmp.innerHTML = renderKvRow(emptyRow, idx);
        var newTr = tmp.querySelector('tr.mcp-kv-row');
        if (newTr) {
          tbody.appendChild(newTr);
          updateKvHeadVisibility(container);
          checkDirty();
        }
      });
    }
  }

  window.App.studio.mcpEditor.envHeaders = {
    collectExistingKvRows: collectExistingKvRows,
    renderKvTable: renderKvTable,
    renderKvRow: renderKvRow,
    updateKvHeadVisibility: updateKvHeadVisibility,
    handleSensitiveToggle: handleSensitiveToggle,
    partitionKvRows: partitionKvRows,
    wire: wire
  };
})();
