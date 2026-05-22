// App.studio.discoverableDropdown — live-data combobox component (M11 F3 L5).
//
// Shared frontend dropdown used by L6a's allowlist editor and L6b's
// routing-rules + per-agent-overlay editors. Combobox shape: typeahead
// ``<input>`` + naive-render results panel + grouped sections +
// chip-list selected-values strip + Refresh button + stale-entry
// rendering. Account-scoped (one instance per axis per account);
// consumes the L4 API at ``GET/POST
// /api/connector-accounts/{accountId}/discoverable-entities``.
//
// Public surface:
//   App.studio.discoverableDropdown(opts) -> HTMLElement
//     opts = {
//       axis: 'peers' | 'channels' | 'groups' | 'roles',
//       accountId: string,
//       currentValues: string[],            // ids currently selected
//       onChange: function(newValues: string[]) -> void,
//       vocab: object                       // App.studio.connectorVocabulary entry
//     }
//
// Behaviour:
//   - Naive render up to 1000 items; > 1000 triggers a type-to-filter
//     hint to avoid eager DOM ballooning.
//   - AbortController-based race protection between an in-flight GET
//     and a POST refresh click (last-response-wins).
//   - Unknown-id chips render id-as-label with a "label unknown — try
//     Refresh" tooltip (no data loss for ids the bot can no longer see).
//   - Stale entries (``stale: true`` in the API response) get
//     ``data-stale="true"`` on the item AND on any matching chip; CSS
//     applies the strikethrough.
//   - The component is the only mutation channel — onChange fires with
//     the new ``currentValues`` array; callers re-render the component
//     if they want to change ``opts.currentValues`` from outside.
//
// Load order: attaches to ``window.App.studio``; loads BETWEEN
// ``connector-vocabulary.js`` and ``connector-account-editor.js`` in
// ``index.html``.

