(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var MODES = ['push', 'overlay'];

  // App.ui.drawer(opts) -> {el, open(opener), close(), toggle(opener),
  // isOpen(), setMode('push'|'overlay'), destroy()}  (M25 F4 L6, DD7, DD14)
  //
  // A NON-modal side panel: an <aside> holding a header (.ui-drawer-header,
  // the heading), a scrolling body (.ui-drawer-body) and an optional footer
  // (.ui-drawer-footer). It is shown and hidden with the `hidden` attribute,
  // never removed, so a toggle's aria-controls always resolves.
  //
  // opts:
  //   label      the <aside>'s aria-label (its landmark name); required
  //   heading    text (an h2.ui-drawer-title, set with textContent) or a Node
  //              (placed in the header as given)
  //   body       a Node, placed in the body
  //   footer     a Node, placed in the footer (no footer without it)
  //   el         an existing <aside> to fill (a static shell slot): its
  //              children are replaced and its id kept; without it the
  //              factory creates the <aside>
  //   testid     placed on the <aside>
  //   onOpenChange(open)  after every change of the open state, however it
  //              was made (open, close, toggle, Escape)
  //
  // Behaviour:
  //   - Built closed (`hidden`) in push mode. open() never moves focus (a
  //     non-modal panel: the opener keeps it).
  //   - open(opener) records the opener; with no argument the last recorded
  //     one stays. close() returns focus to that opener ONLY when focus is
  //     inside the drawer at that moment (so hiding it never drops focus to
  //     <body>, and a close from elsewhere never steals focus).
  //   - Escape while focus is inside closes it (preventDefault and
  //     stopPropagation; ignored while an IME composes), so focus returns to
  //     the opener (the Flight 1 DD8 rule).
  //   - setMode('push') is a flex sibling; setMode('overlay') is absolutely
  //     positioned over the right of its positioned container, with the modal
  //     shadow, no scrim and no outside-click close. The CSS is
  //     .ui-drawer--push / .ui-drawer--overlay; data-mode mirrors it.
  //   - The header and footer wrappers honour `hidden` (a caller may hide the
  //     footer when its content does not apply: the chat drawer with no
  //     settings link).
  //   - One keydown listener on the <aside>; no document or window listener.
  //     destroy() removes it, empties the drawer and hides it; it never
  //     removes the element (the caller owns its placement).
  App.ui.drawer = function (opts) {
    opts = opts || {};
    if (!opts.label) throw new Error('App.ui.drawer: label is required');
    if (opts.el && opts.el.tagName !== 'ASIDE') throw new Error('App.ui.drawer: el must be an <aside>');
    if (opts.body !== undefined && opts.body !== null && !opts.body.nodeType) {
      throw new Error('App.ui.drawer: body must be a Node');
    }
    if (opts.footer !== undefined && opts.footer !== null && !opts.footer.nodeType) {
      throw new Error('App.ui.drawer: footer must be a Node');
    }
    var util = App.ui.util;
    var root = opts.el || util.el('aside');
    var opener = null;
    var mode = null;

    root.textContent = '';
    root.classList.add('ui-drawer');
    root.setAttribute('aria-label', opts.label);
    if (opts.testid) root.setAttribute('data-testid', opts.testid);

    var header = util.el('div', { className: 'ui-drawer-header' });
    if (opts.heading !== undefined && opts.heading !== null) {
      if (opts.heading.nodeType) {
        header.appendChild(opts.heading);
      } else {
        header.appendChild(util.el('h2', { className: 'ui-drawer-title', text: String(opts.heading) }));
      }
    }
    root.appendChild(header);
    var body = util.el('div', { className: 'ui-drawer-body' });
    if (opts.body) body.appendChild(opts.body);
    root.appendChild(body);
    if (opts.footer) root.appendChild(util.el('div', { className: 'ui-drawer-footer' }, [opts.footer]));
    root.hidden = true;

    function notify() {
      if (typeof opts.onOpenChange === 'function') opts.onOpenChange(!root.hidden);
    }

    function isOpen() {
      return !root.hidden;
    }

    function open(by) {
      if (by && by.nodeType) opener = by;
      if (!root.hidden) return;
      root.hidden = false;
      notify();
    }

    function close() {
      if (root.hidden) return;
      var active = document.activeElement;
      // contains() is true for the <aside> itself too.
      if (active && root.contains(active)) {
        if (opener && opener.isConnected && typeof opener.focus === 'function') {
          try {
            opener.focus();
          } catch (e) {
            /* ignore */
          }
        }
      }
      root.hidden = true;
      notify();
    }

    function toggle(by) {
      if (root.hidden) open(by);
      else close();
    }

    function setMode(next) {
      if (MODES.indexOf(next) === -1) throw new Error('App.ui.drawer: unknown mode "' + next + '"');
      if (next === mode) return;
      mode = next;
      root.classList.toggle('ui-drawer--push', next === 'push');
      root.classList.toggle('ui-drawer--overlay', next === 'overlay');
      root.setAttribute('data-mode', next);
    }

    function onKeydown(e) {
      if (e.key !== 'Escape' || e.defaultPrevented || root.hidden) return;
      if (e.isComposing || e.keyCode === 229) return;
      e.preventDefault();
      e.stopPropagation();
      close();
    }
    root.addEventListener('keydown', onKeydown);

    function destroy() {
      root.removeEventListener('keydown', onKeydown);
      root.textContent = '';
      root.hidden = true;
      opener = null;
    }

    setMode('push');
    return {
      el: root,
      open: open,
      close: close,
      toggle: toggle,
      isOpen: isOpen,
      setMode: setMode,
      destroy: destroy
    };
  };
})();
