(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.composer(opts) -> {el, input, fileInput, setPlaceholder(text), setModel(text), setBusy(bool),
  //   setBlocked(reason|null), openFilePicker(), getValue(), setValue(text), focus(),
  //   slots: {telemetry, attachments, attachmentsStatus, queued}, fit(), destroy()}
  // (M31 F6 L04, DD4)
  //
  // The chat composer: div.ui-composer holding four caller-filled slots and then the box
  // (a visually hidden label, the textarea, and a toolbar of Attach, the model id, Stop and
  // Send).
  //
  // opts:
  //   label          the textarea's accessible name (default 'Message')
  //   placeholder    the textarea's placeholder
  //   accept         the file input's accept (default 'image/*'); multiple (default true)
  //   attachLabel    the name of the Attach button and the file input (default 'Attach images')
  //   onSend(text)   Enter, or the Send button, with the RAW value. Enter calls it whenever
  //                  the input is enabled, busy or not, and with empty text too; the caller
  //                  decides what to do. The control NEVER clears the input: the caller
  //                  calls setValue('') on success
  //   onStop()       the Stop button
  //   onAttach()     the Attach button; the caller owns the busy and blocked guard and calls
  //                  openFilePicker() itself
  //   onFiles(files) the file input's change, with the files as an array; the input is then
  //                  reset so the same file can be chosen again
  //   testid, attachTestid, fileInputTestid, modelTestid, stopTestid, sendTestid,
  //   attachmentsTestid, attachmentsStatusTestid, queuedTestid, telemetryTestid
  //                  are the per-part test ids (supplied by the caller)
  //
  // Keyboard: Enter sends, Shift+Enter is a newline, and an Enter inside an IME composition
  // (isComposing, or keyCode 229, which WebKit reports for the committing Enter) does nothing.
  // The textarea grows with its content up to about eight lines, then scrolls (fit(), run
  // on every input event; a no-op while the composer is not connected, so call it after
  // mounting). The focus ring is the box's :focus-within.
  //
  // States: setBusy(true) shows Stop and disables Send (not the input). setBlocked(reason)
  // disables the input and Attach and dims the box. Send is disabled while blocked OR busy,
  // so clearing blocked mid-turn leaves it disabled. The attachments slot hides with an
  // inline display:none (its children set their own display); the telemetry
  // slot hides with the hidden attribute, so no rule here sets a display on them.
  // fileInput is the hidden file input, a read-only reference like input (the caller may
  // mark it, e.g. data-staged). slots.queued is a persistent aria-live="polite" region that is
  // never hidden (so it stays in the accessibility tree and a chip inserted into it is announced);
  // it collapses by being empty (:empty, no margin).
  // destroy() removes every listener (idempotent).
  App.ui.composer = function (opts) {
    opts = opts || {};
    var util = App.ui.util;
    var attachLabel = opts.attachLabel || 'Attach images';
    var inputId = util.uid('composer-input');
    var blocked = false;
    var busy = false;
    var gone = false;

    function tid(node, value) {
      if (value) node.setAttribute('data-testid', value);
      return node;
    }

    var telemetry = tid(util.el('div', { className: 'ui-composer-telemetry', hidden: true }), opts.telemetryTestid);
    var attachments = tid(util.el('div', { className: 'ui-composer-attachments' }), opts.attachmentsTestid);
    attachments.style.display = 'none';
    var attachmentsStatus = tid(
      util.el('div', { className: 'visually-hidden', 'aria-live': 'polite' }),
      opts.attachmentsStatusTestid
    );
    var queued = tid(util.el('div', { className: 'ui-composer-queued', 'aria-live': 'polite' }), opts.queuedTestid);

    var label = util.el('label', {
      className: 'visually-hidden',
      'for': inputId,
      text: opts.label || 'Message'
    });
    var input = tid(util.el('textarea', {
      id: inputId,
      className: 'ui-composer-input',
      rows: '2',
      placeholder: opts.placeholder || '',
      autocomplete: 'off',
      enterkeyhint: 'send'
    }), opts.testid);
    var fileInput = tid(util.el('input', {
      type: 'file',
      accept: opts.accept || 'image/*',
      multiple: opts.multiple !== false,
      hidden: true,
      'aria-label': attachLabel
    }), opts.fileInputTestid);
    var attachBtn = App.ui.button({
      variant: 'ghost',
      size: 'sm',
      icon: 'paperclip',
      iconOnly: true,
      ariaLabel: attachLabel,
      className: 'ui-composer-attach',
      testid: opts.attachTestid
    });
    var modelEl = tid(util.el('span', { className: 'ui-composer-model' }), opts.modelTestid);
    var stopBtn = App.ui.button({
      variant: 'danger',
      icon: 'stop',
      label: 'Stop',
      ariaLabel: 'Stop',
      className: 'ui-composer-stop',
      testid: opts.stopTestid
    });
    stopBtn.hidden = true;
    var sendBtn = App.ui.button({
      variant: 'primary',
      icon: 'send',
      label: 'Send',
      className: 'ui-composer-send',
      testid: opts.sendTestid
    });
    sendBtn.setAttribute('aria-keyshortcuts', 'Enter');

    var toolbar = util.el('div', { className: 'ui-composer-toolbar' }, [
      attachBtn, fileInput, modelEl, stopBtn, sendBtn
    ]);
    var box = util.el('div', { className: 'ui-composer-box' }, [label, input, toolbar]);
    var root = util.el('div', { className: 'ui-composer' }, [
      telemetry, attachments, attachmentsStatus, queued, box
    ]);

    function fit() {
      if (gone || !root.isConnected) return;
      // Back to the rows=2 height first, so the content's own height can be read
      // (scrollHeight never reports less than the box it fills). The box holds its current
      // height meanwhile: otherwise the log above would grow for the measurement and clamp
      // its scrollTop, so a log pinned to its end would drift up on every keystroke.
      box.style.minHeight = box.offsetHeight + 'px';
      input.style.height = '';
      if (input.value && input.getClientRects().length) {
        input.style.height = input.scrollHeight + 'px';
      }
      box.style.minHeight = '';
    }
    function syncSend() {
      sendBtn.disabled = blocked || busy;
    }
    function send() {
      if (typeof opts.onSend === 'function') opts.onSend(input.value);
    }

    function onKeydown(e) {
      if (e.key !== 'Enter' || e.shiftKey) return;
      if (e.isComposing || e.keyCode === 229) return;
      if (input.disabled) return;
      e.preventDefault();
      send();
    }
    function onInput() { fit(); }
    function onSendClick() { send(); }
    function onStopClick() { if (typeof opts.onStop === 'function') opts.onStop(); }
    function onAttachClick() { if (typeof opts.onAttach === 'function') opts.onAttach(); }
    function onFileChange() {
      var files = fileInput.files ? Array.prototype.slice.call(fileInput.files) : [];
      if (typeof opts.onFiles === 'function') opts.onFiles(files);
      fileInput.value = '';
    }
    input.addEventListener('keydown', onKeydown);
    input.addEventListener('input', onInput);
    sendBtn.addEventListener('click', onSendClick);
    stopBtn.addEventListener('click', onStopClick);
    attachBtn.addEventListener('click', onAttachClick);
    fileInput.addEventListener('change', onFileChange);

    return {
      el: root,
      input: input,
      fileInput: fileInput,
      slots: {
        telemetry: telemetry,
        attachments: attachments,
        attachmentsStatus: attachmentsStatus,
        queued: queued
      },
      setPlaceholder: function (text) { input.placeholder = text === undefined || text === null ? '' : String(text); },
      setModel: function (text) { modelEl.textContent = text ? String(text) : ''; },
      setBusy: function (value) {
        busy = !!value;
        stopBtn.hidden = !busy;
        syncSend();
      },
      setBlocked: function (reason) {
        blocked = !!reason;
        input.disabled = blocked;
        attachBtn.disabled = blocked;
        box.classList.toggle('ui-composer-box--blocked', blocked);
        if (blocked && typeof reason === 'string') box.setAttribute('title', reason);
        else box.removeAttribute('title');
        syncSend();
      },
      openFilePicker: function () { fileInput.click(); },
      getValue: function () { return input.value; },
      setValue: function (text) {
        input.value = text === undefined || text === null ? '' : String(text);
        fit();
      },
      focus: function () { input.focus(); },
      fit: fit,
      destroy: function () {
        if (gone) return;
        gone = true;
        input.removeEventListener('keydown', onKeydown);
        input.removeEventListener('input', onInput);
        sendBtn.removeEventListener('click', onSendClick);
        stopBtn.removeEventListener('click', onStopClick);
        attachBtn.removeEventListener('click', onAttachClick);
        fileInput.removeEventListener('change', onFileChange);
      }
    };
  };
})();
