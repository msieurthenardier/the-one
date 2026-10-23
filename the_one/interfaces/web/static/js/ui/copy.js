(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // Copy a string: the async clipboard first, then (for a rejection or a missing
  // API) selectEl.select() plus execCommand('copy'). done(ok) runs once.
  function copyText(value, selectEl, done) {
    function fallback() {
      var ok = false;
      var temp = null;
      var target = selectEl;
      try {
        if (!target) {
          temp = document.createElement('textarea');
          temp.value = value;
          temp.setAttribute('readonly', '');
          temp.style.position = 'fixed';
          temp.style.opacity = '0';
          document.body.appendChild(temp);
          target = temp;
        }
        target.select();
        ok = !!document.execCommand('copy');
      } catch (e) { ok = false; }
      if (temp) temp.remove();
      done(ok);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        navigator.clipboard.writeText(value).then(function () { done(true); }, fallback);
      } catch (e) { fallback(); }
    } else {
      fallback();
    }
  }

  // App.ui.copyButton(opts) -> { el, button }.
  //   text: the string to copy, or a function returning it. selectEl: an input or
  //   textarea selected for the execCommand fallback. label (default "Copy"),
  //   iconOnly (the copy icon, named by label), size, className.
  //   doneText (default "Copied") and failText (default "Copy failed") set ONLY the
  //   screen-reader announcement; the visible text is always "Copied" / "Copy failed"
  //   (the canonical visible wording). liveEl: an existing role=status node to announce in (else the
  //   control owns one and el is a span.ui-copy holding both).
  //   The test id option is placed on the button itself (supplied by the caller).
  //   Feedback: the visible text reads "Copied" for 2s ("Copy failed" on failure);
  //   the accessible name follows the visible text. iconOnly changes aria-label.
  App.ui.copyButton = function (opts) {
    opts = opts || {};
    var label = opts.label || 'Copy';
    var doneText = opts.doneText || 'Copied';
    var failText = opts.failText || 'Copy failed';
    var iconOnly = !!opts.iconOnly;
    var util = App.ui.util;
    var btn = App.ui.button(iconOnly
      ? { iconOnly: true, icon: 'copy', ariaLabel: label, size: opts.size, className: opts.className }
      : { label: label, size: opts.size, className: opts.className });
    if (opts.testid) btn.setAttribute('data-testid', opts.testid);
    var live = opts.liveEl || util.el('span', { className: 'visually-hidden', role: 'status' });
    var root = opts.liveEl ? btn : util.el('span', { className: 'ui-copy' }, [btn, live]);
    var timer = null;

    function show(words) {
      if (iconOnly) btn.setAttribute('aria-label', words);
      else btn.textContent = words;
    }
    function finish(ok) {
      var visible = ok ? 'Copied' : 'Copy failed';
      show(visible);
      live.textContent = '';
      live.textContent = ok ? doneText : failText;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        timer = null;
        if (btn.isConnected) show(label);
      }, 2000);
    }
    btn.addEventListener('click', function () {
      var value = typeof opts.text === 'function' ? opts.text() : opts.text;
      copyText(String(value === undefined || value === null ? '' : value), opts.selectEl, finish);
    });
    return { el: root, button: btn };
  };

  // App.ui.copyField(opts) -> { el, input, button, setValue }: a read-only input
  // and a Copy button in one row (div.ui-copy-field).
  //   value, label (the input's accessible name), mono (default true), extra (a
  //   node or array of nodes between the input and the button), inputClass,
  //   buttonLabel (the button's resting text and name, default "Copy"), rowClass,
  //   copyClass, liveEl, doneText, failText (passed to copyButton).
  //   Test ids: the testid option on the input, copyTestid on the button.
  App.ui.copyField = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var input = App.ui.textInput({ value: opts.value, testid: opts.testid });
    input.readOnly = true;
    if (opts.label) input.setAttribute('aria-label', opts.label);
    if (opts.inputClass) input.className += ' ' + opts.inputClass;
    var copy = App.ui.copyButton({
      text: function () { return input.value; },
      selectEl: input,
      testid: opts.copyTestid,
      label: opts.buttonLabel,
      className: opts.copyClass,
      liveEl: opts.liveEl,
      doneText: opts.doneText,
      failText: opts.failText
    });
    var classes = ['ui-copy-field'];
    if (opts.mono !== false) classes.push('ui-copy-field--mono');
    if (opts.rowClass) classes.push(opts.rowClass);
    var kids = [input];
    var extra = opts.extra ? (opts.extra.nodeType ? [opts.extra] : opts.extra) : [];
    for (var i = 0; i < extra.length; i++) kids.push(extra[i]);
    kids.push(copy.el);
    var row = util.el('div', { className: classes.join(' ') }, kids);
    return {
      el: row,
      input: input,
      button: copy.button,
      setValue: function (v) { input.value = String(v); }
    };
  };
})();
