// App.chat.attachments -- staged image attachments: the staging array, the chip row, the
// per-image and per-message caps and the attach button and file input listeners (M31 F6 L02,
// split out of areas/chat.js, moved verbatim apart from the ctx./state. prefixes).
//
// Exposes: staged (the live array), clearStagedImages, prependStaged, renderAttachments.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  function create(ctx) {
    var state = ctx.state;
    var inputEl = ctx.inputEl;
    var fileInputEl = ctx.fileInputEl;
    var attachBtn = ctx.attachBtn;

    // M16 F12 L08: minimal image-ingestion producer. Staged images
    // ({data: base64, media_type}) are collected by the file-attach handler
    // and consumed (and cleared) by the next performSend.
    // HAT fix (post-L08): a visible chicklet-row preview was added above the
    // composer so the operator can see what's attached.
    // HAT fix round 2 (post-L08): the single-image `stagedImage` slot is now
    // a `stagedImages` ARRAY — attaching APPENDS rather than replacing, and
    // the hidden file input carries `multiple` so one OS-picker interaction
    // can stage several images at once. The chicklet row lives in
    // `attachmentsEl` (`.chat-attachments`, resolved alongside
    // fileInputEl/attachBtn below) ABOVE the composer box (M25 F4 L5; above
    // the old `.input-area` row before it) — the standard multi-attachment
    // layout — rather than inline inside it. `renderAttachments()` fully
    // rebuilds the row from `stagedImages` on every mutation
    // (append/remove/clear) and mirrors non-empty-ness onto a
    // `data-staged="true"` attribute on the file input so a test can
    // deterministically wait for the async FileReader(s) to finish before
    // driving send.
    // NOTE: container visibility is driven via `style.display` (NOT the
    // `hidden` attribute) — `.chip` sets `display: inline-flex`
    // unconditionally, which beats the UA `[hidden]{display:none}` rule at
    // equal specificity (author origin wins over UA origin; see the
    // `.btn-muted-destructive[hidden]` override elsewhere in chat.css for
    // the same footgun). Each chicklet itself also uses `.chip`/`.chip-remove`
    // — no CSS file change.
    // M18 F02 L02: client-side mirror of the server's authoritative caps
    // (the_one/interfaces/web/app.py IMAGE_ATTACHMENT_CAP_BYTES /
    // IMAGE_ATTACHMENT_MAX_COUNT). UX-only — a client that bypasses these
    // is still bounded by the server-side check, which is the authoritative
    // guard. Kept in sync by convention (no shared constants module between
    // the Python backend and this static JS file).
    var IMAGE_ATTACHMENT_CAP_BYTES = 10 * 1024 * 1024; // ~10 MB per image
    var IMAGE_ATTACHMENT_MAX_COUNT = 10; // max attachments per turn
    var stagedImages = [];
    var attachmentsEl = ctx.composer.attachmentsEl;
    function renderAttachments() {
      if (fileInputEl) {
        if (stagedImages.length) fileInputEl.setAttribute('data-staged', 'true');
        else fileInputEl.removeAttribute('data-staged');
      }
      if (!attachmentsEl) return;
      attachmentsEl.replaceChildren();
      for (var i = 0; i < stagedImages.length; i++) {
        attachmentsEl.appendChild(buildAttachmentChip(stagedImages[i], i));
      }
      attachmentsEl.style.display = stagedImages.length ? 'flex' : 'none';
    }
    // M18 F03 L01 (A1): a SEPARATE visually-hidden aria-live="polite" status
    // element announces a short delta per stage/remove mutation. Deliberately
    // NOT on the visible `.chat-attachments` row above — that row fully
    // rebuilds via innerHTML on every mutation (see renderAttachments()), so
    // making IT the live region would re-announce all N remaining chips on
    // every single removal. This element's `textContent` is instead set to
    // just the delta for the mutation that just happened, mirroring the
    // aria-live="polite" precedent set by pendingQueuedEl (chat.js ~line 61).
    var attachmentsStatusEl = ctx.composer.attachmentsStatusEl;
    function announceAttachmentChange(text) {
      if (attachmentsStatusEl) attachmentsStatusEl.textContent = text;
    }
    // One removable chicklet: thumbnail + a per-chip ✕ that removes just
    // this image (closes over `idx` — safe because renderAttachments()
    // rebuilds every chip from scratch on every mutation, so indices are
    // never stale by the time a click fires).
    function buildAttachmentChip(img, idx) {
      var chip = document.createElement('div');
      chip.className = 'chat-attachment chip';
      chip.setAttribute('data-testid', 'chat-attachment');
      chip.setAttribute('data-attachment-index', String(idx));

      // M18 F03 L01 (A2): interpolate the 1-based index so no two staged
      // images share an identical accessible name (thumbnail alt / remove
      // aria-label) — with multi-image staging a user relying on a screen
      // reader could not otherwise tell which chip/remove-button was which.
      var displayIndex = idx + 1;

      var thumb = document.createElement('img');
      thumb.className = 'chat-attachment-thumb';
      thumb.alt = 'Staged image ' + displayIndex;
      thumb.style.width = '24px';
      thumb.style.height = '24px';
      thumb.style.objectFit = 'cover';
      thumb.style.borderRadius = '4px';
      thumb.style.display = 'block';
      thumb.src = 'data:' + img.media_type + ';base64,' + img.data;
      chip.appendChild(thumb);

      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'chat-attachment-remove chip-remove';
      removeBtn.setAttribute('data-testid', 'chat-attachment-remove');
      removeBtn.setAttribute('aria-label', 'Remove staged image ' + displayIndex);
      removeBtn.style.fontSize = '12px';
      removeBtn.textContent = '✕';
      removeBtn.addEventListener('click', function () { removeStagedImage(idx); });
      chip.appendChild(removeBtn);

      return chip;
    }
    function appendStagedImage(img) {
      stagedImages.push(img);
      renderAttachments();
      announceAttachmentChange(
        stagedImages.length === 1 ? 'Image staged' : stagedImages.length + ' images staged'
      );
    }
    function removeStagedImage(idx) {
      stagedImages.splice(idx, 1);
      renderAttachments();
      announceAttachmentChange('Image removed');
    }
    function clearStagedImages() {
      stagedImages = [];
      renderAttachments();
    }

    // The array restored in front of whatever is staged now (a start_failed hands the
    // failed first message's images back).
    function prependStaged(images) {
      stagedImages = images.concat(stagedImages);
      renderAttachments();
    }
    function staged() { return stagedImages; }

    // M16 F12 L08: minimal image-ingestion producer. Attach (chat-attach-btn) opens
    // the OS file picker; the hidden file input's `change` handler reads
    // EVERY selected file (HAT fix round 2: `multiple` + iterate
    // fileInputEl.files, appending — a prior selection is not replaced) via
    // FileReader.readAsDataURL and stages {data, media_type} (base64 payload
    // with the `data:...;base64,` prefix stripped) per file for the next
    // performSend. Attach-while-a-turn-is-running is out of scope for L08
    // (the F09-04 hold queue carries text only) — both handlers ignore the
    // interaction while the current session is busy rather than staging an
    // image that would silently be dropped by the hold-queue clear above.
    attachBtn.addEventListener('click', function () {
      if (ctx.send.isCurrentBusy() || (state.sessionBannerEl || inputEl.disabled)) return;
      fileInputEl.click();
    });
    fileInputEl.addEventListener('change', function () {
      // Snapshot into a real array BEFORE clearing `.value` below — the
      // input's `.files` FileList is LIVE (tied to the element), so
      // resetting `.value` empties it in place; a stored reference to the
      // FileList itself (rather than to the individual File objects) would
      // silently see length 0 by the time the loop below runs.
      var files = fileInputEl.files ? Array.prototype.slice.call(fileInputEl.files) : [];
      // Reset the input value so selecting the SAME file(s) again still
      // fires `change` (browsers do not re-fire change for an unchanged
      // value).
      fileInputEl.value = '';
      if (!files.length) return;
      if (ctx.send.isCurrentBusy()) return;
      // M18 F02 L02: per-file size check + count cap. `plannedCount` (NOT
      // `stagedImages.length` alone) tracks images already staged PLUS
      // ones scheduled earlier in this same batch — FileReader is async,
      // so a multi-select batch would otherwise schedule more than
      // IMAGE_ATTACHMENT_MAX_COUNT reads before any of them resolves and
      // increments `stagedImages`.
      var plannedCount = stagedImages.length;
      var rejectedForSize = false;
      var rejectedForCount = false;
      for (var i = 0; i < files.length; i++) {
        (function (file) {
          // Only image/* is staged — a non-image pick (accept="image/*"
          // already restricts the OS picker, but this guards direct DOM
          // manipulation, e.g. Playwright's set_input_files) is silently
          // ignored per-file.
          if (file.type.indexOf('image/') !== 0) return;
          if (file.size > IMAGE_ATTACHMENT_CAP_BYTES) {
            rejectedForSize = true;
            return;
          }
          if (plannedCount >= IMAGE_ATTACHMENT_MAX_COUNT) {
            rejectedForCount = true;
            return;
          }
          plannedCount++;
          var reader = new FileReader();
          reader.onload = function () {
            var result = String(reader.result || '');
            var comma = result.indexOf(',');
            var base64 = comma >= 0 ? result.slice(comma + 1) : result;
            appendStagedImage({ data: base64, media_type: file.type });
          };
          reader.readAsDataURL(file);
        })(files[i]);
      }
      // Cap-rejection notices announce via the established addMsg('system',
      // ...) mechanism, which lands in the message log's own
      // role="log" aria-live="polite" region (chat.js ~line 279) — that has
      // always announced these to SR users. The M18 F03 L01 a11y pass added
      // a SEPARATE live-region (announceAttachmentChange()) that only
      // covers the staging-row silence (stage/remove of individual
      // chicklets); it is intentionally not wired to these cap notices.
      if (rejectedForSize) {
        ctx.transcript.addMsg(
          'system',
          'One or more images exceed the ' +
            Math.floor(IMAGE_ATTACHMENT_CAP_BYTES / (1024 * 1024)) +
            ' MB per-image limit and were not attached.'
        );
      }
      if (rejectedForCount) {
        ctx.transcript.addMsg(
          'system',
          'Only up to ' +
            IMAGE_ATTACHMENT_MAX_COUNT +
            ' images can be attached per message; extra selections were not attached.'
        );
      }
    });

    return {
      staged: staged,
      clearStagedImages: clearStagedImages,
      prependStaged: prependStaged,
      renderAttachments: renderAttachments
    };
  }

  window.App.chat.attachments = { create: create };
})();
