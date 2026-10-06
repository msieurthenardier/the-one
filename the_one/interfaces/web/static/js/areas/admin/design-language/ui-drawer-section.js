(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};
  window.App.admin.designLanguage = window.App.admin.designLanguage || {};

  // App.ui.drawer (M25 F4 L6, DD7, DD14): the non-modal side panel the chat
  // area's agent drawer is built on. Per theme pane, two frames stand in for
  // the app shell row (position: relative, a flex row; the drawer's width is
  // narrowed to fit the pane through the frame's --drawer-w):
  //   push     a flex sibling of the frame's main area, open at first;
  //   overlay  absolutely over the main area's right, with the modal shadow,
  //            closed at first.
  // Each frame's ghost icon-only toggle (panel-right) carries aria-pressed
  // and aria-controls the drawer; Escape inside a drawer closes it and focus
  // returns to its toggle. Test ids are suffixed per pane (the demo is built
  // twice): ui-demo-drawer-{theme}-{push|overlay} on the <aside>,
  // ui-demo-drawer-toggle-{theme}-{push|overlay} on the toggle.
  var el = App.ui.util.el;

  function frame(pane, theme, mode) {
    var toggle = null;
    var body = el('div', null, [
      el('p', { className: 'design-language-ui-drawer-text', text: 'A short description of the agent.' }),
      el('dl', { className: 'design-language-ui-drawer-facts' }, [
        el('dt', { text: 'Model' }),
        el('dd', { text: 'llama3.1:8b' }),
        el('dt', { text: 'Chats' }),
        el('dd', { text: '3' })
      ])
    ]);
    var drawer = App.ui.drawer({
      label: 'Drawer demo, ' + mode + ' (' + theme + ')',
      heading: 'Research assistant',
      body: body,
      footer: App.ui.button({ variant: 'secondary', icon: 'settings', label: 'Open settings' }),
      testid: 'ui-demo-drawer-' + theme + '-' + mode,
      onOpenChange: function (open) {
        toggle.setAttribute('aria-pressed', open ? 'true' : 'false');
      }
    });
    drawer.el.id = App.ui.util.uid('drawer-demo');
    drawer.setMode(mode);
    toggle = App.ui.button({
      variant: 'ghost',
      icon: 'panel-right',
      iconOnly: true,
      ariaLabel: 'Show the ' + mode + ' demo panel (' + theme + ')',
      testid: 'ui-demo-drawer-toggle-' + theme + '-' + mode,
      onClick: function () {
        drawer.toggle(toggle);
      }
    });
    toggle.setAttribute('aria-controls', drawer.el.id);
    toggle.setAttribute('aria-pressed', 'false');
    var main = el('div', { className: 'design-language-ui-drawer-main' }, [
      toggle,
      el('span', { className: 'design-language-caption', text: mode + ': the chat pane stands here' })
    ]);
    if (mode === 'push') drawer.open(toggle);
    pane.appendChild(el('div', { className: 'design-language-ui-drawer-frame' }, [main, drawer.el]));
  }

  function render(host) {
    var d = App.admin.designLanguage.uiDemo;
    d.demo(host, 'drawer', function (pane, theme) {
      pane.appendChild(d.caption('push: a flex sibling, open at first; Escape inside closes it'));
      frame(pane, theme, 'push');
      pane.appendChild(d.caption('overlay: over the right of the frame, no scrim, closed at first'));
      frame(pane, theme, 'overlay');
    });
  }

  window.App.admin.designLanguage.uiDrawerSection = { render: render };
})();
