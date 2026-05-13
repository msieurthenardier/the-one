(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // Combined System page — Appearance (theme toggle) + Encryption (rotate
  // flow) + Base Prompt (read-only). The Environment env-var display block
  // was removed (no editable affordance, low diagnostic value vs prime
  // real estate); equivalent info is reachable via /api/info.

  function renderSystemPage(container) {
    container.innerHTML =
      '<div class="page-header">' +
        '<h1 class="page-title">General</h1>' +
      '</div>' +
      '<div class="general-grid">' +
        '<div class="general-card">' +
          '<div class="general-card-title" id="admin-appearance-heading">Appearance</div>' +
          '<div class="general-card-sub">' +
            'Choose a theme. Auto follows your operating system preference.' +
          '</div>' +
          '<div class="admin-theme-toggle" id="admin-theme-toggle-mount" aria-labelledby="admin-appearance-heading"></div>' +
        '</div>' +
        '<div class="general-card">' +
          '<div class="general-card-title">Encryption</div>' +
          '<div class="general-card-sub">' +
            'API keys for LLM providers are encrypted at rest. ' +
            'Rotate the key to re-encrypt all stored credentials.' +
          '</div>' +
          '<div class="banner banner-warning" role="note">' +
            'Rotating the encryption key re-encrypts all stored API credentials with a new key. This is irreversible.' +
          '</div>' +
          '<button class="btn-muted-destructive" data-testid="rotate-key-btn" type="button"><span data-confirm-title>Rotate Encryption Key</span></button>' +
          '<div class="admin-system-flash" aria-live="polite"></div>' +
        '</div>' +
        '<div class="general-card general-card--wide">' +
          '<div class="general-card-title">Base Prompt</div>' +
          '<div class="general-card-sub">' +
            'The foundational system prompt every agent inherits. ' +
            'Per-agent personas are appended to this base; ' +
            'this content is read-only and only changes via code releases.' +
          '</div>' +
          '<pre class="admin-base-prompt code-block" data-testid="base-prompt-content">Loading…</pre>' +
        '</div>' +
      '</div>';

    fetchBasePrompt(container);
    mountThemeToggle(container);
    wireEncryptionRotate(container);
  }

  function fetchBasePrompt(container) {
    fetch('/api/info')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var preEl = container.querySelector('.admin-base-prompt');
        if (!preEl) return;
        if (typeof data.base_prompt === 'string') {
          preEl.textContent = data.base_prompt;
        } else {
          preEl.textContent = '(base prompt unavailable)';
        }
      })
      .catch(function () {
        var preEl = container.querySelector('.admin-base-prompt');
        if (preEl) preEl.textContent = '(failed to load)';
      });
  }

  function mountThemeToggle(container) {
    var themeToggleEl = container.querySelector('#admin-theme-toggle-mount');
    if (window.App && window.App.theme && window.App.theme.renderToggle) {
      window.App.theme.renderToggle(themeToggleEl, { labelledBy: 'admin-appearance-heading' });
    }
  }

  function wireEncryptionRotate(container) {
    var rotateBtn = container.querySelector('[data-testid="rotate-key-btn"]');
    var flashEl = container.querySelector('.admin-system-flash');
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
          .then(function () {
            btn.disabled = false;
            // Helper's revertFn restores the original "Rotate Encryption Key"
            // text + removes the .confirm-delete class.
            revertFn();
            flashEl.textContent = 'Encryption key rotated successfully.';
            flashEl.className = 'admin-system-flash success';
            setTimeout(function () { flashEl.textContent = ''; flashEl.className = 'admin-system-flash'; }, 3000);
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

  window.App.admin.renderSystemPage = renderSystemPage;
})();
