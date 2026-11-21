(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.cornerButton(opts) -> {el, setExpanded(bool), setHidden(bool), focus()}  (M36 F3 L2)
  //
  // A 48px violet tile button with one icon, placed by its caller at a corner of a positioned
  // container (the GleepGlorp assistant's "Ask GleepGlorp" button, bottom-right of the app
  // shell row). The factory owns the tile's look and its anchor (absolute, 24px from the
  // bottom-right of the nearest positioned ancestor, z-index 9: under menus, modals and the
  // overlay drawer); the caller appends `el` to the container.
  //
  // opts:
  //   ariaLabel  the accessible name (required; the icon is aria-hidden)
  //   icon       an App.icons name (required)
  //   controls   the id of the element it opens (aria-controls)
  //   expanded   the initial aria-expanded (default false); setExpanded keeps it current
  //   testid     placed on the button; id optional
  //   onClick(e) the click handler
  //   hidden     start hidden (default false)
  //
  // A native <button type="button">: Enter and Space work with no key code of ours. Hiding uses
  // the `hidden` attribute (out of the tab order and the accessibility tree).
  App.ui.cornerButton = function (opts) {
    opts = opts || {};
    if (!opts.ariaLabel) throw new Error('App.ui.cornerButton: ariaLabel is required');
    if (!opts.icon) throw new Error('App.ui.cornerButton: icon is required');
    var btn = App.ui.util.el('button', { type: 'button', className: 'ui-corner-button' });
    btn.appendChild(App.ui.util.icon(opts.icon));
    btn.setAttribute('aria-label', opts.ariaLabel);
    if (opts.controls) btn.setAttribute('aria-controls', opts.controls);
    btn.setAttribute('aria-expanded', opts.expanded ? 'true' : 'false');
    if (opts.id) btn.id = opts.id;
    if (opts.testid) btn.setAttribute('data-testid', opts.testid);
    if (typeof opts.onClick === 'function') btn.addEventListener('click', opts.onClick);
    btn.hidden = !!opts.hidden;
    return {
      el: btn,
      setExpanded: function (open) { btn.setAttribute('aria-expanded', open ? 'true' : 'false'); },
      setHidden: function (hide) { btn.hidden = !!hide; },
      focus: function () { btn.focus(); }
    };
  };
})();
