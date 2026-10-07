(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // The one menu that is open right now (module scope), so opening a second
  // closes the first. Cleared by close() and by a detached-host cleanup.
  var openMenu = null;
  var ITEM_SELECTOR = '[role="menuitem"]:not([aria-disabled="true"])';

  // App.ui.menu(opts) -> controller {el, trigger, popup, open(focus),
  //   close(restoreFocus), isOpen(), destroy()}.  WAI-ARIA menu button.
  //   trigger: options for App.ui.button (iconOnly + ariaLabel allowed); its
  //     test id option lands on the trigger button.
  //   items: [{label, onSelect, icon, danger, disabled, ...}] (required, not
  //     empty); an item's test id option lands on its menuitem.
  //   align: 'start' (default) | 'end'. The popup root takes the test id option.
  //   The popup is a DOM descendant of el (no portal), opens downward, and
  //   does no edge flipping. Document listeners exist only while it is open.
  App.ui.menu = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var items = opts.items;
    if (!items || !items.length) throw new Error('App.ui.menu: items must not be empty');
    var align = opts.align === undefined ? 'start' : opts.align;
    if (align !== 'start' && align !== 'end') {
      throw new Error('App.ui.menu: unknown align "' + align + '"');
    }
    var i;
    for (i = 0; i < items.length; i++) {
      if (!items[i] || !items[i].label) throw new Error('App.ui.menu: every item needs a label');
      if (typeof items[i].onSelect !== 'function') {
        throw new Error('App.ui.menu: every item needs an onSelect function');
      }
    }

    var triggerOpts = opts.trigger || {};
    var trigger = App.ui.button(triggerOpts);
    if (!trigger.id) trigger.id = util.uid('menu-trigger');
    var popupId = util.uid('menu');
    trigger.setAttribute('aria-haspopup', 'menu');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', popupId);

    var popup = util.el('div', {
      role: 'menu',
      id: popupId,
      className: 'ui-menu ui-menu-align-' + align,
      tabindex: '-1',
      hidden: true
    });
    if (triggerOpts.iconOnly) {
      popup.setAttribute('aria-label', triggerOpts.ariaLabel);
    } else {
      popup.setAttribute('aria-labelledby', trigger.id);
    }
    if (opts.testid) popup.setAttribute('data-testid', opts.testid);

    var el = util.el('div', { className: 'ui-menu-wrap' }, [trigger, popup]);
    var isOpen = false;
    var ctl;

    function enabledItems() {
      return Array.prototype.slice.call(popup.querySelectorAll(ITEM_SELECTOR));
    }

    function onDocPointerdown(e) {
      if (!el.isConnected) {
        // Host was wiped without destroy(): drop the listener, touch nothing.
        document.removeEventListener('pointerdown', onDocPointerdown, true);
        isOpen = false;
        if (openMenu === ctl) openMenu = null;
        return;
      }
      if (!el.contains(e.target)) close(false);
    }

    function close(restoreFocus) {
      if (!isOpen) return;
      isOpen = false;
      document.removeEventListener('pointerdown', onDocPointerdown, true);
      if (openMenu === ctl) openMenu = null;
      if (!el.isConnected) return;
      popup.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      if (restoreFocus) trigger.focus();
    }

    function open(focus) {
      if (isOpen || trigger.disabled) return;
      if (openMenu && openMenu !== ctl) openMenu.close(false);
      isOpen = true;
      openMenu = ctl;
      popup.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      document.addEventListener('pointerdown', onDocPointerdown, true);
      var enabled = enabledItems();
      if (!enabled.length) {
        popup.focus();
      } else {
        enabled[focus === 'last' ? enabled.length - 1 : 0].focus();
      }
    }

    function activate(item, node) {
      if (node.getAttribute('aria-disabled') === 'true') return;
      close(true);
      item.onSelect(item);
    }

    items.forEach(function (item) {
      var children = [];
      if (item.icon) children.push(util.el('span', { className: 'ui-menu-item-icon' }, [util.icon(item.icon)]));
      children.push(util.el('span', { className: 'ui-menu-item-label', text: String(item.label) }));
      var node = util.el(
        'button',
        {
          type: 'button',
          role: 'menuitem',
          tabindex: '-1',
          className: item.danger ? 'ui-menu-item ui-menu-item-danger' : 'ui-menu-item',
          'aria-disabled': item.disabled ? 'true' : null
        },
        children
      );
      if (item.testid) node.setAttribute('data-testid', item.testid);
      node.addEventListener('click', function () {
        activate(item, node);
      });
      popup.appendChild(node);
    });

    trigger.addEventListener('click', function () {
      if (isOpen) close(true);
      else open('first');
    });
    trigger.addEventListener('keydown', function (e) {
      if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (isOpen) close(false);
        open(e.key === 'ArrowUp' ? 'last' : 'first');
      }
    });

    // Arrow/Home/End on the popup. rovingFocus writes tabindex="0" on the item it
    // focuses, always BEFORE calling .focus(); resetting on the popup's focusin
    // (fired synchronously by that focus move) keeps every item out of the tab
    // order without depending on keydown listener registration order.
    var unbindRoving = util.rovingFocus(popup, ITEM_SELECTOR, { wrap: true });
    function resetTabindex() {
      var all = popup.querySelectorAll('[role="menuitem"]');
      for (var k = 0; k < all.length; k++) all[k].setAttribute('tabindex', '-1');
    }
    popup.addEventListener('focusin', resetTabindex);
    // Keep focus where it is on a mouse press inside the popup (WebKit does not
    // focus a pressed button, which would otherwise blur the menu mid-click).
    popup.addEventListener('mousedown', function (e) {
      e.preventDefault();
    });

    function onWrapKeydown(e) {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        close(true);
      } else if (e.key === 'Tab') {
        // No preventDefault: default Tab navigation continues from the trigger.
        close(false);
        trigger.focus();
      }
    }
    function onWrapFocusout(e) {
      if (!isOpen) return;
      var next = e.relatedTarget;
      // A null relatedTarget (window blur, pressed non-focusable area) is left to
      // the document pointerdown handler; a real move outside el closes.
      if (next && !el.contains(next)) close(false);
    }
    el.addEventListener('keydown', onWrapKeydown);
    el.addEventListener('focusout', onWrapFocusout);

    ctl = {
      el: el,
      trigger: trigger,
      popup: popup,
      open: open,
      close: close,
      isOpen: function () {
        return isOpen;
      },
      destroy: function () {
        close(false);
        unbindRoving();
        el.removeEventListener('keydown', onWrapKeydown);
        el.removeEventListener('focusout', onWrapFocusout);
      }
    };
    return ctl;
  };
})();