(function () {
  'use strict';

  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  // Axis (plural) → singular vocab key. Placeholder text is derived
  // from ``vocab[axisSingular]``; there is no ``vocab.placeholder``
  // field per F1 L6 vocabulary discipline.
  var _AXIS_TO_SINGULAR = {
    peers: 'peer',
    channels: 'channel',
    groups: 'group',
    roles: 'role'
  };

  var _LARGE_AXIS_THRESHOLD = 1000;
  var _LARGE_AXIS_MIN_FILTER_CHARS = 2;

  function _escapeAttr(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function _placeholderFor(axis, vocab) {
    var singular = _AXIS_TO_SINGULAR[axis];
    var label = (vocab && singular && vocab[singular]) ? vocab[singular] : 'entry';
    return 'Add ' + label + '…';
  }

  function _buildDOM(opts) {
    var axis = opts.axis;
    var accountId = opts.accountId;
    var placeholder = _placeholderFor(axis, opts.vocab);
    var menuId = 'dd-menu-' + axis + '-' + accountId;
    var inputId = 'dd-input-' + axis + '-' + accountId;

    var root = document.createElement('div');
    root.className = 'discoverable-dropdown';
    root.setAttribute('data-axis', axis);
    root.setAttribute('data-account-id', accountId);
    root.setAttribute('data-testid', 'discoverable-dropdown-' + axis);

    root.innerHTML =
      '<div class="discoverable-dropdown-input-row">' +
        '<input type="text" class="discoverable-dropdown-input" ' +
               'role="combobox" aria-autocomplete="list" aria-expanded="false" ' +
               'aria-haspopup="listbox" aria-controls="' + _escapeAttr(menuId) + '" ' +
               'aria-activedescendant="" ' +
               'id="' + _escapeAttr(inputId) + '" ' +
               'data-testid="discoverable-dropdown-input-' + _escapeAttr(axis) + '" ' +
               'placeholder="' + _escapeAttr(placeholder) + '" ' +
               'autocomplete="off" disabled>' +
        '<button type="button" class="discoverable-dropdown-refresh" ' +
                'data-testid="discoverable-dropdown-refresh-' + _escapeAttr(axis) + '" ' +
                'aria-label="Refresh">↻</button>' +
      '</div>' +
      '<div class="discoverable-dropdown-menu" role="listbox" ' +
           'id="' + _escapeAttr(menuId) + '" ' +
           'data-testid="discoverable-dropdown-menu-' + _escapeAttr(axis) + '" hidden></div>' +
      '<div class="chip-list-editor discoverable-dropdown-chips" ' +
           'role="group" aria-label="Selected entries" ' +
           'data-testid="discoverable-dropdown-chips-' + _escapeAttr(axis) + '"></div>' +
      '<div class="discoverable-dropdown-status" ' +
           'data-testid="discoverable-dropdown-status-' + _escapeAttr(axis) + '" ' +
           'aria-live="polite"></div>';

    return root;
  }

  function _findEntityById(entities, axis, id) {
    if (!entities || !entities[axis]) return null;
    var list = entities[axis];
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].id === id) return list[i];
    }
    return null;
  }

  function _renderChips(state) {
    var chipsEl = state.root.querySelector('.discoverable-dropdown-chips');
    if (!chipsEl) return;
    chipsEl.innerHTML = '';

    for (var i = 0; i < state.currentValues.length; i++) {
      var id = state.currentValues[i];
      var entity = _findEntityById(state.entities, state.axis, id);
      var chip = document.createElement('span');
      chip.className = 'chip';
      chip.setAttribute('data-id', id);
      chip.setAttribute('data-testid', 'discoverable-dropdown-chip-' + state.axis);

      var label;
      if (entity) {
        label = entity.label || id;
        if (entity.stale === true) {
          chip.setAttribute('data-stale', 'true');
          chip.setAttribute('title', label + ' — Bot can no longer see this entity.');
        }
      } else {
        // Unknown-id fallback: bare id + tooltip. Operator data
        // preserved; only label degrades.
        label = id;
        chip.setAttribute('data-unknown', 'true');
        chip.setAttribute('title', 'label unknown — try Refresh');
      }

      var labelSpan = document.createElement('span');
      labelSpan.className = 'discoverable-dropdown-chip-label';
      labelSpan.textContent = label;
      chip.appendChild(labelSpan);

      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'chip-remove';
      removeBtn.setAttribute('aria-label', 'Remove ' + label);
      removeBtn.setAttribute('data-testid', 'discoverable-dropdown-chip-remove-' + state.axis);
      removeBtn.textContent = '×';
      removeBtn.addEventListener('click', function (boundId) {
        return function () { _removeValue(state, boundId); };
      }(id));
      chip.appendChild(removeBtn);

      chipsEl.appendChild(chip);
    }
  }

  function _renderMenu(state) {
    var menuEl = state.root.querySelector('.discoverable-dropdown-menu');
    if (!menuEl) return;
    menuEl.innerHTML = '';
    state.focusedItemId = null;

    var items = (state.entities && state.entities[state.axis]) || [];

    // > 1000 entries: skip eager render. The typeahead filter populates
    // matches on demand once enough characters are typed.
    if (items.length > _LARGE_AXIS_THRESHOLD) {
      state.largeAxis = true;
      _setStatus(state, 'Filter to narrow results (> 1000 entries; type at least ' +
                        _LARGE_AXIS_MIN_FILTER_CHARS + ' characters).');
      menuEl.setAttribute('hidden', '');
      return;
    }
    state.largeAxis = false;

    // Group by ``entity.group`` (free-form group key). Items with no
    // group land in an implicit "no-group" bucket rendered without a
    // header.
    var groupOrder = [];
    var groupBuckets = {};
    for (var i = 0; i < items.length; i++) {
      var entity = items[i];
      var groupKey = (entity.group === null || entity.group === undefined) ? '' : String(entity.group);
      if (!groupBuckets[groupKey]) {
        groupBuckets[groupKey] = [];
        groupOrder.push(groupKey);
      }
      groupBuckets[groupKey].push(entity);
    }

    for (var gi = 0; gi < groupOrder.length; gi++) {
      var key = groupOrder[gi];
      var bucket = groupBuckets[key];
      var groupEl = document.createElement('div');
      groupEl.className = 'discoverable-dropdown-group';
      groupEl.setAttribute('data-group-key', key);

      if (key) {
        var headerEl = document.createElement('div');
        headerEl.className = 'discoverable-dropdown-group-header';
        headerEl.textContent = _lookupGroupLabel(state, key);
        groupEl.appendChild(headerEl);
      }

      for (var ei = 0; ei < bucket.length; ei++) {
        groupEl.appendChild(_buildMenuItem(state, bucket[ei]));
      }
      menuEl.appendChild(groupEl);
    }

    _setStatus(state, items.length === 0 ? 'No entries available.' : '');
  }

  function _lookupGroupLabel(state, groupKey) {
    // Cross-axis lookup: a group key in one axis (e.g., a guild id for
    // channels) may match an entity id in another axis. Fall back to
    // the bare key string.
    if (!groupKey) return '';
    var axes = ['groups', 'channels', 'peers', 'roles'];
    for (var i = 0; i < axes.length; i++) {
      var axis = axes[i];
      if (axis === state.axis) continue;
      var entity = _findEntityById(state.entities, axis, groupKey);
      if (entity && entity.label) return entity.label;
    }
    return groupKey;
  }

  function _buildMenuItem(state, entity) {
    var item = document.createElement('div');
    item.className = 'discoverable-dropdown-item';
    item.setAttribute('role', 'option');
    item.setAttribute('id', 'dd-item-' + state.axis + '-' + entity.id);
    item.setAttribute('data-id', entity.id);
    item.setAttribute('data-testid', 'discoverable-dropdown-item-' + state.axis);
    item.setAttribute('tabindex', '-1');

    var selected = state.currentValues.indexOf(entity.id) >= 0;
    item.setAttribute('aria-selected', selected ? 'true' : 'false');

    if (entity.stale === true) {
      item.setAttribute('data-stale', 'true');
      item.setAttribute('title', 'Bot can no longer see this entity.');
    }

    item.textContent = entity.label || entity.id;

    item.addEventListener('mousedown', function (event) {
      // mousedown so the click registers before the input loses focus
      // and closes the menu via the blur handler.
      event.preventDefault();
      _addValue(state, entity.id);
    });

    return item;
  }

  function _setStatus(state, text) {
    var statusEl = state.root.querySelector('.discoverable-dropdown-status');
    if (statusEl) statusEl.textContent = text;
  }

  function _setMenuOpen(state, open) {
    var input = state.root.querySelector('.discoverable-dropdown-input');
    var menu = state.root.querySelector('.discoverable-dropdown-menu');
    if (!input || !menu) return;
    state.menuOpen = !!open;
    if (open && !state.largeAxis) {
      menu.removeAttribute('hidden');
      input.setAttribute('aria-expanded', 'true');
    } else {
      menu.setAttribute('hidden', '');
      input.setAttribute('aria-expanded', 'false');
      input.setAttribute('aria-activedescendant', '');
      state.focusedItemId = null;
    }
  }

  function _applyTypeaheadFilter(state) {
    var input = state.root.querySelector('.discoverable-dropdown-input');
    var menu = state.root.querySelector('.discoverable-dropdown-menu');
    if (!input || !menu) return;
    var query = (input.value || '').trim().toLowerCase();
    state.filter = query;

    if (state.largeAxis) {
      if (query.length < _LARGE_AXIS_MIN_FILTER_CHARS) {
        menu.setAttribute('hidden', '');
        input.setAttribute('aria-expanded', 'false');
        _setStatus(state, 'Filter to narrow results (> 1000 entries; type at least ' +
                          _LARGE_AXIS_MIN_FILTER_CHARS + ' characters).');
        return;
      }
      _renderLargeAxisSubset(state, query);
      menu.removeAttribute('hidden');
      input.setAttribute('aria-expanded', 'true');
      return;
    }

    var groups = menu.querySelectorAll('.discoverable-dropdown-group');
    var visibleCount = 0;
    for (var gi = 0; gi < groups.length; gi++) {
      var group = groups[gi];
      var items = group.querySelectorAll('.discoverable-dropdown-item');
      var anyVisible = false;
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        var label = (item.textContent || '').toLowerCase();
        var matches = !query || label.indexOf(query) >= 0;
        if (matches) {
          item.removeAttribute('hidden');
          anyVisible = true;
          visibleCount++;
        } else {
          item.setAttribute('hidden', '');
        }
      }
      if (anyVisible) group.removeAttribute('hidden');
      else group.setAttribute('hidden', '');
    }

    var total = (state.entities[state.axis] || []).length;
    if (visibleCount === 0 && total > 0) _setStatus(state, 'No matches');
    else if (total === 0) _setStatus(state, 'No entries available.');
    else _setStatus(state, '');
  }

  function _renderLargeAxisSubset(state, query) {
    var menu = state.root.querySelector('.discoverable-dropdown-menu');
    menu.innerHTML = '';
    var items = (state.entities && state.entities[state.axis]) || [];
    var matches = [];
    for (var i = 0; i < items.length; i++) {
      var label = (items[i].label || '').toLowerCase();
      if (label.indexOf(query) >= 0) {
        matches.push(items[i]);
        if (matches.length > _LARGE_AXIS_THRESHOLD) break;
      }
    }
    if (matches.length === 0) {
      _setStatus(state, 'No matches');
      return;
    }
    _setStatus(state, matches.length + ' match' + (matches.length === 1 ? '' : 'es'));
    var groupEl = document.createElement('div');
    groupEl.className = 'discoverable-dropdown-group';
    for (var mi = 0; mi < matches.length; mi++) {
      groupEl.appendChild(_buildMenuItem(state, matches[mi]));
    }
    menu.appendChild(groupEl);
  }

  function _visibleItems(state) {
    var menu = state.root.querySelector('.discoverable-dropdown-menu');
    if (!menu) return [];
    var nodes = menu.querySelectorAll('.discoverable-dropdown-item');
    var visible = [];
    for (var i = 0; i < nodes.length; i++) {
      if (!nodes[i].hasAttribute('hidden')) visible.push(nodes[i]);
    }
    return visible;
  }

  function _focusItemByIndex(state, index) {
    var input = state.root.querySelector('.discoverable-dropdown-input');
    var visible = _visibleItems(state);
    if (visible.length === 0) {
      state.focusedItemId = null;
      if (input) input.setAttribute('aria-activedescendant', '');
      return;
    }
    var clamped = Math.max(0, Math.min(visible.length - 1, index));
    var target = visible[clamped];
    state.focusedItemId = target.id;
    for (var i = 0; i < visible.length; i++) {
      if (visible[i] === target) visible[i].classList.add('discoverable-dropdown-item--focused');
      else visible[i].classList.remove('discoverable-dropdown-item--focused');
    }
    if (input) input.setAttribute('aria-activedescendant', target.id);
    if (target.scrollIntoView) {
      try { target.scrollIntoView({ block: 'nearest' }); }
      catch (e) { /* older browsers */ }
    }
  }

  function _focusedIndex(state) {
    var visible = _visibleItems(state);
    if (!state.focusedItemId) return -1;
    for (var i = 0; i < visible.length; i++) {
      if (visible[i].id === state.focusedItemId) return i;
    }
    return -1;
  }

  function _addValue(state, id) {
    if (!id) return;
    if (state.currentValues.indexOf(id) >= 0) return;
    state.currentValues = state.currentValues.concat([id]);
    _refreshSelectionUI(state);
    _fireOnChange(state);
  }

  function _removeValue(state, id) {
    var next = [];
    for (var i = 0; i < state.currentValues.length; i++) {
      if (state.currentValues[i] !== id) next.push(state.currentValues[i]);
    }
    state.currentValues = next;
    _refreshSelectionUI(state);
    _fireOnChange(state);
  }

  function _refreshSelectionUI(state) {
    _renderChips(state);
    var menu = state.root.querySelector('.discoverable-dropdown-menu');
    if (!menu) return;
    var items = menu.querySelectorAll('.discoverable-dropdown-item');
    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var id = item.getAttribute('data-id');
      item.setAttribute('aria-selected', state.currentValues.indexOf(id) >= 0 ? 'true' : 'false');
    }
  }

  function _fireOnChange(state) {
    if (typeof state.onChange !== 'function') return;
    try { state.onChange(state.currentValues.slice()); }
    catch (e) {
      try { console.error('discoverableDropdown onChange threw:', e); }
      catch (logErr) { /* console missing */ }
    }
  }

  function _handleKeydown(state, event) {
    var key = event.key;
    if (key === 'ArrowDown') {
      event.preventDefault();
      if (!state.menuOpen) _setMenuOpen(state, true);
      var di = _focusedIndex(state);
      _focusItemByIndex(state, di < 0 ? 0 : di + 1);
    } else if (key === 'ArrowUp') {
      event.preventDefault();
      if (!state.menuOpen) _setMenuOpen(state, true);
      var ui = _focusedIndex(state);
      _focusItemByIndex(state, ui < 0 ? 0 : ui - 1);
    } else if (key === 'Enter') {
      var ix = _focusedIndex(state);
      var visible = _visibleItems(state);
      if (ix >= 0 && visible[ix]) {
        event.preventDefault();
        _addValue(state, visible[ix].getAttribute('data-id'));
      }
    } else if (key === 'Escape' || key === 'Tab') {
      _setMenuOpen(state, false);
    }
  }

  function _abortInflight(state) {
    if (state.abortController) {
      try { state.abortController.abort(); }
      catch (e) { /* AbortController.abort doesn't throw in modern browsers */ }
      state.abortController = null;
    }
  }

  // _doFetch consolidates GET (initial mount) + POST (refresh) — sole
  // diffs are the URL suffix, the fetch options, and the status label.
  function _doFetch(state, suffix, fetchOpts, loadingLabel) {
    _abortInflight(state);
    var controller = (typeof AbortController === 'function') ? new AbortController() : null;
    state.abortController = controller;
    if (controller) fetchOpts.signal = controller.signal;

    state.loading = true;
    _setStatus(state, loadingLabel);
    _setInputDisabled(state, true);

    var url = '/api/connector-accounts/' + encodeURIComponent(state.accountId) +
              '/discoverable-entities' + suffix;
    return fetch(url, fetchOpts).then(function (response) {
      if (response.status === 404) {
        return response.json().then(function (body) {
          return { kind: 'pre-probe-404', body: body };
        }, function () {
          return { kind: 'pre-probe-404', body: { detail: 'Run Test Connection first.' } };
        });
      }
      if (response.status === 503) return { kind: 'unsupported' };
      if (!response.ok) return { kind: 'error', status: response.status };
      return response.json().then(function (body) { return { kind: 'ok', body: body }; });
    }).then(function (result) {
      if (state.abortController === controller) state.abortController = null;
      state.loading = false;
      _applyFetchResult(state, result);
    }).catch(function (err) {
      if (err && err.name === 'AbortError') return;
      if (state.abortController === controller) state.abortController = null;
      state.loading = false;
      _setInputDisabled(state, false);
      _setStatus(state, "Couldn't load entities; try Refresh.");
      try { console.error('discoverableDropdown fetch failed:', err); }
      catch (logErr) { /* console missing */ }
    });
  }

  function _fetchEntities(state) {
    return _doFetch(state, '', {}, 'Loading…');
  }

  function _refreshEntities(state) {
    return _doFetch(state, '/refresh', { method: 'POST' }, 'Refreshing…');
  }

  function _applyFetchResult(state, result) {
    _setInputDisabled(state, false);
    if (!result) {
      _setStatus(state, "Couldn't load entities; try Refresh.");
      return;
    }
    if (result.kind === 'pre-probe-404') {
      var detail = (result.body && result.body.detail) || 'Run Test Connection first.';
      _setStatus(state, detail);
      var menu = state.root.querySelector('.discoverable-dropdown-menu');
      if (menu) menu.setAttribute('hidden', '');
      var input = state.root.querySelector('.discoverable-dropdown-input');
      if (input) input.setAttribute('aria-expanded', 'false');
      state.menuOpen = false;
      _renderChips(state);
      return;
    }
    if (result.kind === 'unsupported') {
      _setStatus(state, 'This connector type does not expose discoverable entities.');
      return;
    }
    if (result.kind === 'error') {
      _setStatus(state, "Couldn't load entities; try Refresh.");
      return;
    }
    var body = result.body || {};
    state.entities = body.entities || { peers: [], channels: [], groups: [], roles: [] };
    state.fetched_at = body.fetched_at || '';
    state.stale_seconds = (typeof body.stale_seconds === 'number') ? body.stale_seconds : null;
    _renderMenu(state);
    _renderChips(state);
  }

  function _setInputDisabled(state, disabled) {
    var input = state.root.querySelector('.discoverable-dropdown-input');
    if (!input) return;
    if (disabled) input.setAttribute('disabled', '');
    else input.removeAttribute('disabled');
  }

  function _wireEvents(state) {
    var input = state.root.querySelector('.discoverable-dropdown-input');
    var refresh = state.root.querySelector('.discoverable-dropdown-refresh');
    var menu = state.root.querySelector('.discoverable-dropdown-menu');

    if (input) {
      input.addEventListener('input', function () { _applyTypeaheadFilter(state); });
      input.addEventListener('keydown', function (event) { _handleKeydown(state, event); });
      input.addEventListener('focus', function () {
        if (state.loading) return;
        if (state.largeAxis &&
            (state.filter || '').length < _LARGE_AXIS_MIN_FILTER_CHARS) return;
        _setMenuOpen(state, true);
      });
      input.addEventListener('blur', function () {
        // Defer the close so a mousedown on an item still registers.
        setTimeout(function () {
          if (!state.root.contains(document.activeElement)) _setMenuOpen(state, false);
        }, 100);
      });
    }

    if (refresh) {
      refresh.addEventListener('click', function () { _refreshEntities(state); });
    }

    if (menu) {
      // Click delegation fallback (mousedown on items already adds; this
      // is a safety net for keyboard-driven menus that activate via click).
      menu.addEventListener('click', function (event) {
        var target = event.target;
        while (target && target !== menu) {
          if (target.classList && target.classList.contains('discoverable-dropdown-item')) {
            _addValue(state, target.getAttribute('data-id'));
            return;
          }
          target = target.parentNode;
        }
      });
    }
  }

  function discoverableDropdown(opts) {
    if (!opts || typeof opts !== 'object') {
      throw new TypeError('discoverableDropdown: opts must be an object');
    }
    if (!opts.axis || !_AXIS_TO_SINGULAR[opts.axis]) {
      throw new TypeError('discoverableDropdown: opts.axis must be one of ' +
                          'peers/channels/groups/roles');
    }
    if (typeof opts.accountId !== 'string' || !opts.accountId) {
      throw new TypeError('discoverableDropdown: opts.accountId must be a non-empty string');
    }

    var root = _buildDOM(opts);
    var state = {
      root: root,
      axis: opts.axis,
      accountId: opts.accountId,
      currentValues: Array.isArray(opts.currentValues) ? opts.currentValues.slice() : [],
      onChange: typeof opts.onChange === 'function' ? opts.onChange : function () {},
      vocab: opts.vocab || {},
      entities: { peers: [], channels: [], groups: [], roles: [] },
      fetched_at: '',
      stale_seconds: null,
      loading: false,
      filter: '',
      menuOpen: false,
      focusedItemId: null,
      largeAxis: false,
      abortController: null
    };

    _wireEvents(state);
    _renderChips(state);
    _fetchEntities(state);

    return root;
  }

  window.App.studio.discoverableDropdown = discoverableDropdown;
})();
