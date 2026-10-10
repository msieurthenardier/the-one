(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // The three General pages (M25 F3 L5a, DD6): Appearance (theme toggle),
  // Prompts (the read-only base prompt) and Encryption (the rotate flow).
  // Until L5a they were one "General" page with three blocks; each block now
  // has its own route and renders under the page's own header, so the block's
  // former section title is the page's h1 and nothing repeats it. The blocks
  // keep their markup and test ids. Each renderer owns its whole page and
  // shares no state with the others, so each block's wiring runs only on its
  // own page. Built with DOM APIs (no HTML-string sink).

  function el(tag, attrs, children) {
    return window.App.ui.util.el(tag, attrs, children);
  }

  // The page header (reference spec section 4): one h1 per page, no
  // breadcrumb. `headingId` names the h1 for controls labelled by it.
  function renderPage(container, title, headingId, sectionChildren) {
    container.textContent = '';
    container.appendChild(el('div', { className: 'page-header' }, [
      el('h1', { className: 'page-title', id: headingId || null, text: title })
    ]));
    container.appendChild(el('div', { className: 'admin-form' }, [
      el('div', { className: 'admin-system-section' }, sectionChildren)
    ]));
  }

  function text(copy) {
    return el('p', { className: 'admin-system-text', text: copy });
  }

  // ── Appearance ────────────────────────────────────────────────────────

  function renderAppearancePage(container) {
    // The theme radiogroup is labelled by the page's h1 ("Appearance"), the
    // in-page title it was labelled by before the split.
    var mount = el('div', {
      className: 'admin-theme-toggle',
      id: 'admin-theme-toggle-mount',
      'aria-labelledby': 'admin-appearance-heading'
    });
    renderPage(container, 'Appearance', 'admin-appearance-heading', [
      text('Choose a theme. Auto follows your operating system preference.'),
      mount
    ]);
    if (window.App && window.App.theme && window.App.theme.renderToggle) {
      window.App.theme.renderToggle(mount, { labelledBy: 'admin-appearance-heading' });
    }
  }

  // ── Prompts ───────────────────────────────────────────────────────────

  function promptLayer(title, help, pre) {
    var kids = [el('div', { className: 'section-title', text: title })];
    if (help) { kids.push(text(help)); }
    if (pre) { kids.push(pre); }
    return el('div', { className: 'admin-prompt-layer' }, kids);
  }

  function promptPre() {
    return el('pre', { className: 'admin-base-prompt code-block', text: 'Loading\u2026' });
  }

  function renderPromptsPage(container) {
    var base = promptPre();
    base.setAttribute('data-testid', 'base-prompt-content');
    var rules = promptPre();
    rules.setAttribute('data-testid', 'rules-prompt-content');
    var notes = promptPre();
    notes.setAttribute('data-testid', 'notes-prompt-content');
    renderPage(container, 'Prompts', null, [
      text('Every agent\u2019s system prompt is assembled from these layers, in this order, ' +
        'separated by ---: the base prompt, the agent\u2019s own system prompt (set on its General tab), ' +
        'then rules and notes. They are read-only and only change via code releases. ' +
        'The Rules and Notes layers below show placeholder content.'),
      promptLayer('Base prompt', null, base),
      promptLayer('Rules', 'Added when the agent has enabled rules, numbered in your order.', rules),
      promptLayer('Notes', 'Added last when the agent keeps notes.', notes)
    ]);
    fetchPrompts(base, rules, notes);
  }

  function fetchPrompts(baseEl, rulesEl, notesEl) {
    function fill(pre, value, fallback) {
      pre.textContent = typeof value === 'string' ? value : fallback;
    }
    fetch('/api/info')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        fill(baseEl, data.base_prompt, '(base prompt unavailable)');
        fill(rulesEl, data.rules_prompt_example, '(unavailable)');
        fill(notesEl, data.notes_prompt_example, '(unavailable)');
      })
      .catch(function () {
        [baseEl, rulesEl, notesEl].forEach(function (p) { p.textContent = '(failed to load)'; });
      });
  }

  // ── Encryption ────────────────────────────────────────────────────────

  function renderEncryptionPage(container) {
    var rotateBtn = el('button', { className: 'btn-muted-destructive', type: 'button' }, [
      el('span', { 'data-confirm-title': true, text: 'Rotate Encryption Key' })
    ]);
    rotateBtn.setAttribute('data-testid', 'rotate-key-btn');
    var flashEl = el('div', { className: 'admin-system-flash', 'aria-live': 'polite' });
    renderPage(container, 'Encryption', null, [
      text('API keys for LLM providers are encrypted at rest. ' +
        'You can rotate the encryption key to re-encrypt all stored credentials with a new key.'),
      el('div', {
        className: 'banner banner-warning',
        role: 'note',
        text: 'Rotating the encryption key re-encrypts all stored API credentials with a new key. This is irreversible.'
      }),
      rotateBtn,
      flashEl
    ]);
    wireEncryptionRotate(rotateBtn, flashEl);
  }

  function wireEncryptionRotate(rotateBtn, flashEl) {
    rotateBtn.addEventListener('click', function () {
      window.App.confirmDelete(rotateBtn, function (btn, revertFn) {
        var titleEl = btn.querySelector('[data-confirm-title]');
        btn.disabled = true;
        if (titleEl) titleEl.textContent = 'Rotating…';
        fetch('/api/encryption/rotate', { method: 'POST' })
          .then(function (r) {
            if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Rotation failed'); });
            return r.json();
          })
          .then(function (data) {
            btn.disabled = false;
            // Helper's revertFn restores the original "Rotate Encryption Key"
            // text + removes the .confirm-delete class.
            revertFn();
            if (data && data.key_file === 'staged') {
              // DB + in-memory key rotated, but the on-disk key file could
              // not be promoted (`.next` sidecar reconciles at next start).
              // Warn and leave the flash up — an operator must not mistake
              // this for the ordinary success path.
              flashEl.textContent =
                'Encryption key rotated, but the key file could not be updated on disk — ' +
                'the new key is staged and will be applied at next start. Check the server log.';
              flashEl.className = 'admin-system-flash warning';
            } else {
              // "promoted" and any other/missing key_file value are treated
              // as success (backward-compatible with older server builds).
              flashEl.textContent = 'Encryption key rotated successfully.';
              flashEl.className = 'admin-system-flash success';
              setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 3000);
            }
          })
          .catch(function (err) {
            btn.disabled = false;
            revertFn();
            flashEl.textContent = 'Error: ' + err.message;
            flashEl.className = 'admin-system-flash error';
            setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 4000);
          });
      }, { confirmLabel: 'Confirm Rotate?' });
    });
  }

  window.App.admin.renderAppearancePage = renderAppearancePage;
  window.App.admin.renderPromptsPage = renderPromptsPage;
  window.App.admin.renderEncryptionPage = renderEncryptionPage;
})();
