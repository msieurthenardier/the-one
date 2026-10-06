(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // SURFACES section samples the M17 F3 tile/list vocabulary: entity tiles
  // (surface + hairline + radius-md; hover shifts to --border-hover;
  // selected = accent border) and 40px list rows with hover surface shift.
  // The app picker sample was retired with the top bar (M25 F2 L6); the rail
  // is demonstrated by the library reference. The toggle demo moved to the
  // library reference (ui-choices-section.js, App.ui.toggle). The former
  // section navigation sample was retired with that control (M25 F3 L5a):
  // the Settings nav is App.ui.navGroups, demonstrated in the "Library:
  // lists and navigation" section.
  // Rendered via createElement per the innerHTML-sink freeze (M17 F1).

  function el(tag, className) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  function sample(labelText) {
    var wrap = el('div');
    wrap.style.display = 'flex';
    wrap.style.flexDirection = 'column';
    wrap.style.gap = '8px';
    var label = el('span');
    label.style.fontFamily = 'var(--font-family-mono)';
    label.style.fontSize = 'var(--font-size-tiny)';
    label.style.color = 'var(--fg-muted)';
    label.textContent = labelText;
    wrap.appendChild(label);
    return wrap;
  }

  function tile(name, description, active) {
    var node = el('div', 'entity-tile' + (active ? ' active' : ''));
    node.setAttribute('role', 'listitem');
    node.tabIndex = 0;
    if (active) node.setAttribute('aria-selected', 'true');
    var nameEl = el('span', 'entity-tile-name');
    nameEl.textContent = name;
    node.appendChild(nameEl);
    var descEl = el('span', 'entity-tile-description');
    descEl.textContent = description;
    node.appendChild(descEl);
    return node;
  }

  function render(host) {
    // --- Entity tile (single) ---
    var single = sample('entity-tile (single)');
    single.appendChild(tile('Sample Tile', 'Short description text for the tile.', false));
    host.appendChild(single);

    // --- Entity tile grid ---
    var gridSample = sample('entity-tile-grid');
    var grid = el('div', 'entity-tile-grid');
    grid.appendChild(tile('Tile One', 'First grid tile.', false));
    grid.appendChild(tile('Tile Two (active)', 'Selected tile state.', true));
    grid.appendChild(tile('Tile Three', 'Third grid tile.', false));
    gridSample.appendChild(grid);
    host.appendChild(gridSample);

    // --- List items (40px rows, hover surface shift) ---
    var listSample = sample('list-item');
    var list = el('div');
    list.style.display = 'flex';
    list.style.flexDirection = 'column';
    list.style.gap = '4px';
    list.style.maxWidth = '320px';
    var plain = el('div', 'list-item');
    plain.textContent = 'Default list item';
    list.appendChild(plain);
    var active = el('div', 'list-item active');
    active.textContent = 'Active list item';
    list.appendChild(active);
    var confirm = el('div', 'list-item confirm-delete');
    var confirmTitle = el('span');
    confirmTitle.setAttribute('data-confirm-title', '');
    confirmTitle.textContent = 'Confirm-delete list item';
    confirm.appendChild(confirmTitle);
    var deleteBtn = el('button', 'list-item-delete');
    deleteBtn.type = 'button';
    deleteBtn.setAttribute('aria-label', 'delete');
    deleteBtn.textContent = '×';
    confirm.appendChild(deleteBtn);
    list.appendChild(confirm);
    listSample.appendChild(list);
    host.appendChild(listSample);
  }

  window.App.admin.designLanguage.surfacesSection = { render: render };
})();
