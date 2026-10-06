// App.chat.composer -- the chat composer's DOM (M25 F4 leg 4b extracted it;
// leg 5 restyled it to reference spec 5.5 and moved the telemetry readout
// into a row above it, 5.3; flight DD6, A25).
//
// A DOM builder with no listeners: the chat area (areas/chat.js) wires every
// handler on the references it returns. `render` and `fit` only patch the
// nodes built here (the placeholder and model text, the textarea's height).
//
// App.chat.composer.create() -> {el, box, input, fileInput, attachBtn,
//   modelEl, stopBtn, sendBtn, attachmentsEl, attachmentsStatusEl,
//   queuedRegion, telemetryRow, render(view), fit()}
//
//   el (div.composer, padding 12px 24px 20px) holds, top to bottom:
//     telemetryRow         div.composer-telemetry, the flex-end row the caller
//                          fills with App.chat.renderTelemetry() and shows
//                          only while a chat is joined (`hidden` otherwise)
//     attachmentsEl        the staged-image chicklet row (chat-attachments)
//     attachmentsStatusEl  its visually hidden aria-live status
//                          (chat-attachments-status)
//     queuedRegion         the held queued message's region
//                          (pending-queued-region, `hidden` until one is held)
//     box                  div.composer-box (max 760px, centred, --surface,
//                          a hairline, radius-md; the focus ring is its
//                          :focus-within, A25): the visually hidden label
//                          "Message", the textarea, then the toolbar:
//       input              textarea.composer-input (chat-input), rows=2,
//                          labelled by the <label for>, no aria-label
//       attachBtn          Attach images (chat-attach-btn), ghost, small,
//                          icon only (paperclip)
//       fileInput          the hidden image input (chat-image-input), named
//                          "Attach images" (squawk 0110)
//       modelEl            the agent's model id (chat-model), 11px mono,
//                          --fg-muted; empty when unknown
//       stopBtn            Stop (chat-stop-btn), hidden until a turn is busy
//       sendBtn            Send (chat-send-btn), the send icon and label,
//                          aria-keyshortcuts=Enter; pushed to the end
//   render({agent, model})  the placeholder "Message {agent}…" ("Message…"
//                           with no agent) and the model id ('' when unknown)
//   fit()                   sizes the textarea to its content: two rows at
//                           least, at most the CSS max-height (about eight
//                           lines), then it scrolls. Call it on `input` and
//                           after setting the value from script.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  // One composer per page (the chat area builds it once), so a fixed id is
  // enough for the label's `for`.
  var INPUT_ID = 'chat-composer-input';

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  function placeholder(agent) {
    return agent ? 'Message ' + String(agent) + '…' : 'Message…';
  }

  function create() {
    // HAT fix round 2 (post-L08): chicklet row of staged-image previews,
    // above the composer box (the standard multi-attachment layout), rather
    // than an inline single-image chip inside it. Hidden until an image is
    // staged. NOTE: hidden via inline style display:none (NOT the `hidden`
    // attribute) -- .chip (used per-chicklet, not on this container) sets
    // `display: inline-flex` unconditionally, which beats the UA
    // `[hidden]{display:none}` rule at equal specificity (author origin wins
    // over UA origin; see the .btn-muted-destructive[hidden] override in
    // chat.css for the same footgun) -- so this container is driven purely
    // via style.display, never `hidden`. The chat area's renderAttachments()
    // rebuilds the chicklets and toggles visibility. Its layout (wrap, gap,
    // the column width) is chat.css's `.chat-attachments`.
    var attachmentsEl = el('div', { className: 'chat-attachments' });
    attachmentsEl.setAttribute('data-testid', 'chat-attachments');
    attachmentsEl.style.display = 'none';

    // M18 F03 L01 (A1): visually hidden status element announcing a short
    // delta ("Image staged" / "Image removed" / "N images staged") on each
    // staged-image mutation. Kept SEPARATE from the chicklet row above (which
    // fully rebuilds on every mutation and would over-announce on removal).
    var attachmentsStatusEl = el('div', { className: 'visually-hidden', 'aria-live': 'polite' });
    attachmentsStatusEl.setAttribute('data-testid', 'chat-attachments-status');

    // F09-04: the pinned region for the held queued message's chip, outside
    // the scrolling message log so it cannot scroll away. The chat area's
    // showPendingQueued/clearPendingQueued fill it and toggle `hidden`.
    var queuedRegion = el('div', { className: 'pending-queued-region', hidden: true });
    queuedRegion.setAttribute('data-testid', 'pending-queued-region');

    // M25 F4 L5 (5.3): the telemetry readout's row, filled by the caller.
    var telemetryRow = el('div', { className: 'composer-telemetry', hidden: true });

    // The textarea. Its own outline is off (`outline: none` in chat.css)
    // only because the box carries the ring through :focus-within (A25).
    var label = el('label', { className: 'visually-hidden', 'for': INPUT_ID, text: 'Message' });
    var input = el('textarea', {
      id: INPUT_ID,
      className: 'composer-input',
      rows: '2',
      placeholder: placeholder(null),
      autocomplete: 'off',
      enterkeyhint: 'send'
    });
    input.setAttribute('data-testid', 'chat-input');

    // M16 F12 L08: minimal image-ingestion producer. The file input is hidden
    // (triggered through Attach); it is the control Playwright drives with
    // set_input_files. accept="image/*" restricts the OS picker; the change
    // handler also gates on file.type. `multiple` (HAT fix round 2) lets one
    // OS-picker interaction stage several images in one `change`. Squawk
    // 0110: it carries the visible button's name, because the shared label
    // resolver (and assistive tech that reaches it) sees it despite `hidden`.
    var fileInput = el('input', {
      type: 'file',
      accept: 'image/*',
      multiple: true,
      hidden: true,
      'aria-label': 'Attach images'
    });
    fileInput.setAttribute('data-testid', 'chat-image-input');

    // The attachment really is image-only, so the board's "Attach a file"
    // would be untrue (DD6).
    var attachBtn = App.ui.button({
      variant: 'ghost',
      size: 'sm',
      icon: 'paperclip',
      iconOnly: true,
      ariaLabel: 'Attach images',
      className: 'composer-attach',
      testid: 'chat-attach-btn'
    });

    var modelEl = el('span', { className: 'composer-model' });
    modelEl.setAttribute('data-testid', 'chat-model');

    // F7 L04: Stop, shown only while the current conversation is busy.
    var stopBtn = App.ui.button({
      variant: 'danger',
      icon: 'stop',
      label: 'Stop',
      ariaLabel: 'Stop',
      className: 'composer-stop',
      testid: 'chat-stop-btn'
    });
    stopBtn.hidden = true;

    var sendBtn = App.ui.button({
      variant: 'primary',
      icon: 'send',
      label: 'Send',
      className: 'composer-send',
      testid: 'chat-send-btn'
    });
    sendBtn.setAttribute('aria-keyshortcuts', 'Enter');

    var toolbar = el('div', { className: 'composer-toolbar' }, [
      attachBtn, fileInput, modelEl, stopBtn, sendBtn
    ]);
    var box = el('div', { className: 'composer-box' }, [label, input, toolbar]);
    var wrapper = el('div', { className: 'composer' }, [
      telemetryRow, attachmentsEl, attachmentsStatusEl, queuedRegion, box
    ]);

    function render(view) {
      view = view || {};
      input.placeholder = placeholder(view.agent);
      modelEl.textContent = view.model ? String(view.model) : '';
    }

    function fit() {
      // Back to the rows=2 height first, so the content's own height can be
      // read (scrollHeight never reports less than the box it fills). The
      // box holds its current height meanwhile: otherwise the message log
      // above would grow for the measurement and clamp its scrollTop, so a
      // log pinned to its end would drift up on every keystroke. Empty, or
      // not rendered (a hidden chrome measures 0): two rows.
      box.style.minHeight = box.offsetHeight + 'px';
      input.style.height = '';
      if (input.value && input.getClientRects().length) {
        input.style.height = input.scrollHeight + 'px';
      }
      box.style.minHeight = '';
    }

    return {
      el: wrapper,
      box: box,
      input: input,
      fileInput: fileInput,
      attachBtn: attachBtn,
      modelEl: modelEl,
      stopBtn: stopBtn,
      sendBtn: sendBtn,
      attachmentsEl: attachmentsEl,
      attachmentsStatusEl: attachmentsStatusEl,
      queuedRegion: queuedRegion,
      telemetryRow: telemetryRow,
      render: render,
      fit: fit
    };
  }

  window.App.chat.composer = { create: create, placeholder: placeholder };
})();
