(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var NOTE_TESTID_DEFAULT = 'time-tool-note';

  // App.ui.groupTile(opts) -> {el, body, setCount(text), setMaster(state),
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

    var expandBtn = util.el('button', {
      type: 'button',
      className: 'ui-group-tile-expand',
      'aria-expanded': 'false',
      // The tile's name joins the button's name through the description, so "3 tools"
      // is not the whole of what a screen reader hears (SC 2.4.6, 4.1.2).
      'aria-describedby': nameEl.id,
      'data-testid': opts.expandTestid
    });
    var labelEl = util.el('span', { className: 'ui-group-tile-expand-label' });
    var chevron = util.el('span', {
      className: 'ui-group-tile-chevron',
      'aria-hidden': 'true',
      text: '▸'
    });
    expandBtn.appendChild(labelEl);
    expandBtn.appendChild(chevron);
    root.appendChild(expandBtn);

    var body = util.el('div', {
      className: 'ui-group-tile-body',
      hidden: true,
      'data-testid': opts.bodyTestid
    });
    root.appendChild(body);

    function setToolCount(value) {
      labelEl.textContent = '';
      if (typeof value === 'number') {
        labelEl.appendChild(util.el('strong', { text: String(value) }));
        labelEl.appendChild(document.createTextNode(value === 1 ? ' tool' : ' tools'));
      } else {
        labelEl.textContent = value === null || value === undefined ? 'Tools' : String(value);
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
    expandBtn.addEventListener('click', onExpandClick);
    if (opts.expanded) setExpanded(true);

    return {
      el: root,
      body: body,
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
        expandBtn.removeEventListener('click', onExpandClick);
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
})();
