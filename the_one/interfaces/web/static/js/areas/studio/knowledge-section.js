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
// static single-string-literal even if it were scanned. Icons follow the
// same discipline: `window.App.icon()` returns raw SVG HTML meant for an
// `innerHTML` assignment, which this file never performs. Where a real
// icon is required (the two destructive controls), it goes in through
// `_appendIcon` below — the DOMParser route that
// `tests/_ui_guard_helpers.py`'s own allowance note names as the
// sanctioned no-inner-HTML path, and that `markdown.js::injectIcon`
// already uses for exactly this reason.
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
// protecting). `updateItems` only ever touches the item rows nested
// inside each folder panel's body plus the trailing "Other items" panel;
// `chunksPanel`/`sourcePanel` are separate siblings under the Folders
// section and are untouched by a list rebuild, so an open panel survives
// it.
//
// Mission 24 Flight 6 Leg 6 (HAT — restyle to the MCP server editor's
// shape, 2026-09-19): four leg design decisions —
//   L6-D1: Name + Description become ALWAYS-LIVE fields in the header
//     region (no edit-button toggle); Save/Cancel sit beside Back in the
//     header, disabled until the form is dirty, mirroring
//     `mcp-server-editor.js`. THE GENUINE HAZARD this introduces: the
//     5-second status poll must never re-render these fields mid-
//     keystroke. Structural guarantee: the name/description inputs live
//     in `fieldsSection`, a DOM subtree `renderStatusSummary`/
//     `renderFolders`/`renderAllItems` (the only functions the poll
//     calls, via the returned `updateStatus`/`updateItems` handles) never
//     touch. Those functions only ever write into `summaryEl`,
//     `foldersListEl`'s panels, and folder/other-items file lists.
//   L6-D2: folders become native `<details>` panels (`buildFolderPanel`)
//     containing their own files — items are grouped by `parent_id`
//     against the CURRENT folder set (`renderAllItems`); anything whose
//     `parent_id` is unset OR points at a folder that no longer exists
//     lands in a trailing "Other items" `<details>` panel
//     (`renderOtherItems`), never nested under a folder its path merely
//     happens to contain (DD-9's standalone badge is exactly for that
//     case, and only applies inside "Other items").
//   L6-D3 (as AMENDED by the Flight Director after first
//     implementation): the folders control reads "Add folder", and Leg
//     5's labelled Remove-then-Confirm control becomes a trash-glyph
//     icon button in the folder's summary line. The Custom Headers row
//     in `mcp-server-editor.js` supplies that icon's VISUAL form only —
//     it does NOT supply its bare, unconfirmed click. A Custom Headers
//     row is a client-side form row: it is added and removed purely in
//     the DOM and nothing is persisted until the operator presses Save,
//     so its bare click costs nothing and is undone by not saving.
//     Removing a registered folder is the opposite — an immediate,
//     irreversible, server-side cascading DELETE of the folder, its file
//     items, and their chunks. The two-step confirm therefore SURVIVES
//     the restyle, rendered through the canonical `App.confirmDelete`
//     (`static/js/confirm.js`) with the folder's `<summary>` as the
//     state element and the folder-path span as its
//     `[data-confirm-title]` target — the same helper and the same shape
//     as this page's own Danger Zone delete and as chat.js's session
//     delete. (The part of the Custom Headers analogy that DOES hold: a
//     form-control descendant of `<summary>` does not toggle the
//     `<details>`, per HTML spec, so the icon never fights the expand/
//     collapse gesture.) The armed state is only safe because
//     `renderFolders`' keyed reconciliation MOVES an already-attached
//     panel rather than re-creating it, so a 5-second poll tick landing
//     inside the helper's 3-second revert window cannot destroy an armed
//     row; `updateFolderMeta` must correspondingly keep its hands off
//     the path span. The two behaviours are coupled; neither is
//     optional. The consequence sentence the old two-step confirm
//     carried survives INDEPENDENTLY of the confirm, as persistent
//     section-level helper text under "Folders"
//     (`kb-folders-cascade-hint`) rather than a per-click caption, per
//     the leg's explicit rationale.
//   L6-D4: the per-row overflow menu (`buildItemMenu`, unchanged) now
//     lives on file rows nested inside folder panels / the "Other items"
//     panel. The existing single-open tracker (`openItemMenu` /
//     `closeAnyOpenItemMenu`) is extended to close on a `<details>`
//     panel's own `toggle`-to-closed event, so a panel collapsing while
//     its menu is open does not leak the same way a list rebuild
//     already didn't.
//
// Poll-vs-mutation split (Leg 6): `renderFolders(folders)` reconciles
// `<details>` panel IDENTITY (create/update/remove, keyed by folder id)
// plus each panel's summary/meta content (path/status/watch/errors) — it
// is safe to call on every 5-second tick because it NEVER recreates an
// existing panel's DOM node, so an operator-expanded panel stays expanded
// across ticks, and it NEVER touches a panel's file-row content, so an
// open per-item menu is untouched by a metadata-only tick.
// `renderAllItems(items)` is the items-list counterpart — it only
// rebuilds file rows (closing any open item menu first, mirroring the
// pre-restyle discipline) and is called at mount, by `updateItems` on an
// actual items-signature change, and by the immediate
// `refreshItemsListNow()` after a folder mutation. The two never call
// each other, so a folder-metadata-only tick can never trigger an
// items-list rebuild, and vice versa.
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

  // Appends a TRUSTED icons.js SVG to `parent` without an HTML-string
  // sink. `window.App.icon(name)` returns SVG *markup*, which normally
  // wants `innerHTML`; Mission 17 Flight 1's dynamic-sink freeze
  // (tests/test_ui_guards.py) forbids a new one, and this file has no
  // baseline entry to spend. `markdown.js::injectIcon` solves the same
  // problem the same way, and `tests/_ui_guard_helpers.py`'s allowance
  // note calls that route "the sanctioned no-inner-HTML path for the
  // copy-button glyph". Only literal icon names are ever passed here —
  // no untrusted data reaches the parser.
  function _appendIcon(parent, name) {
    var svgString = (window.App && window.App.icon) ? window.App.icon(name) : '';
    if (!svgString) return;
    var doc = new DOMParser().parseFromString(svgString, 'image/svg+xml');
    var svg = doc && doc.documentElement;
    if (svg && svg.nodeName.toLowerCase() === 'svg') parent.appendChild(svg);
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

  // M24 F06 L05 (L5-D2): the create form and the detail view's fields
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

  // AC-9 (Leg 6)/DD-9: separator-aware containment — a bare
  // `itemPath.startsWith(folderPath)` is wrong at directory boundaries
  // (folder `/data/foo` would falsely claim item `/data/foobar/x.txt`).
  // `sep` is read off the folder path's own separator (the server stores
  // `str(canonical)` in OS-native form with no guaranteed trailing
  // separator). Only ever consulted for items rendered in the trailing
  // "Other items" panel — a truly-parented item (its own `parent_id`
  // matches a folder id) never needs the guess.
  function _containingFolder(item, folders) {
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
  //
  // Section order (AC-6, Leg 6): header/fields → Status → Folders →
  // Search → Danger Zone.

  function renderKnowledgeDetail(container, kb, state, callbacks) {
    callbacks = callbacks || {};
    state = state || {};
    var items = state.items || [];
    var initialStatus = state.status || null;

    container.textContent = '';

    var root = _el('div', { className: 'knowledge-inventory knowledge-detail' });
    root.setAttribute('data-testid', 'studio-knowledge-inventory');
    container.appendChild(root);

    // ── Header (AC-1, L6-D1) — static title/subtitle (last-saved values;
    // refreshed only on a successful Save's remount) + Back/Cancel/Save,
    // mirroring `mcp-server-editor.js`'s header exactly. No edit button.
    var header = _el('div', { className: 'editor-header' });
    var headerText = _el('div', { className: 'editor-header-text' });
    headerText.appendChild(_el('h1', { className: 'editor-title', text: kb.name }));
    headerText.appendChild(_el('p', { className: 'editor-subtitle', text: kb.description || '' }));
    header.appendChild(headerText);

    var actions = _el('div', { className: 'form-actions' });
    var backBtn = _btn('btn-outlined-primary back-btn', 'back-knowledge-btn', '← Back');
    backBtn.setAttribute('aria-label', 'Back to knowledge bases');
    actions.appendChild(backBtn);
    var cancelBtn = _btn('btn-outlined-primary cancel-btn', 'cancel-knowledge-btn', 'Cancel');
    cancelBtn.disabled = true;
    actions.appendChild(cancelBtn);
    var saveBtn = _btn('btn-filled-primary save-btn', 'save-knowledge-btn', 'Save');
    saveBtn.disabled = true;
    actions.appendChild(saveBtn);
    var headerErrorEl = _el('span', { className: 'editor-error' });
    actions.appendChild(headerErrorEl);
    header.appendChild(actions);
    root.appendChild(header);

    // AC-5/L5-D3 (carried): the dirty GATE for this click lives in
    // studio.js's `onBack` (mirrors mcp-sources' own onBack, which checks
    // the orchestrator's `dirty` closure var and shows App.confirmDialog
    // itself before proceeding) — this module only ever requests the
    // navigation, never decides to discard unsaved edits on its own.
    backBtn.addEventListener('click', function () {
      if (callbacks.onBack) callbacks.onBack();
    });

    // ── Fields (AC-2, L6-D1) — Name + Description, ALWAYS live, no
    // wrapping edit form. Reuses the create form's 43-code-point advisory
    // hint and empty-name refusal.
    var fieldsSection = _el('div', { className: 'editor-section' });
    root.appendChild(fieldsSection);

    var nameInput = _input('text', 'name', kb.name, 'Knowledge base name');
    nameInput.setAttribute('data-testid', 'kb-name-input');
    var nameGroup = _fieldGroup(fieldsSection, 'Name', 'kb-name', nameInput);
    var nameHint = _el('span', {
      className: 'field-hint',
      text: 'Names over 43 characters get a shortened, hashed tool name.'
    });
    nameHint.setAttribute('data-testid', 'kb-name-hint');
    nameHint.hidden = Array.from(kb.name || '').length <= 43;
    nameGroup.appendChild(nameHint);

    var descInput = _textarea('description', kb.description, 3, 'Optional description');
    descInput.setAttribute('data-testid', 'kb-description-input');
    _fieldGroup(fieldsSection, 'Description', 'kb-description', descInput);

    // AC-3/AC-4 — dirty tracking: Save/Cancel disabled until the fields
    // differ from the loaded baseline; Cancel reverts + clears dirty.
    function fieldsSnapshot() {
      return JSON.stringify({ name: nameInput.value, description: descInput.value });
    }
    var baselineSnapshot = fieldsSnapshot();
    function checkDirty() {
      var dirty = (fieldsSnapshot() !== baselineSnapshot);
      saveBtn.disabled = !dirty;
      cancelBtn.disabled = !dirty;
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(dirty);
      return dirty;
    }
    function recapture() {
      baselineSnapshot = fieldsSnapshot();
      saveBtn.disabled = true;
      cancelBtn.disabled = true;
      if (callbacks.onDirtyChange) callbacks.onDirtyChange(false);
    }

    nameInput.addEventListener('input', function () {
      nameHint.hidden = Array.from(nameInput.value).length <= 43;
      headerErrorEl.textContent = '';
      checkDirty();
    });
    descInput.addEventListener('input', function () {
      headerErrorEl.textContent = '';
      checkDirty();
    });

    cancelBtn.addEventListener('click', function () {
      nameInput.value = kb.name;
      descInput.value = kb.description || '';
      nameHint.hidden = Array.from(kb.name || '').length <= 43;
      headerErrorEl.textContent = '';
      recapture();
    });

    saveBtn.addEventListener('click', function () {
      headerErrorEl.textContent = '';
      // AC-7 (Leg 6, carried from L5-D2): an empty name is refused
      // client-side — no request sent — exactly as the create form's
      // empty-name refusal.
      var newName = nameInput.value.trim();
      if (!newName) {
        headerErrorEl.textContent = 'Name is required.';
        return;
      }
      saveBtn.disabled = true;
      cancelBtn.disabled = true;
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName, description: descInput.value })
      }).then(function (r) {
        if (!r.ok) {
          return r.text().then(function (body) {
            throw new Error(_errorMessageFromResponse(body) || 'Save failed');
          });
        }
        return r.json();
      }).then(function (updated) {
        // L3-D5 (carried): the caller re-mounts the whole detail view from
        // the saved object — refreshes the header title/subtitle and
        // re-fetches status/items — and updates the grid's section-local
        // cache so navigating back shows the new name without a second
        // fetch. The remount naturally re-disables Save/Cancel (AC-3).
        if (callbacks.onSaveSuccess) callbacks.onSaveSuccess(updated);
      }).catch(function (err) {
        checkDirty(); // restore button state to match actual dirtiness
        headerErrorEl.textContent = err.message || String(err);
      });
    });

    // ── Folders (AC-6/AC-7/AC-8/AC-9/AC-10, L6-D2/L6-D3) ────────────────
    //
    // HAT polish pass (2026-09-19): Folders is now created BEFORE Status,
    // so it renders ABOVE it. `_section` appends in call order, so the
    // Status block that used to sit here has moved verbatim to just after
    // this section's last append (search for "── Status"), taking the
    // re-index row with it. The operator read the re-index pair as
    // folder-scoped while it sat among the per-folder panels; it is a
    // whole-knowledge-base operation, so it belongs beside the
    // whole-knowledge-base status counts.
    var foldersSection = _section(root, 'Folders');

    // L6-D3: the cascade warning that used to live as a per-row caption
    // beside the two-step Remove control now lives here — section-level,
    // persistent, present before any click.
    var cascadeHint = _el('p', {
      className: 'field-hint',
      text: 'Removing a folder removes every file indexed from it, along with their chunks and search entries.'
    });
    cascadeHint.setAttribute('data-testid', 'kb-folders-cascade-hint');
    foldersSection.appendChild(cascadeHint);

    var folderInput = _input('text', 'path', '', '/path/to/folder');
    folderInput.setAttribute('data-testid', 'kb-folder-path-input');
    _fieldGroup(foldersSection, 'Folder path', 'kb-folder-path', folderInput);
    // kb-studio-round-trip remediation FIX 3 (continued) — see the
    // create-error site above. This is the site DD-10's data-directory
    // refusal message renders through.
    var folderErrorEl = _el('div', { className: 'field-error' });
    folderErrorEl.setAttribute('data-testid', 'kb-folder-add-error');
    foldersSection.appendChild(folderErrorEl);
    // AC-7: "Add folder" (was "Register folder").
    var addFolderBtn = _btn('btn-outlined-primary', 'kb-add-folder-btn', 'Add folder');
    foldersSection.appendChild(addFolderBtn);

    var foldersListEl = _el('div', { className: 'kb-folders-list' });
    foldersListEl.setAttribute('data-testid', 'kb-folders-list');
    foldersSection.appendChild(foldersListEl);

    var foldersEmptyEl = _el('div', { className: 'empty-state', text: 'No folders registered.' });
    foldersListEl.appendChild(foldersEmptyEl);

    // Reconciliation state — keyed by folder id so an operator-expanded
    // `<details>` panel is never torn down by a routine poll tick (see
    // the module docstring's "Poll-vs-mutation split").
    var folderPanels = {}; // folder id -> { detailsEl, statusChip, watchChip, metaEl, filesEl }
    var currentFolders = (initialStatus && initialStatus.folders) || [];
    var otherItemsPanel = null; // built lazily, only while standalone items exist

    // ── Overflow menu (AC-13, L5-D4 carried / L6-D4) — "View chunks" and
    // "View source" move behind a per-row overflow control on file rows
    // nested inside a folder panel or the "Other items" panel. At most one
    // menu is open at a time, tracked here so a poll-driven items rebuild
    // OR a `<details>` panel collapsing while its menu is open can
    // positively close whichever one is open rather than leaking a
    // detached element + a stale document listener.
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
    // do not check ARIA/keyboard behaviour at all — AC-10/AC-13 is the
    // only net for this): the trigger carries aria-haspopup="menu" +
    // aria-expanded, the menu has role="menu" with role="menuitem"
    // children, Escape closes and returns focus to the trigger, arrow
    // keys move between items, and a click outside closes it.
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

    // kb-studio-round-trip remediation FIX 4: both panels render at a
    // fixed position and, with more than one row, nothing on screen said
    // which item's content is showing. Title each panel with the item's
    // own path on open.
    function _panelTitle(item) {
      var t = _el('div', { className: 'section-title', text: item.path_or_url });
      t.setAttribute('data-testid', 'kb-panel-title');
      return t;
    }

    var chunksPanel = _el('div', { className: 'kb-chunks-panel' });
    chunksPanel.setAttribute('data-testid', 'kb-chunks-panel');
    chunksPanel.hidden = true;
    var sourcePanel = _el('div', { className: 'kb-source-panel' });
    sourcePanel.setAttribute('data-testid', 'kb-source-panel');
    sourcePanel.hidden = true;

    // DD-8/AC-13: neither is fetched while rendering the item list — only
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
          // AC-13: render in seq order (the route already pages in seq
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

    // Shared row builder for a file item, used both inside a folder
    // panel's body and inside the trailing "Other items" panel.
    // `opts.standalone` gates the DD-9 badge lookup — only meaningful for
    // items with no real parent, which is exactly the "Other items" set.
    function buildFileItemRow(item, opts) {
      opts = opts || {};
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
      if (opts.standalone) {
        // DD-9: a standalone file whose path lies inside a registered
        // folder is badged rather than silently shown as a look-alike
        // duplicate.
        var standaloneFolder = _containingFolder(item, currentFolders);
        if (standaloneFolder) {
          var badge = _el('span', {
            className: 'chip kb-item-standalone-badge',
            text: 'standalone (in ' + standaloneFolder.path + ')'
          });
          badge.setAttribute('data-testid', 'kb-item-standalone-badge');
          row.appendChild(badge);
        }
      }
      row.appendChild(buildItemMenu(item));
      return row;
    }

    // ── Folder panel construction/reconciliation (L6-D2/L6-D3/L6-D4) ────

    // `revertFn` comes from App.confirmDelete's commit callback: on the
    // transport-failure path the armed row must roll back (path text
    // restored, `.confirm-delete` cleared) rather than being left
    // stranded reading "Confirm delete?" over a folder that still exists.
    function deleteFolder(f, deleteBtn, revertFn) {
      deleteBtn.disabled = true;
      fetch(
        '/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items/' + encodeURIComponent(f.id),
        { method: 'DELETE' }
      ).then(function (r) {
        if (!r.ok) throw new Error('Remove failed');
        // AC-11: an IMMEDIATE refresh on the success path — both the
        // status/folders AND the item list (a folder's children are file
        // items that just vanished with it) — never waiting on the
        // 5-second poll.
        refreshStatusNow();
        refreshItemsListNow();
      }).catch(function (err) {
        deleteBtn.disabled = false;
        if (typeof revertFn === 'function') revertFn();
        window.App.showFlash(container, 'Error: ' + (err.message || err), true);
      });
    }

    function buildFolderPanel(f) {
      var details = document.createElement('details');
      details.className = 'mcp-tool-item';
      details.setAttribute('data-testid', 'kb-folder-panel');
      details.setAttribute('data-folder-id', f.id);

      var summary = document.createElement('summary');
      // `kb-folder-summary` exists purely so the armed-confirm CSS can be
      // scoped to THIS consumer of the borrowed `.mcp-tool-summary`
      // vocabulary (same precedent as `kb-folder-delete-btn` beside
      // `kv-remove-row-btn` below) — it carries no layout of its own.
      summary.className = 'mcp-tool-summary kb-folder-summary';

      var pathSpan = _el('span', { className: 'mcp-tool-summary-text kb-folder-path', text: f.path });
      // App.confirmDelete swaps THIS element's text to "Confirm delete?"
      // while armed, and restores it on revert. Nothing else may write to
      // it — see updateFolderMeta's note.
      pathSpan.setAttribute('data-confirm-title', '');
      summary.appendChild(pathSpan);

      var statusChip = _el('span', { className: 'chip kb-folder-status', text: 'status: ' + f.status });
      summary.appendChild(statusChip);

      var watchChip = _el('span', { className: 'chip kb-folder-watch', text: 'watch: ' + f.watch });
      summary.appendChild(watchChip);

      // L6-D3 (amended): a form-control descendant of `<summary>` does
      // not toggle the parent `<details>` (per HTML spec — see the
      // tools-tab.js precedent this mirrors), so this click never fights
      // expand/collapse. The icon's VISUAL form is the Custom Headers
      // row's in mcp-server-editor.js; its BEHAVIOUR is not. That row
      // persists nothing until Save, so a bare click there is free;
      // removing a folder is an immediate, irreversible, server-side
      // cascading DELETE (the folder, its file items, their chunks), so
      // it keeps Leg 5's two-step confirm — the canonical
      // App.confirmDelete, armed on the `<summary>` with the path span as
      // `[data-confirm-title]`, exactly as the Danger Zone delete below.
      // The persistent `cascadeHint` above states the consequence before
      // any click; it is additional to the confirm, not a substitute.
      var deleteBtn = _el('button', { className: 'kv-remove-row-btn kb-folder-delete-btn' });
      deleteBtn.type = 'button';
      deleteBtn.setAttribute('data-testid', 'kb-folder-delete-btn');
      // The armed state's visible signal is the PATH SPAN's text swap —
      // a different element from this button, and not inside its
      // accessible name. Rather than mutate this label on arm (which the
      // helper's internal 3-second auto-revert gives us no hook to undo,
      // so it would go stale and lie), the two-step is stated once,
      // statically, in the name a screen reader announces on focus.
      deleteBtn.setAttribute(
        'aria-label', 'Delete folder ' + f.path + ' (press twice to confirm)'
      );
      deleteBtn.title = 'Delete folder';
      // HAT polish pass: a real 16px trash icon (the size
      // `.kv-remove-row-btn svg` already sets for the Custom Headers row
      // this borrows from) replaces the text glyph, which rendered at the
      // summary line's 12px and read as too small. `_appendIcon` keeps the
      // no-inner-HTML discipline — see its comment.
      _appendIcon(deleteBtn, 'trash');
      deleteBtn.addEventListener('click', function () {
        window.App.confirmDelete(summary, function (el, revertFn) {
          deleteFolder(f, deleteBtn, revertFn);
        });
      });
      summary.appendChild(deleteBtn);

      var chevron = _el('span', { className: 'mcp-tool-chevron', text: '▸' });
      summary.appendChild(chevron);

      details.appendChild(summary);

      var body = _el('div', { className: 'mcp-tool-body' });
      var metaEl = _el('div', { className: 'kb-folder-meta' });
      body.appendChild(metaEl);
      var filesEl = _el('div', { className: 'kb-folder-files' });
      filesEl.appendChild(_el('div', {
        className: 'empty-state',
        text: 'No files indexed from this folder yet.'
      }));
      body.appendChild(filesEl);
      details.appendChild(body);

      // L6-D4: an open item menu inside this panel's body must not leak
      // when the panel itself collapses.
      details.addEventListener('toggle', function () {
        if (!details.open) closeAnyOpenItemMenu();
      });

      return { detailsEl: details, statusChip: statusChip, watchChip: watchChip, metaEl: metaEl, filesEl: filesEl };
    }

    // Runs on EVERY poll tick. It must never write to the folder-path
    // span: while a delete confirm is armed, that span holds
    // App.confirmDelete's "Confirm delete?" placeholder, and the helper's
    // revert restores from a value captured at arm time — a tick that
    // rewrote the span would either wipe the armed signal or (worse) get
    // its own text captured as the "original" and written back on revert.
    // Chips and the meta body are separate nodes and are safe to rewrite.
    // This is the second half of L6-D3's coupling, the first being
    // renderFolders' move-don't-recreate reconciliation.
    function updateFolderMeta(panel, f) {
      panel.statusChip.textContent = 'status: ' + f.status;
      panel.watchChip.textContent = 'watch: ' + f.watch;
      panel.metaEl.textContent = '';
      if (f.indexed_at) {
        panel.metaEl.appendChild(_el('div', { className: 'kb-folder-indexed-at', text: 'Indexed: ' + f.indexed_at }));
      }
      // AC-5 (carried, M24 F06 L01): the folder's own walk `error`.
      if (f.error) {
        var errEl = _el('div', { className: 'field-error kb-folder-error', text: f.error });
        errEl.setAttribute('data-testid', 'kb-folder-status-error');
        panel.metaEl.appendChild(errEl);
      }
      if (f.watch_error) {
        var werrEl = _el('div', { className: 'field-error kb-folder-watch-error', text: f.watch_error });
        werrEl.setAttribute('data-testid', 'kb-folder-watch-error');
        panel.metaEl.appendChild(werrEl);
      }
    }

    // Reconciles `<details>` panel identity ONLY — never touches a
    // panel's file-row content (that's `renderAllItems`'s job). Safe to
    // call on every poll tick: an existing panel is never recreated, so
    // its `open` state and any nested (non-menu) DOM survive.
    function renderFolders(folders) {
      currentFolders = folders;
      foldersEmptyEl.hidden = folders.length > 0;

      var seenIds = {};
      folders.forEach(function (f) {
        seenIds[f.id] = true;
        var panel = folderPanels[f.id];
        if (!panel) {
          panel = buildFolderPanel(f);
          folderPanels[f.id] = panel;
        }
        // appendChild on an already-attached node MOVES it (preserving
        // `open` state) rather than re-creating it — this both inserts
        // brand-new panels and keeps existing ones in the folders' order.
        foldersListEl.appendChild(panel.detailsEl);
        updateFolderMeta(panel, f);
      });

      Object.keys(folderPanels).forEach(function (id) {
        if (!seenIds[id]) {
          var stale = folderPanels[id];
          if (stale.detailsEl.parentNode) stale.detailsEl.parentNode.removeChild(stale.detailsEl);
          delete folderPanels[id];
        }
      });
    }
    renderFolders(currentFolders);

    // ── "Other items" trailing panel (L6-D2, chosen option (a)) ─────────
    // Items with `parent_id` unset, OR pointing at a folder that no
    // longer exists, render here — never nested under a folder whose path
    // merely contains them (that would render a FALSE parentage, exactly
    // what DD-9's standalone badge exists to prevent).

    function buildOtherItemsPanel() {
      var details = document.createElement('details');
      details.className = 'mcp-tool-item';
      details.setAttribute('data-testid', 'kb-other-items-panel');

      var summary = document.createElement('summary');
      summary.className = 'mcp-tool-summary';
      var textSpan = _el('span', { className: 'mcp-tool-summary-text', text: 'Other items' });
      summary.appendChild(textSpan);
      var chevron = _el('span', { className: 'mcp-tool-chevron', text: '▸' });
      summary.appendChild(chevron);
      details.appendChild(summary);

      var body = _el('div', { className: 'mcp-tool-body' });
      var filesEl = _el('div', { className: 'kb-other-items-files' });
      body.appendChild(filesEl);
      details.appendChild(body);

      details.addEventListener('toggle', function () {
        if (!details.open) closeAnyOpenItemMenu();
      });

      return { detailsEl: details, summaryText: textSpan, filesEl: filesEl };
    }

    function renderOtherItems(otherItems) {
      if (otherItems.length === 0) {
        if (otherItemsPanel && otherItemsPanel.detailsEl.parentNode) {
          otherItemsPanel.detailsEl.parentNode.removeChild(otherItemsPanel.detailsEl);
        }
        return;
      }
      if (!otherItemsPanel) {
        otherItemsPanel = buildOtherItemsPanel();
      }
      // Trailing — appended after every folder panel currently in
      // `foldersListEl` (renderFolders always runs before renderAllItems
      // in every call path below, so folder panels are already placed).
      foldersListEl.appendChild(otherItemsPanel.detailsEl);
      otherItemsPanel.summaryText.textContent = 'Other items (' + otherItems.length + ')';
      otherItemsPanel.filesEl.textContent = '';
      otherItems.forEach(function (item) {
        otherItemsPanel.filesEl.appendChild(buildFileItemRow(item, { standalone: true }));
      });
    }

    // ── Items reconciliation (L1-D2/FIX1 carried) — only ever called at
    // mount, on an actual items-signature change, or right after a folder
    // mutation. Never called from `renderFolders`, so a metadata-only
    // poll tick never touches file rows or the open-menu tracker.
    function renderFolderFiles(panel, fileItemsForFolder) {
      panel.filesEl.textContent = '';
      if (fileItemsForFolder.length === 0) {
        panel.filesEl.appendChild(_el('div', {
          className: 'empty-state',
          text: 'No files indexed from this folder yet.'
        }));
        return;
      }
      fileItemsForFolder.forEach(function (item) {
        panel.filesEl.appendChild(buildFileItemRow(item, { standalone: false }));
      });
    }

    function renderAllItems(nextItems) {
      // Edge case (L5-D4/L6-D4): the overflow menu open when the list
      // re-renders must close rather than leak a detached element + a
      // stale document-level listener.
      closeAnyOpenItemMenu();

      var folderIds = {};
      currentFolders.forEach(function (f) { folderIds[f.id] = true; });

      var byFolder = {};
      var other = [];
      nextItems
        .filter(function (it) { return it.type === 'file'; })
        .forEach(function (item) {
          if (item.parent_id && folderIds[item.parent_id]) {
            (byFolder[item.parent_id] = byFolder[item.parent_id] || []).push(item);
          } else {
            other.push(item);
          }
        });

      Object.keys(folderPanels).forEach(function (id) {
        renderFolderFiles(folderPanels[id], byFolder[id] || []);
      });
      renderOtherItems(other);
    }
    renderAllItems(items);

    function refreshStatusNow() {
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/status')
        .then(function (r) {
          if (!r.ok) throw new Error('status fetch failed: HTTP ' + r.status);
          return r.json();
        })
        .then(function (status) {
          renderStatusSummary(status);
          renderFolders((status && status.folders) || []);
        })
        .catch(function () {
          // L1-D2: a failed refresh leaves the last-rendered state.
        });
    }

    function refreshItemsListNow() {
      fetch('/api/knowledge-bases/' + encodeURIComponent(kb.id) + '/items')
        .then(function (r) {
          if (!r.ok) throw new Error('items fetch failed: HTTP ' + r.status);
          return r.json();
        })
        .then(function (freshItems) { renderAllItems(freshItems); })
        .catch(function () {
          // Leave last-rendered state; the operator can retry.
        });
    }

    addFolderBtn.addEventListener('click', function () {
      folderErrorEl.textContent = '';
      var path = folderInput.value.trim();
      if (!path) {
        folderErrorEl.textContent = 'Folder path is required.';
        return;
      }
      addFolderBtn.disabled = true;
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
        addFolderBtn.disabled = false;
        refreshStatusNow();
        // kb-studio-round-trip remediation FIX 1: registration changes the
        // status counts, so the poll-invalidation path in `studio.js`
        // (comparing `/status`'s counts against what the items list was
        // last rendered against) refreshes the list on its own within one
        // poll interval — no separate callback needed.
      }).catch(function (err) {
        addFolderBtn.disabled = false;
        folderErrorEl.textContent = err.message || String(err);
      });
    });

    foldersSection.appendChild(chunksPanel);
    foldersSection.appendChild(sourcePanel);

    // ── Status (AC-6, amended by the HAT polish pass) — counts / chunks /
    // indexer, plus the re-index controls. Created AFTER `foldersSection`
    // so it renders BELOW it. `renderStatusSummary` is a hoisted function
    // declaration and `summaryEl` a hoisted `var`, so the earlier
    // `refreshStatusNow` / `updateStatus` call sites still resolve — both
    // only ever run from an event handler or a promise, long after this
    // assignment.
    var statusSection = _section(root, 'Status');
    var summaryEl = _el('div', { className: 'kb-status-summary' });
    summaryEl.setAttribute('data-testid', 'kb-status-summary');
    statusSection.appendChild(summaryEl);

    function renderStatusSummary(status) {
      summaryEl.textContent = '';
      if (!status) {
        summaryEl.appendChild(_el('div', { className: 'admin-loading', text: 'Loading status…' }));
        return;
      }
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
    renderStatusSummary(initialStatus);

    // ── Re-index ─────────────────────────────────────────────────────
    // Both buttons POST to /reindex, which is whole-knowledge-base by
    // construction (`requeue_for_reindex` is one UPDATE across every
    // folder) — there is no per-folder re-index. Sitting among the
    // per-folder panels they read as folder-scoped, which is the
    // misreading this pass fixes: they moved here, the labels name what
    // is re-indexed rather than a bare "all", and the hint states the
    // scope in the page's existing `.field-hint` voice.
    var reindexHint = _el('p', {
      className: 'field-hint kb-reindex-hint',
      text:
        'Re-indexing always covers every folder registered in this knowledge base — ' +
        'there is no per-folder re-index. "Changed files" re-walks each folder and ' +
        'indexes only what differs; "All files" re-embeds every file from scratch.'
    });
    reindexHint.setAttribute('data-testid', 'kb-reindex-scope-hint');
    statusSection.appendChild(reindexHint);
    var reindexRow = _el('div', { className: 'kb-reindex-row' });
    var reindexChangedBtn = _btn(
      'btn-outlined-primary', 'kb-reindex-changed-btn', 'Re-index changed files'
    );
    var reindexAllBtn = _btn('btn-outlined-primary', 'kb-reindex-all-btn', 'Re-index all files');
    reindexRow.appendChild(reindexChangedBtn);
    reindexRow.appendChild(reindexAllBtn);
    statusSection.appendChild(reindexRow);

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
        // The reindex response carries no indexer state, so issue one
        // immediate status fetch rather than waiting a full poll interval.
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

    // ── Search (AC-6, DD-6) ──────────────────────────────────────────────
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
          // AC-12 (carried): the degrade line and the indexer word come
          // from the SAME search response — never the polled status.
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

    // ── Danger Zone (AC-12) — matches mcp-server-editor.js's classes
    // exactly: `editor-section danger-zone` + `section-title danger-zone-
    // title` + `btn-muted-destructive`.
    var danger = _el('div', { className: 'editor-section danger-zone' });
    danger.appendChild(_el('div', { className: 'section-title danger-zone-title', text: 'Danger Zone' }));
    var deleteBtn = _el('button', { className: 'btn-muted-destructive delete-btn' });
    deleteBtn.type = 'button';
    deleteBtn.setAttribute('data-testid', 'delete-knowledge-base-btn');
    // HAT polish pass: a red trash icon BESIDE the label, not instead of
    // it — the exact shape `mcp-server-editor.js`'s own Danger Zone
    // delete already has. The icon sits OUTSIDE the `data-confirm-title`
    // span so App.confirmDelete swaps only the label text on arm and the
    // glyph persists through the confirm flow. Colour and layout need no
    // new CSS: `.btn-muted-destructive` is already `inline-flex` with a
    // 6px gap and `color: var(--status-danger)`, which the icon's
    // `stroke="currentColor"` inherits, and components.css already sizes
    // `.btn-muted-destructive svg` at 16px.
    _appendIcon(deleteBtn, 'trash');
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

    return {
      updateStatus: function (status) {
        renderStatusSummary(status);
        renderFolders((status && status.folders) || []);
      },
      updateItems: renderAllItems
    };
  }

  window.App.studio.renderKnowledgeGrid = renderKnowledgeGrid;
  window.App.studio.renderKnowledgeDetail = renderKnowledgeDetail;
})();
