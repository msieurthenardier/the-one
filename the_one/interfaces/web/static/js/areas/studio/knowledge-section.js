// App.studio.renderKnowledgeGrid / renderKnowledgeDetail — Studio's
// Knowledge section (Mission 24 Flight 6 Leg 1, DD-2, L1-D1).
//
// Replaces the F5 `stub-knowledge.js` placeholder with the real global
// knowledge-base inventory: create + delete a knowledge base, register a
// folder (DD-10's refusal-message rendering), and inspect one down to
// individual chunks and source text (DD-8's on-demand fetch). Two-branch
// shape mirroring `mcp-servers-grid.js` + `mcp-server-editor.js` — a grid
// (no selection) and a detail view (one knowledge base selected),
// hash-routed by `studio.js` as `#studio/knowledge` /
// `#studio/knowledge/{kb_id}`.
//
// Built entirely via document.createElement + textContent assignment (the
// `_el` helper below), NOT string-concatenated HTML sinks — Mission 17
// Flight 1's dynamic-sink baseline freeze (see tests/test_ui_guards.py)
// forbids new dynamic HTML-sink call sites. This mirrors `connector-
// editor.js` and `self-configuration-tab.js`, NOT the pre-freeze string-
// template style still visible in `mcp-servers-grid.js` (grandfathered
// baseline entry, L1-D3's "do not copy this style" precedent). Every
// container clear below assigns a bare empty string literal to
// `textContent` — outside the guard's scanned sink set entirely, and a
// static single-string-literal even if it were scanned.
//
// L1-D2: the 5-second status poll is owned by `studio.js`, not this
// module — `renderKnowledgeDetail` returns `{ updateStatus(status) }`, a
// handle the orchestrator calls on each poll tick so the status summary +
// folders list refresh WITHOUT rebuilding the items list, an open chunks/
// source panel, or the search form (none of those are polled — L1-D2's
// Cache Declaration: only status is fetched on an interval; items, chunks
// and source text are fetched "at the moment they are displayed").
//
// kb-studio-round-trip remediation (2026-09-18, FIX 1): L1-D2's Cache
// Declaration mis-grouped the ITEMS LIST with chunks/source — chunks and
// source really are on-demand, but the items list is displayed
// continuously, so "fetched at the moment it's displayed" collapsed to
// "fetched once at mount and never again" while the status chips beside
// it kept polling. `renderKnowledgeDetail` now also returns
// `updateItems(items)`, called by `studio.js` only when the status poll's
// per-status + chunk counts differ from what the list was last rendered
// against (never on every tick — that would blow away an open chunks/
// source panel or scroll position, which is exactly what L1-D2 was
// protecting). `updateItems` only ever touches `itemsListEl`'s children;
// `chunksPanel`/`sourcePanel` are separate siblings under `itemsSection`
// and are untouched by a list rebuild, so an open panel survives it.
//
// M24 F06 L05 (HAT-found affordance gaps): three additions, each traced
// back to a leg design decision —
//   L5-D1: each folder row gains a two-step Remove control
//     (App.confirmDelete, button label "Confirm remove?"; the consequence
//     sentence is a static caption beside the control, not the label).
//   L5-D2: the rename-only affordance (F06 L03) is replaced by a single
//     Name + Description edit form with one Save. No server change — the
//     PUT already gates the cross-entity rewrite behind a raw-name check
//     then a derived-name check (L2-D9's two early returns).
//   L5-D4: "View chunks"/"View source" move behind a per-row overflow
//     menu (`buildItemMenu`), built minimal and local to this file — see
//     its own comment block for the accessibility contract.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var STATUS_LABELS = ['pending', 'indexing', 'indexed', 'failed'];

  // ── DOM-builder micro-helpers (no innerHTML anywhere below) ──────────

  function _el(tag, opts) {
    var e = document.createElement(tag);
    opts = opts || {};
    if (opts.className) e.className = opts.className;
    if (opts.text !== undefined) e.textContent = opts.text;
    return e;
  }

  function _btn(className, testid, text) {
    var b = _el('button', { className: className, text: text });
    b.type = 'button';
    if (testid) b.setAttribute('data-testid', testid);
    return b;
  }

  function _input(type, field, value, placeholder) {
    var i = _el('input', { className: 'field-input' });
    i.type = type;
    i.setAttribute('data-field', field);
    i.value = value || '';
    if (placeholder) i.placeholder = placeholder;
    return i;
  }

  // M24 F06 L05 (L5-D2): the create form and the detail view's edit form
  // both gain a Description field. Mirrors connector-editor.js's
  // `_textarea` helper.
  function _textarea(field, value, rows, placeholder) {
    var t = _el('textarea', { className: 'field-textarea' });
    t.setAttribute('data-field', field);
    t.rows = rows;
    t.value = value || '';
    if (placeholder) t.placeholder = placeholder;
    return t;
  }

  // Returns the `.field-group` wrap so callers can append a hint/error
  // span after the control — unlike connector-editor.js's `_fieldGroup`
  // (which returns the control), several fields here need that wrap.
  function _fieldGroup(section, labelText, id, inputEl) {
    var wrap = _el('div', { className: 'field-group' });
    var label = _el('label', { text: labelText });
    label.setAttribute('for', id);
    inputEl.id = id;
    wrap.appendChild(label);
    wrap.appendChild(inputEl);
    section.appendChild(wrap);
    return wrap;
  }

  function _section(container, titleText) {
    var sec = _el('div', { className: 'editor-section' });
    sec.appendChild(_el('div', { className: 'section-title', text: titleText }));
    container.appendChild(sec);
    return sec;
  }

  function _errorMessageFromResponse(body) {
    var detail;
    try {
      var parsed = JSON.parse(body);
      detail = parsed && parsed.detail;
    } catch (_e) {
      // Non-JSON body — fall through.
    }
    if (Array.isArray(detail)) {
      detail = detail.map(function (d) {
        var loc = (d.loc || []).join('.');
        return loc ? (loc + ': ' + d.msg) : d.msg;
      }).join(' | ');
    }
    return detail;
  }

  // AC-7: separator-aware containment — a bare `itemPath.startsWith(
  // folderPath)` is wrong at directory boundaries (folder `/data/foo`
  // would falsely claim item `/data/foobar/x.txt`). `sep` is read off the
  // folder path's own separator (the server stores `str(canonical)` in
  // OS-native form with no guaranteed trailing separator).
  function _containingFolder(item, folders) {
    if (item.parent_id) return null;
    for (var i = 0; i < folders.length; i++) {
      var folderPath = folders[i].path;
      var sep = (folderPath.indexOf('\\') !== -1 && folderPath.indexOf('/') === -1) ? '\\' : '/';
      if (item.path_or_url === folderPath || item.path_or_url.indexOf(folderPath + sep) === 0) {
        return folders[i];
      }
    }
    return null;
  }

  // ── Grid ──────────────────────────────────────────────────────────────
  //
  // Chrome (header + create form) is built ONCE per call; only the tile
  // list itself is rebuilt via the returned `updateList(kbs)` handle. This
  // matters because the create form is transient UI state (open/closed,
  // typed-but-unsubmitted text) that a background list refresh must never
  // clobber — `studio.js` re-fetches the list on every grid mount AND
  // after every create, and a full-container rebuild on that second call
  // would silently close the form (and lose the operator's still-being-
  // typed name) out from under them if the fetch resolved while it was
  // open. Mirrors the detail view's `updateStatus` handle (L1-D2).

  function renderKnowledgeGrid(container, kbs, callbacks) {
    callbacks = callbacks || {};
    var onSelect = callbacks.onSelectKnowledgeBase || function () {};
    var onCreateSuccess = callbacks.onCreateSuccess || function () {};

    container.textContent = '';

    var root = _el('div', { className: 'knowledge-inventory' });
    root.setAttribute('data-testid', 'studio-knowledge-inventory');
    container.appendChild(root);

    var header = _el('div', { className: 'page-header' });
    header.appendChild(_el('h1', { className: 'page-title', text: 'Knowledge' }));
    var newBtn = _btn('btn-outlined-primary', 'new-knowledge-base-btn', 'New Knowledge Base');
    header.appendChild(newBtn);
    root.appendChild(header);

    // ── Create form (AC-2) — collapsed until the CTA is clicked; the CTA
    // itself stays always-visible in the header above (AC-1).
    var createForm = _el('div', { className: 'editor-section knowledge-create-form' });
    createForm.hidden = true;
    root.appendChild(createForm);

    var nameInput = _input('text', 'name', '', 'Knowledge base name');
    nameInput.setAttribute('data-testid', 'kb-create-name-input');
    var nameGroup = _fieldGroup(createForm, 'Name', 'kb-create-name', nameInput);
    // DD-16: advisory only — 43 CODE POINTS ([...name].length), never
    // name.length (UTF-16 units), or an astral character would count
    // double in the browser and single on the server.
    var hint = _el('span', {
      className: 'field-hint',
      text: 'Names over 43 characters get a shortened, hashed tool name.'
    });
    hint.setAttribute('data-testid', 'kb-create-name-hint');
    hint.hidden = true;
    nameGroup.appendChild(hint);
    nameInput.addEventListener('input', function () {
      hint.hidden = Array.from(nameInput.value).length <= 43;
    });

    // AC-4 (M24 F06 L05): the create form also accepts a description —
    // no length rule, nothing derives from it (L5-D2).
    var descInput = _textarea('description', '', 3, 'Optional description');
    descInput.setAttribute('data-testid', 'kb-create-description-input');
    _fieldGroup(createForm, 'Description', 'kb-create-description', descInput);

    // kb-studio-round-trip remediation FIX 3: `.editor-error`'s only rule
    // is scoped `.form-actions .editor-error` (components.css), which this
    // site is not inside — it rendered unstyled. `field-error` (already
    // styled and already used correctly elsewhere in this file) plus a
    // `<div>` (block-level, so the submit button below isn't dragged onto
    // the end of the error text) fixes it with no new CSS vocabulary.
    var createErrorEl = _el('div', { className: 'field-error' });
    createErrorEl.setAttribute('data-testid', 'kb-create-error');
    createForm.appendChild(createErrorEl);

    var createBtn = _btn('btn-filled-primary', 'kb-create-submit-btn', 'Create');
    createForm.appendChild(createBtn);

    newBtn.addEventListener('click', function () {
      createForm.hidden = !createForm.hidden;
      if (!createForm.hidden) nameInput.focus();
    });

    createBtn.addEventListener('click', function () {
      createErrorEl.textContent = '';
      // AC-2: an empty name is refused client-side — no request sent.
      var name = nameInput.value.trim();
      if (!name) {
        createErrorEl.textContent = 'Name is required.';
        return;
      }
      createBtn.disabled = true;
      fetch('/api/knowledge-bases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, description: descInput.value })
      }).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            throw new Error(_errorMessageFromResponse(body) || 'Create failed');
          });
        }
        return r.json();
      }).then(function (kb) {
        nameInput.value = '';
        descInput.value = '';
        hint.hidden = true;
        createForm.hidden = true;
        createBtn.disabled = false;
        onCreateSuccess(kb);
      }).catch(function (err) {
        createBtn.disabled = false;
        createErrorEl.textContent = err.message || String(err);
      });
    });

    // ── Tile grid ────────────────────────────────────────────────────
    var gridEl = _el('div', { className: 'entity-tile-grid' });
    gridEl.setAttribute('role', 'listbox');
    gridEl.setAttribute('aria-label', 'Knowledge bases');
    root.appendChild(gridEl);

    function updateList(nextKbs) {
      gridEl.textContent = '';

      if (nextKbs === null || nextKbs === undefined) {
        gridEl.appendChild(_el('div', { className: 'admin-loading', text: 'Loading knowledge bases…' }));
        return;
      }

      if (nextKbs.length === 0) {
        var empty = _el('div', { className: 'empty-canvas' });
        var inner = _el('div', { className: 'empty-canvas-inner admin-provider-empty' });
        inner.appendChild(_el('div', { text: 'No knowledge bases yet. Create one to get started.' }));
        empty.appendChild(inner);
        gridEl.appendChild(empty);
        return;
      }

      nextKbs.forEach(function (kb) {
        var tile = _el('button', { className: 'entity-tile knowledge-base-tile' });
        tile.type = 'button';
        tile.setAttribute('role', 'option');
        tile.setAttribute('data-testid', 'knowledge-base-card');
        tile.setAttribute('data-id', kb.id);
        tile.appendChild(_el('span', { className: 'entity-tile-name', text: kb.name }));
        tile.appendChild(_el('span', { className: 'entity-tile-meta', text: kb.description || '—' }));
        tile.addEventListener('click', function () { onSelect(kb.id); });
        gridEl.appendChild(tile);
      });
    }
    updateList(kbs);

    return { updateList: updateList };
  }

  // ── Detail ────────────────────────────────────────────────────────────

  function renderKnowledgeDetail(container, kb, state, callbacks) {
    callbacks = callbacks || {};
    state = state || {};
    var items = state.items || [];
    var initialStatus = state.status || null;

    container.textContent = '';

    var root = _el('div', { className: 'knowledge-inventory knowledge-detail' });
    root.setAttribute('data-testid', 'studio-knowledge-inventory');
    container.appendChild(root);

    // ── Header ───────────────────────────────────────────────────────
    var header = _el('div', { className: 'editor-header' });
    var headerText = _el('div', { className: 'editor-header-text' });
    headerText.appendChild(_el('h1', { className: 'editor-title', text: kb.name }));
    header.appendChild(headerText);
    var actions = _el('div', { className: 'form-actions' });
    var editToggleBtn = _btn('btn-outlined-primary', 'edit-knowledge-base-btn', 'Edit');
    actions.appendChild(editToggleBtn);
    var backBtn = _btn('btn-outlined-primary back-btn', 'back-knowledge-btn', '← Back');
    backBtn.setAttribute('aria-label', 'Back to knowledge bases');
    actions.appendChild(backBtn);
    header.appendChild(actions);
    root.appendChild(header);
    // AC-8/L5-D3: the dirty GATE for this click lives in studio.js's
    // `onBack` (mirrors mcp-sources' own onBack, which checks the
    // orchestrator's `dirty` closure var and shows App.confirmDialog
    // itself before proceeding) — this module only ever requests the
    // navigation, never decides to discard unsaved edits on its own.
    backBtn.addEventListener('click', function () {
      if (callbacks.onBack) callbacks.onBack();
    });

    // ── Edit: Name + Description in one form, one Save (AC-5/AC-6/AC-6b/
    // AC-7/AC-8, L5-D2, M24 F06 L05) — replaces the F06 L03 rename-only
    // affordance. Reuses the create form's 43-code-point advisory hint and
    // empty-name refusal (L1-D3's find_label_for_without_control /
    // describedby guards are satisfied the same way the create form
    // satisfies them, via `_fieldGroup`). Collapsed until the button above
    // is clicked; the server needs no change (L5-D2 — `update_knowledge_base`
    // already gates the cross-entity rewrite behind a raw-name check and a
    // derived-name check, so sending `name` unchanged alongside a changed
    // `description` performs zero agent I/O).
    var editForm = _el('div', { className: 'editor-section knowledge-edit-form' });
    editForm.hidden = true;
    root.appendChild(editForm);

    var editNameInput = _input('text', 'name', kb.name, 'Knowledge base name');
    editNameInput.setAttribute('data-testid', 'kb-edit-name-input');
    var editNameGroup = _fieldGroup(editForm, 'Name', 'kb-edit-name', editNameInput);
    var editNameHint = _el('span', {
      className: 'field-hint',
      text: 'Names over 43 characters get a shortened, hashed tool name.'
    });
    editNameHint.setAttribute('data-testid', 'kb-edit-name-hint');
    editNameHint.hidden = Array.from(kb.name || '').length <= 43;
    editNameGroup.appendChild(editNameHint);
    editNameInput.addEventListener('input', function () {
      editNameHint.hidden = Array.from(editNameInput.value).length <= 43;
      // L5-D3 dirty bridge — mirrors mcp-sources'/connectors'
      // onDirtyChange(d) callback, consumed by studio.js's
      // `inEditor`/`_confirmLeaveImpl` gate.
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(true);
    });

    // DD-16's advisory length hint applies to the name field only — the
    // description field carries no length rule (nothing derives from it).
    var editDescInput = _textarea('description', kb.description, 3, 'Optional description');
    editDescInput.setAttribute('data-testid', 'kb-edit-description-input');
    _fieldGroup(editForm, 'Description', 'kb-edit-description', editDescInput);
    editDescInput.addEventListener('input', function () {
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(true);
    });

    // kb-studio-round-trip remediation FIX 3 — see the create-error site above.
    var editErrorEl = _el('div', { className: 'field-error' });
    editErrorEl.setAttribute('data-testid', 'kb-edit-error');
    editForm.appendChild(editErrorEl);

    var editSaveBtn = _btn('btn-filled-primary', 'kb-edit-save-btn', 'Save');
    editForm.appendChild(editSaveBtn);

    editToggleBtn.addEventListener('click', function () {
      var opening = editForm.hidden;
      editForm.hidden = !editForm.hidden;
      if (opening) {
        editNameInput.value = kb.name;
        editDescInput.value = kb.description || '';
        editNameHint.hidden = Array.from(kb.name || '').length <= 43;
        editErrorEl.textContent = '';
        editNameInput.focus();
      } else {
        // Collapsed without saving — the re-populate-on-open above already
        // discards any typed-but-unsubmitted edit, so the dirty mirror
        // must follow (mirrors mcp-sources' Cancel-when-dirty: no dialog
        // gate on a deliberate collapse of an unsaved form).
        if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
      }
    });

    editSaveBtn.addEventListener('click', function () {
      editErrorEl.textContent = '';
      // AC-7: an empty name is refused client-side — no request sent —
      // exactly as the create form's empty-name refusal.
      var newName = editNameInput.value.trim();
      if (!newName) {
        editErrorEl.textContent = 'Name is required.';
        return;
      }
      editSaveBtn.disabled = true;
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName, description: editDescInput.value })
      }).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            throw new Error(_errorMessageFromResponse(body) || 'Save failed');
          });
        }
        return r.json();
      }).then(function (updated) {
        editSaveBtn.disabled = false;
        editForm.hidden = true;
        if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
        // L3-D5 (carried): the inventory re-fetches — a name change moves
        // the derived tool name every attached agent renders (Leg 2's
        // rewrite), and an already-open agent editor is a DIFFERENT
        // Studio section so no cross-surface invalidation is needed; its
        // own edit-mount refresh is what makes the next mount correct.
        if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated);
      }).catch(function (err) {
        editSaveBtn.disabled = false;
        editErrorEl.textContent = err.message || String(err);
      });
    });

    // ── Status (AC-5, AC-9, AC-13, L1-D2) ──────────────────────────────
    var statusSection = _section(root, 'Status');
    var summaryEl = _el('div', { className: 'kb-status-summary' });
    summaryEl.setAttribute('data-testid', 'kb-status-summary');
    statusSection.appendChild(summaryEl);
    var foldersListEl = _el('div', { className: 'kb-folders-list' });
    foldersListEl.setAttribute('data-testid', 'kb-folders-list');
    statusSection.appendChild(foldersListEl);

    // FIX 1: `renderItemsList` (defined below, after the items section
    // exists) reads the CURRENT folder list for the standalone-badge
    // lookup (AC-7/DD-9) rather than the one captured at mount — a
    // status poll tick can bring a newly registered folder before the
    // items list is next rebuilt.
    var currentFolders = (initialStatus && initialStatus.folders) || [];

    function renderStatus(status) {
      summaryEl.textContent = '';
      if (!status) {
        summaryEl.appendChild(_el('div', { className: 'admin-loading', text: 'Loading status…' }));
      } else {
        var counts = status.items || {};
        var countsRow = _el('div', { className: 'kb-status-counts' });
        STATUS_LABELS.forEach(function (label) {
          var chip = _el('span', {
            className: 'chip kb-status-chip',
            text: label + ': ' + (counts[label] || 0)
          });
          chip.setAttribute('data-testid', 'kb-status-count');
          chip.setAttribute('data-status', label);
          countsRow.appendChild(chip);
        });
        summaryEl.appendChild(countsRow);
        var chunkEl = _el('div', { className: 'kb-chunk-count', text: 'Chunks: ' + status.chunks });
        chunkEl.setAttribute('data-testid', 'kb-chunk-count');
        summaryEl.appendChild(chunkEl);
        var indexerEl = _el('div', {
          className: 'kb-indexer-state',
          text: 'Indexer: ' + status.indexer
        });
        indexerEl.setAttribute('data-testid', 'kb-indexer-state');
        summaryEl.appendChild(indexerEl);
      }

      foldersListEl.textContent = '';
      var folders = (status && status.folders) || [];
      currentFolders = folders;
      if (folders.length === 0) {
        foldersListEl.appendChild(_el('div', { className: 'empty-state', text: 'No folders registered.' }));
      } else {
        folders.forEach(function (f) {
          var row = _el('div', { className: 'kb-folder-row' });
          row.setAttribute('data-testid', 'kb-folder-row');
          row.setAttribute('data-folder-id', f.id);
          row.appendChild(_el('span', { className: 'kb-folder-path', text: f.path }));
          row.appendChild(_el('span', { className: 'kb-folder-status', text: 'status: ' + f.status }));
          if (f.indexed_at) {
            row.appendChild(_el('span', {
              className: 'kb-folder-indexed-at',
              text: 'indexed: ' + f.indexed_at
            }));
          }
          if (f.error) {
            var errEl = _el('span', { className: 'field-error kb-folder-error', text: f.error });
            errEl.setAttribute('data-testid', 'kb-folder-status-error');
            row.appendChild(errEl);
          }
          // AC-5: all four watch state words (off/starting/watching/
          // unavailable) are rendered exactly as the API reports them.
          row.appendChild(_el('span', { className: 'kb-folder-watch', text: 'watch: ' + f.watch }));
          if (f.watch_error) {
            var werrEl = _el('span', {
              className: 'field-error kb-folder-watch-error',
              text: f.watch_error
            });
            werrEl.setAttribute('data-testid', 'kb-folder-watch-error');
            row.appendChild(werrEl);
          }
          // ── Remove (AC-1/AC-2/AC-3, L5-D1, M24 F06 L05) — the two-step
          // App.confirmDelete pattern every other destructive control in
          // the codebase uses. The BUTTON label stays terse ("Remove" ->
          // "Confirm remove?", matching every other confirmDelete caller);
          // the consequence sentence lives in a static CAPTION beside the
          // control, rendered before any click rather than only in the
          // armed state.
          var removeCaption = _el('span', {
            className: 'field-hint kb-folder-remove-caption',
            text: 'Removes this folder and every file indexed from it, with their chunks and search entries.'
          });
          removeCaption.setAttribute('data-testid', 'kb-folder-remove-caption');
          row.appendChild(removeCaption);
          var removeBtn = _el('button', { className: 'btn-muted-destructive btn-sm kb-folder-remove-btn' });
          removeBtn.type = 'button';
          removeBtn.setAttribute('data-testid', 'kb-folder-remove-btn');
          var removeTitle = _el('span', { text: 'Remove' });
          removeTitle.setAttribute('data-confirm-title', '');
          removeBtn.appendChild(removeTitle);
          row.appendChild(removeBtn);
          removeBtn.addEventListener('click', function () {
            window.App.confirmDelete(removeBtn, function (el, revertFn) {
              fetch(
                '/api/knowledge-bases/' + encodeURIComponent(kb.id) +
                '/items/' + encodeURIComponent(f.id),
                { method: 'DELETE' }
              ).then(function (r) {
                if (!r.ok) throw new Error('Remove failed');
                // AC-1: an IMMEDIATE refresh on the success path — both
                // the status counts/folder list AND the item list (a
                // folder's children are file items that just vanished
                // with it) — never waiting on the 5-second poll, which
                // would satisfy the wording while leaving up to five
                // seconds of stale display.
                refreshStatusNow();
                refreshItemsListNow();
              }).catch(function () {
                revertFn();
              });
            }, { confirmLabel: 'Confirm remove?' });
          });
          foldersListEl.appendChild(row);
        });
      }
    }
    renderStatus(initialStatus);

    function refreshStatusNow() {
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/status')
        .then(function (r) {
          if (!r.ok) throw new Error('status fetch failed: HTTP ' + r.status);
          return r.json();
        })
        .then(function (status) { renderStatus(status); })
        .catch(function () {
          // L1-D2: a failed refresh leaves the last-rendered state.
        });
    }

    // AC-1 (L5-D1): a companion to refreshStatusNow — re-fetches /items and
    // rebuilds the items list immediately, so a folder removal's cascaded
    // item deletions are visible without waiting on studio.js's poll-driven
    // signature comparison. `renderItemsList` is defined further below in
    // this same closure (function declarations hoist, so this forward
    // reference resolves fine at call time).
    function refreshItemsListNow() {
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items')
        .then(function (r) {
          if (!r.ok) throw new Error('items fetch failed: HTTP ' + r.status);
          return r.json();
        })
        .then(function (freshItems) { renderItemsList(freshItems); })
        .catch(function () {
          // Leave last-rendered state; the operator can retry.
        });
    }

    // ── Register a folder (AC-6, DD-10) ────────────────────────────────
    var registerSection = _section(root, 'Register a folder');
    var folderInput = _input('text', 'path', '', '/path/to/folder');
    folderInput.setAttribute('data-testid', 'kb-folder-path-input');
    _fieldGroup(registerSection, 'Folder path', 'kb-folder-path', folderInput);
    // kb-studio-round-trip remediation FIX 3 (checkpoint 4) — see the
    // create-error site above. This is the site DD-10's data-directory
    // refusal message renders through, so it is the one the finding calls
    // out by name: legible only by accident, at default body-text weight,
    // with the "Register folder" button dragged onto the end of the
    // sentence by the inline span flow.
    var folderErrorEl = _el('div', { className: 'field-error' });
    folderErrorEl.setAttribute('data-testid', 'kb-folder-register-error');
    registerSection.appendChild(folderErrorEl);
    var registerBtn = _btn('btn-outlined-primary', 'kb-register-folder-btn', 'Register folder');
    registerSection.appendChild(registerBtn);

    registerBtn.addEventListener('click', function () {
      folderErrorEl.textContent = '';
      var path = folderInput.value.trim();
      if (!path) {
        folderErrorEl.textContent = 'Folder path is required.';
        return;
      }
      registerBtn.disabled = true;
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'folder', path_or_url: path })
      }).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            // DD-10: render the route's own `detail` message verbatim —
            // 422 non-existent/not-a-directory, 422 filesystem root, 422
            // data-directory overlap, 409 overlapping folder, 422 body
            // validation all carry a prose `detail`.
            throw new Error(_errorMessageFromResponse(body) || 'Folder registration failed');
          });
        }
        return r.json();
      }).then(function () {
        folderInput.value = '';
        registerBtn.disabled = false;
        refreshStatusNow();
        // kb-studio-round-trip remediation FIX 1: registration changes the
        // status counts, so the poll-invalidation path in `studio.js`
        // (comparing `/status`'s counts against what the items list was
        // last rendered against) refreshes the list on its own within one
        // poll interval — no separate callback needed. (Previously called
        // a dead `callbacks.onFolderRegistered()` with no caller anywhere
        // in the repo.)
      }).catch(function (err) {
        registerBtn.disabled = false;
        folderErrorEl.textContent = err.message || String(err);
      });
    });

    // ── Items (AC-7, AC-8, AC-9) ────────────────────────────────────────
    var itemsSection = _section(root, 'Items');
    var itemsListEl = _el('div', { className: 'kb-items-list' });
    itemsListEl.setAttribute('data-testid', 'kb-items-list');
    itemsSection.appendChild(itemsListEl);

    var chunksPanel = _el('div', { className: 'kb-chunks-panel' });
    chunksPanel.setAttribute('data-testid', 'kb-chunks-panel');
    chunksPanel.hidden = true;
    var sourcePanel = _el('div', { className: 'kb-source-panel' });
    sourcePanel.setAttribute('data-testid', 'kb-source-panel');
    sourcePanel.hidden = true;

    // kb-studio-round-trip remediation FIX 4: both panels render at a
    // fixed position below all item rows and, with more than one row,
    // nothing on screen said which item's content is showing. Title each
    // panel with the item's own path on open — smaller change than
    // relocating the panel beside its row, and the same fix for both.
    function _panelTitle(item) {
      var t = _el('div', { className: 'section-title', text: item.path_or_url });
      t.setAttribute('data-testid', 'kb-panel-title');
      return t;
    }

    // ── Overflow menu (AC-9/AC-10, L5-D4, M24 F06 L05) — "View chunks" and
    // "View source" move behind a per-row overflow control. Built minimal
    // and LOCAL to this file (not promoted to components.css — there is
    // exactly one consumer; a second consumer is the trigger for
    // promotion, not the first). At most one menu is open at a time,
    // tracked here so a poll-driven items-list rebuild (or opening a
    // second row's menu) can positively close whichever one is open
    // rather than leaking a detached element + a stale document listener.
    var openItemMenu = null;
    function closeAnyOpenItemMenu() {
      if (openItemMenu) {
        var closer = openItemMenu;
        openItemMenu = null;
        closer({ returnFocus: false });
      }
    }

    // Accessibility (spelled out in L5-D4 because a menu is a keyboard
    // trap if done carelessly, and the seven test_ui_guards.py invariants
    // do not check ARIA/keyboard behaviour at all — AC-10 is the only net
    // for this): the trigger carries aria-haspopup="menu" + aria-expanded,
    // the menu has role="menu" with role="menuitem" children, Escape
    // closes and returns focus to the trigger, arrow keys move between
    // items, and a click outside closes it.
    function buildItemMenu(item) {
      var wrap = _el('div', { className: 'kb-item-menu-wrap' });

      var trigger = _el('button', { className: 'kb-item-menu-trigger', text: '⋯' });
      trigger.type = 'button';
      trigger.setAttribute('data-testid', 'kb-item-menu-btn');
      trigger.setAttribute('aria-haspopup', 'menu');
      trigger.setAttribute('aria-expanded', 'false');
      trigger.setAttribute('aria-label', 'Item actions');
      wrap.appendChild(trigger);

      var menu = _el('div', { className: 'kb-item-menu' });
      menu.setAttribute('role', 'menu');
      menu.setAttribute('data-testid', 'kb-item-menu');
      menu.hidden = true;
      wrap.appendChild(menu);

      var chunksItem = _btn('kb-item-menu-item', 'kb-item-chunks-btn', 'View chunks');
      chunksItem.setAttribute('role', 'menuitem');
      var sourceItem = _btn('kb-item-menu-item', 'kb-item-source-btn', 'View source');
      sourceItem.setAttribute('role', 'menuitem');
      menu.appendChild(chunksItem);
      menu.appendChild(sourceItem);
      var menuItems = [chunksItem, sourceItem];

      function onDocClick(e) {
        if (!wrap.contains(e.target)) closeMenu({ returnFocus: false });
      }
      function onDocKeydown(e) {
        if (e.key === 'Escape') {
          e.preventDefault();
          closeMenu();
        } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          var idx = menuItems.indexOf(document.activeElement);
          var dir = e.key === 'ArrowDown' ? 1 : -1;
          var next = (idx + dir + menuItems.length) % menuItems.length;
          menuItems[next].focus();
        }
      }
      function closeMenu(opts) {
        opts = opts || {};
        menu.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        document.removeEventListener('click', onDocClick, true);
        document.removeEventListener('keydown', onDocKeydown, true);
        if (openItemMenu === closeMenu) openItemMenu = null;
        if (opts.returnFocus !== false) trigger.focus();
      }
      function openMenu() {
        closeAnyOpenItemMenu();
        menu.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        document.addEventListener('click', onDocClick, true);
        document.addEventListener('keydown', onDocKeydown, true);
        openItemMenu = closeMenu;
      }

      trigger.addEventListener('click', function () {
        if (menu.hidden) {
          openMenu();
          menuItems[0].focus();
        } else {
          closeMenu();
        }
      });
      trigger.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowDown' && menu.hidden) {
          e.preventDefault();
          openMenu();
          menuItems[0].focus();
        }
      });
      chunksItem.addEventListener('click', function () {
        closeMenu({ returnFocus: false });
        openChunksPanel(item);
      });
      sourceItem.addEventListener('click', function () {
        closeMenu({ returnFocus: false });
        openSourcePanel(item);
      });

      return wrap;
    }

    // DD-8/AC-8: neither is fetched while rendering the item list — only
    // on the operator's explicit click below.
    function openChunksPanel(item) {
      sourcePanel.hidden = true;
      chunksPanel.hidden = false;
      chunksPanel.textContent = '';
      chunksPanel.appendChild(_panelTitle(item));
      chunksPanel.appendChild(_el('div', { className: 'admin-loading', text: 'Loading chunks…' }));
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) +
        '/items/' + encodeURIComponent(item.id) + '/chunks'
      )
        .then(function (r) {
          if (!r.ok) throw new Error('Failed to load chunks: HTTP ' + r.status);
          return r.json();
        })
        .then(function (chunks) {
          chunksPanel.textContent = '';
          chunksPanel.appendChild(_panelTitle(item));
          if (chunks.length === 0) {
            chunksPanel.appendChild(_el('div', { className: 'empty-state', text: 'No chunks yet.' }));
            return;
          }
          // AC-8: render in seq order (the route already pages in seq
          // order; sort defensively so the UI's own contract doesn't
          // depend on that staying true).
          chunks.sort(function (a, b) { return a.seq - b.seq; });
          chunks.forEach(function (c) {
            var row = _el('div', { className: 'kb-chunk-row' });
            row.setAttribute('data-testid', 'kb-chunk-row');
            row.appendChild(_el('span', { className: 'kb-chunk-seq', text: '#' + c.seq }));
            row.appendChild(_el('span', { className: 'kb-chunk-text', text: c.text }));
            chunksPanel.appendChild(row);
          });
        })
        .catch(function (err) {
          chunksPanel.textContent = '';
          chunksPanel.appendChild(_panelTitle(item));
          chunksPanel.appendChild(_el('div', { className: 'field-error', text: err.message || String(err) }));
        });
    }

    function openSourcePanel(item) {
      chunksPanel.hidden = true;
      sourcePanel.hidden = false;
      sourcePanel.textContent = '';
      sourcePanel.appendChild(_panelTitle(item));
      sourcePanel.appendChild(_el('div', { className: 'admin-loading', text: 'Loading source…' }));
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) +
        '/items/' + encodeURIComponent(item.id) + '/source'
      )
        .then(function (r) {
          if (!r.ok) {
            return r.text().then(function (body) {
              throw new Error(_errorMessageFromResponse(body) || 'Failed to load source');
            });
          }
          return r.json();
        })
        .then(function (result) {
          sourcePanel.textContent = '';
          sourcePanel.appendChild(_panelTitle(item));
          var pre = _el('pre', { className: 'kb-source-text', text: result.text });
          pre.setAttribute('data-testid', 'kb-source-text');
          sourcePanel.appendChild(pre);
        })
        .catch(function (err) {
          sourcePanel.textContent = '';
          sourcePanel.appendChild(_panelTitle(item));
          sourcePanel.appendChild(_el('div', { className: 'field-error', text: err.message || String(err) }));
        });
    }

    // kb-studio-round-trip remediation FIX 1: extracted so `studio.js` can
    // call it again — via the returned `updateItems` handle below — when
    // the status poll observes the counts have changed, without rebuilding
    // the rest of the detail view. Only ever touches `itemsListEl`'s own
    // children; `chunksPanel`/`sourcePanel` are separate siblings appended
    // to `itemsSection` once, below, so an open panel is untouched by a
    // list rebuild.
    function renderItemsList(nextItems) {
      // Edge case (L5-D4): the overflow menu open when the list re-renders
      // (the poll's signature-based invalidation fires) must close rather
      // than leak a detached element + a stale document-level listener.
      closeAnyOpenItemMenu();
      itemsListEl.textContent = '';
      // Edge case: "the status route excludes folders from items counts by
      // design, so a registered folder must never be rendered as a
      // document" — GET /items returns folder-typed rows too (DD-9's
      // parent_id read path needs them to exist in `items`), but only
      // `type === 'file'` items become a document row here.
      var nextFileItems = nextItems.filter(function (it) { return it.type === 'file'; });

      if (nextFileItems.length === 0) {
        itemsListEl.appendChild(_el('div', { className: 'empty-state', text: 'No items yet.' }));
        return;
      }
      nextFileItems.forEach(function (item) {
        var row = _el('div', { className: 'kb-item-row' });
        row.setAttribute('data-testid', 'kb-item-row');
        row.setAttribute('data-item-id', item.id);
        row.appendChild(_el('span', { className: 'kb-item-path', text: item.path_or_url }));
        var statusEl = _el('span', { className: 'kb-item-status', text: item.status });
        statusEl.setAttribute('data-testid', 'kb-item-status');
        row.appendChild(statusEl);
        if (item.status === 'failed' && item.error) {
          var itemErrEl = _el('span', { className: 'field-error kb-item-error', text: item.error });
          itemErrEl.setAttribute('data-testid', 'kb-item-error');
          row.appendChild(itemErrEl);
        }
        // DD-9: a standalone file whose path lies inside a registered
        // folder is badged rather than silently shown as a look-alike
        // duplicate. Reads `currentFolders` — the most recently rendered
        // status's folder list — rather than the mount-time snapshot, so a
        // folder registered after mount is reflected in the next rebuild.
        var standaloneFolder = _containingFolder(item, currentFolders);
        if (standaloneFolder) {
          var badge = _el('span', {
            className: 'chip kb-item-standalone-badge',
            text: 'standalone (in ' + standaloneFolder.path + ')'
          });
          badge.setAttribute('data-testid', 'kb-item-standalone-badge');
          row.appendChild(badge);
        }
        // AC-9/L5-D4: "View chunks"/"View source" live behind a per-row
        // overflow control rather than crowding the row as two buttons.
        row.appendChild(buildItemMenu(item));
        itemsListEl.appendChild(row);
      });
    }
    renderItemsList(items);
    itemsSection.appendChild(chunksPanel);
    itemsSection.appendChild(sourcePanel);

    // ── Re-index (AC-9) ──────────────────────────────────────────────
    var reindexRow = _el('div', { className: 'kb-reindex-row' });
    var reindexChangedBtn = _btn('btn-outlined-primary', 'kb-reindex-changed-btn', 'Re-index changed');
    var reindexAllBtn = _btn('btn-outlined-primary', 'kb-reindex-all-btn', 'Re-index all');
    reindexRow.appendChild(reindexChangedBtn);
    reindexRow.appendChild(reindexAllBtn);
    itemsSection.appendChild(reindexRow);

    function triggerReindex(scope) {
      reindexChangedBtn.disabled = true;
      reindexAllBtn.disabled = true;
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/reindex?scope=' + scope,
        { method: 'POST' }
      )
        .then(function (r) {
          if (!r.ok) throw new Error('Re-index request failed: HTTP ' + r.status);
          return r.json();
        })
        // AC-9: the reindex response carries no indexer state, so issue
        // one immediate status fetch rather than waiting up to a full
        // poll interval.
        .then(function () { refreshStatusNow(); })
        .catch(function () {
          // Leave last-rendered state; the operator can retry.
        })
        .then(function () {
          reindexChangedBtn.disabled = false;
          reindexAllBtn.disabled = false;
        });
    }
    reindexChangedBtn.addEventListener('click', function () { triggerReindex('changed'); });
    reindexAllBtn.addEventListener('click', function () { triggerReindex('all'); });

    // ── Search (AC-10, AC-12, DD-6) ─────────────────────────────────────
    var searchSection = _section(root, 'Search');
    var searchInput = _input('text', 'q', '', 'Search this knowledge base');
    searchInput.setAttribute('data-testid', 'kb-search-input');
    _fieldGroup(searchSection, 'Search', 'kb-search-query', searchInput);
    var searchBtn = _btn('btn-outlined-primary', 'kb-search-btn', 'Search');
    searchSection.appendChild(searchBtn);
    // kb-studio-round-trip remediation FIX 3 (continued — the initial pass
    // missed these two of seven `.editor-error` sites): same unscoped-CSS
    // problem as the FIX 3 comment above. `field-error` keeps the
    // `kb-search-degraded` class, which the behavior spec and tests key on.
    var degradedEl = _el('div', { className: 'field-error kb-search-degraded' });
    degradedEl.setAttribute('data-testid', 'kb-search-degraded');
    degradedEl.hidden = true;
    searchSection.appendChild(degradedEl);
    var resultsEl = _el('div', { className: 'kb-search-results' });
    resultsEl.setAttribute('data-testid', 'kb-search-results');
    searchSection.appendChild(resultsEl);

    function runSearch() {
      var q = searchInput.value;
      resultsEl.textContent = '';
      degradedEl.hidden = true;
      if (!q.trim()) return;
      resultsEl.appendChild(_el('div', { className: 'admin-loading', text: 'Searching…' }));
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) +
        '/search?q=' + encodeURIComponent(q) + '&limit=10'
      )
        .then(function (r) {
          if (!r.ok) throw new Error('Search failed: HTTP ' + r.status);
          return r.json();
        })
        .then(function (result) {
          resultsEl.textContent = '';
          // AC-12: the degrade line and the indexer word come from the
          // SAME search response — never the polled status.
          if (result.degraded) {
            degradedEl.hidden = false;
            degradedEl.textContent = 'Degraded: ' + result.degraded + ' (indexer: ' + result.indexer + ')';
          }
          if (result.hits.length === 0) {
            resultsEl.appendChild(_el('div', { className: 'empty-state', text: 'No results.' }));
            return;
          }
          result.hits.forEach(function (hit) {
            var row = _el('div', { className: 'kb-search-hit' });
            row.setAttribute('data-testid', 'kb-search-hit');
            row.appendChild(_el('span', { className: 'kb-search-hit-path', text: hit.path }));
            row.appendChild(_el('span', {
              className: 'kb-search-hit-score',
              text: 'score: ' + hit.score.toFixed(3)
            }));
            row.appendChild(_el('span', { className: 'kb-search-hit-text', text: hit.text }));
            resultsEl.appendChild(row);
          });
        })
        .catch(function (err) {
          resultsEl.textContent = '';
          resultsEl.appendChild(_el('div', { className: 'field-error', text: err.message || String(err) }));
        });
    }
    searchBtn.addEventListener('click', runSearch);
    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); runSearch(); }
    });

    // ── Danger Zone (AC-3) — the project's existing two-step confirm
    // affordance (App.confirmDelete), same pattern as connector-editor.js.
    var danger = _el('div', { className: 'editor-section danger-zone' });
    danger.appendChild(_el('div', { className: 'section-title danger-zone-title', text: 'Danger Zone' }));
    var deleteBtn = _el('button', { className: 'btn-muted-destructive delete-btn' });
    deleteBtn.type = 'button';
    deleteBtn.setAttribute('data-testid', 'delete-knowledge-base-btn');
    var deleteTitle = _el('span', { text: 'Delete Knowledge Base' });
    deleteTitle.setAttribute('data-confirm-title', '');
    deleteBtn.appendChild(deleteTitle);
    danger.appendChild(deleteBtn);
    root.appendChild(danger);

    deleteBtn.addEventListener('click', function () {
      window.App.confirmDelete(deleteBtn, function (el, revertFn) {
        fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id), { method: 'DELETE' })
          .then(function (r) {
            if (!r.ok) throw new Error('Delete failed');
            if (callbacks.onDeleteSuccess) callbacks.onDeleteSuccess();
          })
          .catch(function () {
            revertFn();
          });
      });
    });

    return { updateStatus: renderStatus, updateItems: renderItemsList };
  }

  window.App.studio.renderKnowledgeGrid = renderKnowledgeGrid;
  window.App.studio.renderKnowledgeDetail = renderKnowledgeDetail;
})();
