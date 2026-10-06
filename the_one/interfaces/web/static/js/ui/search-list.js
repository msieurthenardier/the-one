(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.searchList(opts) -> controller {el, input, refresh(), getActive(),
  // setActive(id), destroy()}.  A combobox input over a grouped listbox
  // (M25 F4 L1, DD14, A10): the agent picker's and the jump-to palette's list.
  //   label (required): the input's visually hidden label; also the listbox's
  //     accessible name.
  //   placeholder: the input's placeholder.
  //   source(query) (required): called synchronously with the input's raw
  //     value on every input event and on refresh(); returns the groups
  //     [{id, label, items: [item]}].  A group with no items is dropped (no
  //     caption without options); a group with no label renders its options
  //     with no caption and no group element.
  //   item: {id, label, description, meta, metaMono, lead, testid, dataset}.
  //     lead is a caller-built node placed before the text in an aria-hidden
  //     wrapper; meta is right-aligned (mono when metaMono); dataset sets
  //     data-* on the row; the per-item test id option lands on the row and
  //     wins over rowTestid.  Item ids need not be unique across groups (the
  //     picker's "All agents" repeats "Recently used"): every option element
  //     gets its own generated id.
  //   emptyText(query): the empty state's title when source returns no
  //     options (called with the same raw value); default "No matches".
  //   onPick(item): Enter on the active option, or a click on an option.
  //   testid (the root), inputTestid (the input), rowTestid (every row
  //     without its own test id).
  //
  // ARIA (the APG combobox with a listbox popup that is always shown): the
  // input is role=combobox with aria-autocomplete=list, aria-expanded=true,
  // aria-controls (the listbox) and aria-activedescendant (the active option;
  // removed when there is none).  The listbox holds role=group elements, each
  // labelled by its visible caption (role=presentation, never an option), and
  // role=option rows; only the active row carries aria-selected="true".
  // Rows are never focusable: focus stays in the input.
  //
  // Keys (on the input only): ArrowDown / ArrowUp move the active option
  // across groups, clamped at the ends (no wrap); Enter picks the active
  // option (preventDefault) and does nothing with no options.  Home and End
  // are NOT intercepted (they move the caret, per the APG combobox pattern);
  // Escape is NOT handled (the containing modal owns it).  Keys during IME
  // composition (isComposing, or keyCode 229) are ignored.  After every
  // source call the first option is active.  A pointermove over a row makes
  // it active and a click picks it; a mousedown on the listbox is prevented so
  // focus never leaves the input.  Keyboard and source activation scroll the
  // active option into view inside the listbox only (block 'nearest';
  // never an ancestor); pointer activation never scrolls (the row is under
  // the pointer).
  //
  // With no options the listbox is hidden, aria-expanded is "false" and an
  // App.ui.emptyState shows emptyText(query); a persistent visually hidden
  // role=status region carries the same text (a hidden-toggled element is not
  // a reliable live region). With options and a non-blank query the region
  // reads "1 result" / "{n} results"; with a blank query it is empty.
  // Built with DOM APIs only; every listener is on the input or the listbox
  // (none on document or window) and destroy() removes them.
  App.ui.searchList = function (opts) {
    opts = opts || {};
    if (!opts.label) throw new Error('App.ui.searchList: label is required');
    if (typeof opts.source !== 'function') {
      throw new Error('App.ui.searchList: source must be a function');
    }
    var util = App.ui.util;
    var listId = util.uid('sl-list');
    var flat = []; // [{item, el, first, caption}] in display order
    var activeIndex = -1;

    var input = App.ui.textInput({ placeholder: opts.placeholder, autocomplete: 'off' });
    input.setAttribute('role', 'combobox');
    input.setAttribute('aria-autocomplete', 'list');
    input.setAttribute('aria-expanded', 'true');
    input.setAttribute('aria-controls', listId);
    input.setAttribute('spellcheck', 'false');
    if (opts.inputTestid) input.setAttribute('data-testid', opts.inputTestid);
    var field = App.ui.field({ label: opts.label, labelHidden: true, control: input });
    field.el.classList.add('ui-search-list-field');

    var listbox = util.el('div', {
      className: 'ui-search-list-listbox',
      role: 'listbox',
      id: listId,
      'aria-label': opts.label
    });
    var empty = App.ui.emptyState({ title: 'No matches' });
    var emptyTitle = empty.querySelector('.ui-empty-title');
    empty.classList.add('ui-search-list-empty');
    empty.hidden = true;
    var status = util.el('div', { className: 'visually-hidden' });
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    var root = util.el('div', { className: 'ui-search-list' }, [field.el, listbox, empty, status]);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    function buildOption(item) {
      var row = util.el('div', { className: 'ui-search-list-row', role: 'option', id: util.uid('sl-opt') });
      if (item.lead) {
        row.appendChild(util.el('span', { className: 'ui-search-list-lead', 'aria-hidden': 'true' }, [item.lead]));
      }
      var text = util.el('span', { className: 'ui-search-list-text' }, [
        util.el('span', { className: 'ui-search-list-label', text: String(item.label) })
      ]);
      if (item.description) {
        text.appendChild(util.el('span', { className: 'ui-search-list-description', text: String(item.description) }));
      }
      row.appendChild(text);
      if (item.meta !== undefined && item.meta !== null && item.meta !== '') {
        row.appendChild(util.el('span', {
          className: item.metaMono ? 'ui-search-list-meta ui-search-list-meta-mono' : 'ui-search-list-meta',
          text: String(item.meta)
        }));
      }
      if (item.dataset) {
        for (var k in item.dataset) {
          if (Object.prototype.hasOwnProperty.call(item.dataset, k)) row.dataset[k] = item.dataset[k];
        }
      }
      var rowTestid = item.testid || opts.rowTestid;
      if (rowTestid) row.setAttribute('data-testid', rowTestid);
      return row;
    }

    // Keep the active option visible inside the listbox, never scrolling an
    // ancestor (scrollIntoView would).  The first option of a group brings
    // its caption into view with it.
    function scrollActiveIntoView() {
      if (activeIndex < 0 || listbox.hidden) return;
      var entry = flat[activeIndex];
      var box = listbox.getBoundingClientRect();
      var viewTop = box.top + listbox.clientTop;
      var viewBottom = viewTop + listbox.clientHeight;
      var rowBox = entry.el.getBoundingClientRect();
      var top = entry.first && entry.caption ? entry.caption.getBoundingClientRect().top : rowBox.top;
      if (top < viewTop) {
        listbox.scrollTop -= viewTop - top;
      } else if (rowBox.bottom > viewBottom) {
        listbox.scrollTop += rowBox.bottom - viewBottom;
      }
    }

    function setActiveIndex(index, scroll) {
      if (activeIndex >= 0 && flat[activeIndex] && index !== activeIndex) {
        flat[activeIndex].el.removeAttribute('aria-selected');
      }
      activeIndex = index;
      if (index < 0 || !flat[index]) {
        activeIndex = -1;
        input.removeAttribute('aria-activedescendant');
        return;
      }
      flat[index].el.setAttribute('aria-selected', 'true');
      input.setAttribute('aria-activedescendant', flat[index].el.id);
      if (scroll) scrollActiveIntoView();
    }

    // Validate source's groups BEFORE any DOM is touched, so a bad item
    // throws with the previous options still rendered.
    function validate(groups) {
      if (!Array.isArray(groups)) throw new Error('App.ui.searchList: source must return an array of groups');
      for (var g = 0; g < groups.length; g++) {
        var items = (groups[g] && groups[g].items) || [];
        if (!Array.isArray(items)) throw new Error('App.ui.searchList: group items must be an array');
        for (var i = 0; i < items.length; i++) {
          var item = items[i];
          if (!item || item.id === undefined || item.id === null || item.id === '') {
            throw new Error('App.ui.searchList item: id required');
          }
          if (item.lead !== undefined && item.lead !== null && !item.lead.nodeType) {
            throw new Error('App.ui.searchList item ' + item.id + ': lead must be a node');
          }
        }
      }
      return groups;
    }

    function render() {
      var query = input.value;
      var groups = validate(opts.source(query) || []);
      listbox.textContent = '';
      flat = [];
      activeIndex = -1;
      for (var g = 0; g < groups.length; g++) {
        var group = groups[g] || {};
        var items = group.items || [];
        if (!items.length) continue;
        var host = listbox;
        var caption = null;
        if (group.label) {
          var capId = util.uid('sl-cap');
          caption = util.el('div', {
            className: 'ui-search-list-caption',
            role: 'presentation',
            id: capId,
            text: String(group.label)
          });
          host = util.el('div', { className: 'ui-search-list-group', role: 'group', 'aria-labelledby': capId }, [caption]);
          listbox.appendChild(host);
        }
        for (var i = 0; i < items.length; i++) {
          var row = buildOption(items[i]);
          host.appendChild(row);
          flat.push({ item: items[i], el: row, first: i === 0, caption: caption });
        }
      }
      var none = flat.length === 0;
      listbox.hidden = none;
      empty.hidden = !none;
      var emptyText = '';
      if (none) {
        emptyText = (typeof opts.emptyText === 'function' ? opts.emptyText(query) : '') || 'No matches';
        if (emptyTitle.textContent !== emptyText) emptyTitle.textContent = emptyText;
      }
      // Combobox state follows the listbox; the status region announces the
      // result count while filtering (as list-pane does), the empty text for
      // none, and stays empty on the unfiltered first open.
      input.setAttribute('aria-expanded', none ? 'false' : 'true');
      var statusText = emptyText;
      if (!none && query.trim()) statusText = flat.length === 1 ? '1 result' : flat.length + ' results';
      if (status.textContent !== statusText) status.textContent = statusText;
      listbox.scrollTop = 0;
      setActiveIndex(none ? -1 : 0, false);
    }

    function pick(index) {
      if (index < 0 || !flat[index]) return;
      if (typeof opts.onPick === 'function') opts.onPick(flat[index].item);
    }

    function indexOfRow(node) {
      var row = node && node.closest ? node.closest('.ui-search-list-row') : null;
      if (!row) return -1;
      for (var i = 0; i < flat.length; i++) {
        if (flat[i].el === row) return i;
      }
      return -1;
    }

    function onInput() {
      render();
    }

    function onKeydown(e) {
      if (e.isComposing || e.keyCode === 229) return;
      if (e.ctrlKey || e.altKey || e.metaKey) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!flat.length) return;
        var next = activeIndex + (e.key === 'ArrowDown' ? 1 : -1);
        if (next < 0) next = 0;
        if (next > flat.length - 1) next = flat.length - 1;
        setActiveIndex(next, true);
      } else if (e.key === 'Enter') {
        if (activeIndex < 0) return;
        e.preventDefault();
        pick(activeIndex);
      }
    }

    function onPointermove(e) {
      var index = indexOfRow(e.target);
      if (index !== -1 && index !== activeIndex) setActiveIndex(index, false);
    }

    function onClick(e) {
      var index = indexOfRow(e.target);
      if (index === -1) return;
      setActiveIndex(index, false);
      pick(index);
    }

    // Keep focus in the input on a press inside the listbox (a click on a
    // non-focusable row would otherwise move focus to a focusable ancestor).
    function onMousedown(e) {
      e.preventDefault();
    }

    input.addEventListener('input', onInput);
    input.addEventListener('keydown', onKeydown);
    listbox.addEventListener('pointermove', onPointermove);
    listbox.addEventListener('click', onClick);
    listbox.addEventListener('mousedown', onMousedown);

    function getActive() {
      return activeIndex >= 0 && flat[activeIndex] ? flat[activeIndex].item : null;
    }

    // Activate the first option whose item id is `id` (an unknown id is a
    // no-op) and scroll it into view inside the listbox.
    function setActive(id) {
      for (var i = 0; i < flat.length; i++) {
        if (flat[i].item.id === id) {
          setActiveIndex(i, true);
          return;
        }
      }
    }

    function destroy() {
      input.removeEventListener('input', onInput);
      input.removeEventListener('keydown', onKeydown);
      listbox.removeEventListener('pointermove', onPointermove);
      listbox.removeEventListener('click', onClick);
      listbox.removeEventListener('mousedown', onMousedown);
      listbox.textContent = '';
      flat = [];
      activeIndex = -1;
      input.removeAttribute('aria-activedescendant');
    }

    render();
    return {
      el: root,
      input: input,
      refresh: render,
      getActive: getActive,
      setActive: setActive,
      destroy: destroy
    };
  };
})();
