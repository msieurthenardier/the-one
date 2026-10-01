(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  var VARIANT_CLASS = {
    primary: 'btn-filled-primary',
    secondary: 'btn-outlined-primary',
    ghost: 'btn-ghost',
    danger: 'btn-muted-destructive'
  };
  var SIZE_CLASS = { sm: 'btn-sm', lg: 'btn-lg', xl: 'btn-xl' };

  // App.ui.button(opts) -> HTMLButtonElement.
  //   variant: primary | secondary (default) | ghost | danger
  //   size: sm | lg | xl (omit for the default 32px)
  //   label: button text (set with textContent, never as HTML)
  //   icon: an App.icons name, prepended as a parsed SVG node
  //   iconOnly: true adds btn-icon and requires ariaLabel (throws otherwise)
  //   ariaLabel, disabled, onClick, className
  //   the test id option: placed on the button itself (supplied by the caller)
  App.ui.button = function (opts) {
    opts = opts || {};
    var variant = opts.variant || 'secondary';
    if (!VARIANT_CLASS[variant]) throw new Error('App.ui.button: unknown variant "' + variant + '"');
    if (opts.size && !SIZE_CLASS[opts.size]) {
      throw new Error('App.ui.button: unknown size "' + opts.size + '"');
    }
    if (opts.iconOnly && !opts.ariaLabel) {
      throw new Error('App.ui.button: iconOnly requires ariaLabel');
    }
    var classes = [VARIANT_CLASS[variant]];
    if (opts.size) classes.push(SIZE_CLASS[opts.size]);
    if (opts.iconOnly) classes.push('btn-icon');
    if (opts.className) classes.push(opts.className);
    var btn = App.ui.util.el('button', { type: 'button', className: classes.join(' ') });
    if (opts.icon) btn.appendChild(App.ui.util.icon(opts.icon));
    if (opts.label !== undefined && opts.label !== null) {
      btn.appendChild(document.createTextNode(String(opts.label)));
    }
    if (opts.ariaLabel) btn.setAttribute('aria-label', opts.ariaLabel);
    if (opts.disabled) btn.disabled = true;
    if (opts.testid) btn.setAttribute('data-testid', opts.testid);
    if (typeof opts.onClick === 'function') btn.addEventListener('click', opts.onClick);
    return btn;
  };
})();
