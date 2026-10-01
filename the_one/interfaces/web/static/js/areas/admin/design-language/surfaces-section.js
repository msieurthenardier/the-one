(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // SURFACES section samples the M17 F3 tile/list vocabulary plus brand
  // chrome miniatures: entity tiles (surface + hairline + radius-md; hover
  // shifts to --border-hover; selected = accent border), 40px list rows
  // with hover surface shift, section-nav and static app-picker miniatures
  // (no event bindings, no real renderTopBar invocation). The toggle demo
  // moved to the library reference (ui-choices-section.js, App.ui.toggle).
  // Rendered via createElement per the innerHTML-sink freeze (M17 F1).

  var SVG_NS = 'http://www.w3.org/2000/svg';

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

  function pickerButton(labelText, current) {
    var btn = el('button', 'app-picker-button');
    btn.type = 'button';
    if (current) btn.setAttribute('aria-current', 'page');
    var iconWrap = el('span', 'app-picker-button-icon');
    var svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 18 18');
    svg.setAttribute('fill', 'currentColor');
    var circle = document.createElementNS(SVG_NS, 'circle');
    circle.setAttribute('cx', '9');
    circle.setAttribute('cy', '9');
    circle.setAttribute('r', '6');
    circle.setAttribute('fill', 'none');
    circle.setAttribute('stroke', 'currentColor');
    circle.setAttribute('stroke-width', '1.5');
    svg.appendChild(circle);
    iconWrap.appendChild(svg);
    btn.appendChild(iconWrap);
    var labelEl = el('span', 'app-picker-button-label');
    labelEl.textContent = labelText;
    btn.appendChild(labelEl);
    return btn;
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

    // --- Section nav ---
    var navSample = sample('section-nav');
    var nav = el('div', 'section-nav');
    nav.style.maxWidth = '220px';
    var items = ['Item one', 'Item two (current)', 'Item three'];
    for (var i = 0; i < items.length; i++) {
      var navBtn = el('button', 'section-nav-item');
      navBtn.type = 'button';
      if (i === 1) navBtn.setAttribute('aria-current', 'page');
      navBtn.textContent = items[i];
      nav.appendChild(navBtn);
    }
    navSample.appendChild(nav);
    host.appendChild(navSample);

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

    // --- App-picker miniature (rest + active, static) ---
    var pickerSample = sample('app-picker-button (rest / active)');
    var pickerRow = el('div');
    pickerRow.style.display = 'flex';
    pickerRow.style.gap = '12px';
    pickerRow.style.alignItems = 'center';
    pickerRow.appendChild(pickerButton('System', false));
    pickerRow.appendChild(pickerButton('System', true));
    pickerSample.appendChild(pickerRow);
    host.appendChild(pickerSample);
  }

  window.App.admin.designLanguage.surfacesSection = { render: render };
})();
