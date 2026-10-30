(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var NOTE_TESTID_DEFAULT = 'time-tool-note';

  // App.ui.groupTile(opts) -> {el, body, nameEl, expandBtn, toggle (the master's App.ui.toggle
  // controller or null), setCount(text), setMaster(state),
  // setToolCount(n|label), setExpanded(bool), isExpanded(), setSubtitle(text|node
  // |null), destroy()} (M31 F2 L4, flight DD3). The tile the Built-in tools and
  // MCP tabs share: a master tristate switch, a name, chips, header actions, an
  // optional subtitle, an expand button and a collapsible body.
  //   name, count (text, e.g. "3 / 4 enabled"; omitted = no count chip), chips
  //   [text], actions [node] (the host builds them, e.g. a small Refresh button),
  //   subtitle (text or node), master {label (aria-label), state 'on'|'off'|
  //   'mixed', onChange(nextChecked), disabled, testid}, toolCount (a number: the
  //   expand button reads "<strong>N</strong> tools", "1 tool" for one) or
  //   toolLabel (text when the count is unknown, e.g. "Tools"), expanded,
  //   onExpand(expanded), onFirstExpand(body) (fires once, on the first expand),
  //   testid, dataset (applied to the root), expandTestid, bodyTestid.
  //   expand: false (M33 F4 L06) omits the expand button and the body: body and expandBtn
  //   are null, setExpanded/setToolCount are no-ops, and the host appends its own children
  //   under el (el is then div.ui-group-tile-row and the optional subtitle, nothing else).
  //   expandLabel (function(countText) -> string, M31 F5 L11, A20): names the expand
  //   button by its content plus the owner ("Tools for Docs search", "3 tools for
  //   Docs search"); it sets aria-label, is re-applied by setToolCount, and drops the
  //   button's aria-describedby to the name span (the owner is not read twice). The
  //   visible text is unchanged. Without it the button keeps its content-only name.
  //   master.tristate (default true; false = a plain on/off switch with
  //   role=switch, never mixed: setMaster('mixed') then reads as off) and
  //   master.describedBy (id of an outside element that describes the master) and
  //   master.dataset (applied to the master's native input, M31 F2 L07b).
  //   el is div.ui-group-tile: div.ui-group-tile-row (the master App.ui.toggle
  //   with tristate, span.ui-group-tile-name, span.ui-group-tile-chip for the
  //   count and each extra chip, div.ui-group-tile-actions), an optional
  //   div.ui-group-tile-subtitle, button.ui-group-tile-expand[aria-expanded]
  //   (the label and span.ui-group-tile-chevron) and div.ui-group-tile-body
  //   [hidden]. The master is silent on setMaster; a user click on a mixed
  //   master gives checked and onChange(true). The tile never changes its
  //   children itself: the consumer does, and calls setMaster/setCount back.
  App.ui.groupTile = function (opts) {
    opts = opts || {};
    if (!opts.name) throw new Error('App.ui.groupTile: name is required');
    var util = App.ui.util;
    var master = opts.master || null;

    var root = util.el('div', { className: 'ui-group-tile' });
    util.applyDataset(root, opts.dataset);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    var row = util.el('div', { className: 'ui-group-tile-row' });
    var toggle = null;
    if (master) {
      toggle = App.ui.toggle({
        label: master.label || 'Enable all ' + opts.name,
        labelHidden: true,
        tristate: master.tristate !== false,
        dataset: master.dataset,
        disabled: !!master.disabled,
        describedBy: master.describedBy,
        testid: master.testid,
        onChange: master.onChange
      });
      row.appendChild(toggle.el);
    }
    var nameEl = util.el('span', {
      className: 'ui-group-tile-name',
      id: util.uid('gt-name'),
      text: opts.name
    });
    row.appendChild(nameEl);
    var countEl = null;
    if (opts.count !== undefined && opts.count !== null && opts.count !== '') {
      countEl = util.el('span', { className: 'ui-group-tile-chip', text: opts.count });
      row.appendChild(countEl);
    }
    var chips = opts.chips || [];
    var i;
    for (i = 0; i < chips.length; i++) {
      row.appendChild(util.el('span', { className: 'ui-group-tile-chip', text: chips[i] }));
    }
    var actions = opts.actions || [];
    if (actions.length) {
      var actionsEl = util.el('div', { className: 'ui-group-tile-actions' });
      for (i = 0; i < actions.length; i++) actionsEl.appendChild(actions[i]);
      row.appendChild(actionsEl);
    }
    root.appendChild(row);

    var subtitleEl = null;
    function setSubtitle(value) {
      if (value === null || value === undefined || value === '') {
        if (subtitleEl && subtitleEl.parentNode) subtitleEl.parentNode.removeChild(subtitleEl);
        subtitleEl = null;
        return;
      }
      if (!subtitleEl) {
        subtitleEl = util.el('div', { className: 'ui-group-tile-subtitle' });
        root.insertBefore(subtitleEl, row.nextSibling);
      }
      subtitleEl.textContent = '';
      if (typeof value === 'string') {
        subtitleEl.textContent = value;
      } else {
        subtitleEl.appendChild(value);
      }
    }
    setSubtitle(opts.subtitle);

    // expand: false (M33 F4 L06) builds the tile without its expand button and body: a card
    // whose host appends its own children under `el` (the Self-configuration items).
    var withExpand = opts.expand !== false;
    var expandBtn = null;
    var labelEl = null;
    var body = null;
    if (withExpand) {
      expandBtn = util.el('button', {
        type: 'button',
        className: 'ui-group-tile-expand',
        'aria-expanded': 'false',
        // The tile's name joins the button's name through the description, so "3 tools"
        // is not the whole of what a screen reader hears (SC 2.4.6, 4.1.2).
        'aria-describedby': typeof opts.expandLabel === 'function' ? undefined : nameEl.id,
        'data-testid': opts.expandTestid
      });
      labelEl = util.el('span', { className: 'ui-group-tile-expand-label' });
      var chevron = util.el('span', {
        className: 'ui-group-tile-chevron',
        'aria-hidden': 'true',
        text: '▸'
      });
      expandBtn.appendChild(labelEl);
      expandBtn.appendChild(chevron);
      root.appendChild(expandBtn);

      body = util.el('div', {
        className: 'ui-group-tile-body',
        hidden: true,
        'data-testid': opts.bodyTestid
      });
      root.appendChild(body);
    }

    function setToolCount(value) {
      if (!withExpand) return;
      labelEl.textContent = '';
      if (typeof value === 'number') {
        labelEl.appendChild(util.el('strong', { text: String(value) }));
        labelEl.appendChild(document.createTextNode(value === 1 ? ' tool' : ' tools'));
      } else {
        labelEl.textContent = value === null || value === undefined ? 'Tools' : String(value);
      }
      if (typeof opts.expandLabel === 'function') {
        expandBtn.setAttribute('aria-label', String(opts.expandLabel(labelEl.textContent)));
      }
    }
    setToolCount(typeof opts.toolCount === 'number' ? opts.toolCount : (opts.toolLabel || 'Tools'));

    function setMaster(state) {
      if (!toggle) return;
      if (state === 'mixed' && toggle.setIndeterminate) {
        toggle.setChecked(false);
        toggle.setIndeterminate(true);
      } else {
        toggle.setChecked(state === 'on');
      }
    }
    if (master) setMaster(master.state || 'off');

    var expanded = false;
    var opened = false;
    function setExpanded(value) {
      if (!withExpand) return;
      expanded = !!value;
      expandBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
      body.hidden = !expanded;
      if (expanded && !opened) {
        opened = true;
        if (typeof opts.onFirstExpand === 'function') opts.onFirstExpand(body);
      }
    }
    function onExpandClick() {
      setExpanded(!expanded);
      if (typeof opts.onExpand === 'function') opts.onExpand(expanded);
    }
    if (withExpand) expandBtn.addEventListener('click', onExpandClick);
    if (opts.expanded) setExpanded(true);

    return {
      el: root,
      body: body,
      // The title span, the expand button and the master's App.ui.toggle controller (null
      // without a master), for hosts that patch them (HAT fix pass 1).
      nameEl: nameEl,
      expandBtn: expandBtn,
      toggle: toggle,
      setCount: function (text) {
        if (!countEl) {
          countEl = util.el('span', { className: 'ui-group-tile-chip' });
          var name = row.querySelector('.ui-group-tile-name');
          row.insertBefore(countEl, name.nextSibling);
        }
        countEl.textContent = text === null || text === undefined ? '' : String(text);
        countEl.hidden = !countEl.textContent;
      },
      setMaster: setMaster,
      setToolCount: setToolCount,
      setExpanded: setExpanded,
      isExpanded: function () { return expanded; },
      setSubtitle: setSubtitle,
      destroy: function () {
        if (withExpand) expandBtn.removeEventListener('click', onExpandClick);
      }
    };
  };

  function truncate(text) {
    return text.length > 100 ? text.slice(0, 100) + '…' : text;
  }

  // App.ui.toolRow(opts) -> {el, input, body, setChecked(bool), setDisabled(bool),
  // setOpen(bool), destroy()} (M31 F2 L4, flight DD3). One tool in a group:
  // a checkbox, the mono name and " — " plus a description, optionally
  // with an expandable body.
  //   name, description (shown cut to 100 characters plus an ellipsis, the full
  //   text in its title), checked, disabled, strike, onChange(checked), title,
  //   testid (on the checkbox), dataset (on the root), inputDataset (on the
  //   checkbox input, M31 F2 L07b), note (a string, or
  //   {text, testid} -- an extra description line; the testid defaults to
  //   "time-tool-note"), disclosure {label ('Overrides'), onFirstOpen(body),
  //   open}.
  //   Without disclosure (or when disabled) el is label.ui-tool-row: the
  //   input.checkbox-primary and span.ui-tool-row-text. With disclosure el is
  //   details.ui-tool-row whose summary holds the label face and
  //   span.ui-tool-row-affordance ("Overrides" and a chevron), then
  //   div.ui-tool-row-body; onFirstOpen(body) fires once, from the details
  //   toggle event. A click or Space on the checkbox toggles only the checkbox
  //   (an interactive control inside a summary does not toggle the details:
  //   the HTML rule, no stopPropagation); Enter on the summary or a click on
  //   the affordance toggles only the details. A disabled row has no disclosure
  //   or affordance, the title "Disabled by operator" and the strike-through.
  App.ui.toolRow = function (opts) {
    opts = opts || {};
    if (!opts.name) throw new Error('App.ui.toolRow: name is required');
    var util = App.ui.util;
    var disabled = !!opts.disabled;
    var disclosure = !disabled && opts.disclosure ? opts.disclosure : null;

    var input = util.el('input', { type: 'checkbox', className: 'checkbox-primary' });
    if (opts.checked) input.checked = true;
    if (disabled) input.disabled = true;
    util.applyDataset(input, opts.inputDataset);
    if (opts.testid) input.setAttribute('data-testid', opts.testid);
    if (typeof opts.onChange === 'function') {
      input.addEventListener('change', function () { opts.onChange(input.checked); });
    }

    var nameEl = util.el('span', {
      className: 'ui-tool-row-name' + (opts.strike || disabled ? ' ui-tool-row-name--strike' : ''),
      text: opts.name
    });
    var textEl = util.el('span', { className: 'ui-tool-row-text' }, [nameEl]);
    if (opts.description) {
      textEl.appendChild(util.el('span', {
        className: 'ui-tool-row-desc',
        title: opts.description,
        text: ' — ' + truncate(opts.description)
      }));
    }
    if (opts.note) {
      var note = typeof opts.note === 'string' ? { text: opts.note } : opts.note;
      textEl.appendChild(util.el('span', {
        className: 'ui-tool-row-desc',
        'data-testid': note.testid || NOTE_TESTID_DEFAULT,
        text: note.text
      }));
    }

    var rootClass = 'ui-tool-row' + (disabled ? ' is-disabled' : '');
    var root;
    var body = null;
    var onToggle = null;
    if (disclosure) {
      root = util.el('details', { className: rootClass + ' ui-tool-row--disclosure' });
      var face = util.el('label', { className: 'ui-tool-row-face' }, [input, textEl]);
      var affordance = util.el('span', { className: 'ui-tool-row-affordance' }, [
        util.el('span', { text: disclosure.label || 'Overrides' }),
        util.el('span', { className: 'ui-tool-row-chevron', 'aria-hidden': 'true', text: '▸' })
      ]);
      root.appendChild(util.el('summary', { className: 'ui-tool-row-summary' }, [face, affordance]));
      body = util.el('div', { className: 'ui-tool-row-body' });
      root.appendChild(body);
      var opened = false;
      onToggle = function () {
        if (root.open && !opened) {
          opened = true;
          if (typeof disclosure.onFirstOpen === 'function') disclosure.onFirstOpen(body);
        }
      };
      root.addEventListener('toggle', onToggle);
      if (disclosure.open) root.open = true;
    } else {
      root = util.el('label', { className: rootClass + ' ui-tool-row--plain' }, [input, textEl]);
    }
    util.applyDataset(root, opts.dataset);
    if (disabled) {
      root.title = opts.title || 'Disabled by operator';
    } else if (opts.title) {
      root.title = opts.title;
    }

    return {
      el: root,
      input: input,
      body: body,
      setChecked: function (value) { input.checked = !!value; },
      setDisabled: function (value) {
        input.disabled = !!value;
        root.classList.toggle('is-disabled', !!value);
      },
      setOpen: function (value) {
        if (disclosure) root.open = !!value;
      },
      destroy: function () {
        if (onToggle) root.removeEventListener('toggle', onToggle);
      }
    };
  };

  // App.ui.toolTile(opts) -> {el, key, link, toggle, setSelected(bool),
  // setChecked(bool), setDisabled(bool), setDescription(text)} (M31 F4 L04e, flight
  // DD4/DD12). The Built-in tools card: a linked name, an optional badge, a
  // description and an enable switch.
  //   key (the tool name; defaults to name), name (required), href (the item
  //   link), selected, badge {text, kind, title} (an App.ui.badge), description,
  //   toggle {label (required: the switch's accessible name, supplied by the
  //   caller), checked, disabled, onChange(checked), testid (on the native
  //   input), dataset (on the toggle's native input)}, testid, dataset (on the
  //   root).
  //   el is div.ui-tool-tile[role=listitem] (plus the legacy entity-tile tool-tile
  //   until leg 06's handover): div.ui-tool-tile-row (a.ui-tool-tile-link, the
  //   name, aria-current="page" when selected, then the badge), then
  //   span.ui-tool-tile-desc (clamped to two lines) and the App.ui.toggle in the
  //   flow below, end-aligned. A selected tile also carries ui-tool-tile--selected
  //   (and the legacy active).
  App.ui.toolTile = function (opts) {
    opts = opts || {};
    if (!opts.name) throw new Error('App.ui.toolTile: name is required');
    var tg = opts.toggle || {};
    if (!tg.label) throw new Error('App.ui.toolTile: toggle.label is required');
    var util = App.ui.util;
    var selected = !!opts.selected;

    var root = util.el('div', { className: 'ui-tool-tile entity-tile tool-tile', role: 'listitem' });
    util.applyDataset(root, opts.dataset);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    var row = util.el('div', { className: 'ui-tool-tile-row tile-title-row' });
    var link = util.el('a', {
      className: 'ui-tool-tile-link entity-tile-name tool-tile-link',
      text: opts.name
    });
    if (opts.href) link.setAttribute('href', opts.href);
    row.appendChild(link);
    if (opts.badge) {
      var badge = App.ui.badge(opts.badge);
      badge.classList.add('ui-tool-tile-badge');
      row.appendChild(badge);
    }
    root.appendChild(row);

    var desc = util.el('span', {
      className: 'ui-tool-tile-desc entity-tile-description',
      text: opts.description || ''
    });
    // The two-line clamp hides the rest: the full text is the tooltip.
    function setDescriptionTitle(text) {
      if (text) desc.title = text; else desc.removeAttribute('title');
    }
    setDescriptionTitle(opts.description);
    root.appendChild(desc);

    var toggle = App.ui.toggle({
      label: tg.label,
      labelHidden: true,
      checked: !!tg.checked,
      disabled: !!tg.disabled,
      dataset: tg.dataset,
      testid: tg.testid,
      onChange: tg.onChange
    });
    toggle.el.classList.add('ui-tool-tile-toggle');
    root.appendChild(toggle.el);

    function setSelected(value) {
      selected = !!value;
      root.classList.toggle('ui-tool-tile--selected', selected);
      root.classList.toggle('active', selected);
      if (selected) {
        link.setAttribute('aria-current', 'page');
      } else {
        link.removeAttribute('aria-current');
      }
    }
    setSelected(selected);

    return {
      el: root,
      key: opts.key !== undefined ? opts.key : opts.name,
      link: link,
      toggle: toggle,
      setSelected: setSelected,
      setChecked: function (value) { toggle.setChecked(!!value); },
      setDisabled: function (value) { toggle.setDisabled(!!value); },
      setDescription: function (text) {
        desc.textContent = text || '';
        setDescriptionTitle(text);
      }
    };
  };

  // App.ui.toolTile.grid({label, testid}) -> {el, sync(tiles)}. The tile grid: a
  // div.ui-tool-tile-grid[role=list] (plus the legacy entity-tile-grid). sync(tiles)
  // makes the grid's children exactly the given toolTile controllers, in order,
  // through App.ui.util.syncChildren (a kept tile is never re-inserted, so
  // its state survives); duplicate keys throw. A focused element inside the grid
  // is given focus back if a move blurred it.
  App.ui.toolTile.grid = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var el = util.el('div', {
      className: 'ui-tool-tile-grid entity-tile-grid',
      role: 'list',
      'aria-label': opts.label || null
    });
    if (opts.testid) el.setAttribute('data-testid', opts.testid);
    return {
      el: el,
      sync: function (tiles) {
        tiles = tiles || [];
        var seen = Object.create(null);
        var nodes = [];
        for (var i = 0; i < tiles.length; i++) {
          if (seen[tiles[i].key]) throw new Error('App.ui.toolTile.grid: duplicate key "' + tiles[i].key + '"');
          seen[tiles[i].key] = true;
          nodes.push(tiles[i].el);
        }
        var focused = document.activeElement;
        if (!focused || !el.contains(focused)) focused = null;
        util.syncChildren(el, nodes);
        if (focused && document.activeElement !== focused && focused.isConnected) focused.focus();
      }
    };
  };
})();
